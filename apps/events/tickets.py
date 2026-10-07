"""Inscrições vindas da ETK: a ETK emite, cobra e dá a entrada; a `Registration` local é o espelho de cada bilhete.

Fluxos:
- `buy_ticket`: o membro inscreve-se na app → cria o bilhete na ETK (grátis nasce pago; pago inicia a cobrança no telemóvel).
- `confirm_presence`: pré-inscrição → confirma presença na ETK.
- `refresh_registration` / `refresh_member` / `sync_tickets`: lêem o estado na ETK e actualizam o espelho (pagamento
  concluído, entrada dada à porta, bilhetes comprados no site). Entradas dadas fora da app também pagam os pontos.
"""
import logging
from datetime import timedelta
from decimal import Decimal

from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from apps.core.emails import send_templated_email
from apps.notifications import services as push

from . import etk
from . import services as event_services
from .models import Event, Registration, SyncCursor

logger = logging.getLogger(__name__)

# estado do pagamento na ETK → estado da inscrição aqui
CONFIRMED_STATES = {"paid", "invited", "preregistered"}
ANNOUNCE_STATES = {"paid", "invited"}  # a pré-inscrição ainda não garante lugar: só avisa quando a presença for confirmada
PENDING_STATES = {"pending", "review"}
PAYMENT_METHODS = {"mpesa": "M-Pesa", "emola": "e-Mola", "mkesh": "mKesh", "card": "Cartão"}


class TicketError(Exception):
    """Mensagem em português para mostrar ao membro."""


def _status_for(payment: str) -> str:
    if payment in CONFIRMED_STATES:
        return Registration.Status.CONFIRMED
    if payment in PENDING_STATES:
        return Registration.Status.PENDING
    return Registration.Status.CANCELLED  # failed, refunded…


def _find_member(ticket: dict):
    from .ticket_checkin import find_member

    return find_member(ticket.get("phone", ""), ticket.get("email", ""))


@transaction.atomic
def upsert_registration(ticket: dict, user=None, *, via_app=False):
    """Cria/actualiza o espelho de um bilhete da ETK. Devolve a Registration, ou None se o titular não for membro
    (ou o evento ainda não estiver sincronizado). Idempotente."""
    event = Event.objects.filter(external_id=ticket.get("eventId")).first()
    user = user or _find_member(ticket)
    if event is None or user is None:
        return None
    payment = ticket.get("payment", "")
    new_status = _status_for(payment)

    reg = Registration.objects.select_for_update().filter(external_ticket_id=ticket["id"]).first()
    if reg is None:
        # Um membro tem uma inscrição por evento: se já tem outra, só a substitui um bilhete "melhor" (e nunca o contrário)
        other = Registration.objects.select_for_update().filter(event=event, user=user).first()
        if other is not None and other.external_ticket_id and other.status in (Registration.Status.CONFIRMED,
                                                                              Registration.Status.PENDING):
            return other
        reg = other or Registration(event=event, user=user)
        reg.via_app = via_app
    previous = reg.status if reg.pk else None
    updated_at = parse_datetime(str(ticket.get("updatedAt") or ""))
    if reg.pk and updated_at and reg.ticket_updated_at and updated_at < reg.ticket_updated_at:
        return reg  # aviso atrasado (webhook repetido/fora de ordem): o estado que já temos é mais recente

    reg.external_ticket_id = ticket["id"]
    reg.status = new_status
    reg.cancelled_at = timezone.now() if new_status == Registration.Status.CANCELLED else None
    reg.ticket_payment = payment
    reg.ticket_qr = ticket.get("qrValue", "") or reg.ticket_qr
    reg.ticket_price_name = (ticket.get("price") or {}).get("name", "")[:100]
    reg.ticket_amount = Decimal(str(ticket["amount"])) if ticket.get("amount") is not None else None
    reg.ticket_expires_at = parse_datetime(str(ticket.get("expiresAt") or ""))
    reg.ticket_checkout_url = ticket.get("checkoutUrl") or ""
    reg.ticket_instructions = (ticket.get("paymentInstructions") or reg.ticket_instructions or "")[:255]
    reg.ticket_entered = bool(ticket.get("entered"))
    reg.ticket_synced_at = timezone.now()
    reg.ticket_updated_at = updated_at or reg.ticket_updated_at
    reg.save()

    # Entrou (por qualquer porta, também pela app da ETK): paga os pontos de presença uma só vez
    if reg.ticket_entered and reg.is_active and not reg.checked_in_at:
        event_services.check_in(reg)
        reg.refresh_from_db()

    if reg.via_app and previous == Registration.Status.PENDING and payment in ANNOUNCE_STATES:
        _announce_confirmed(reg)
    return reg


def _announce_confirmed(reg):
    transaction.on_commit(lambda: send_templated_email(
        "registration_confirmed", reg.user.email, {"user": reg.user, "event": reg.event, "registration": reg}))
    push.notify(reg.user, "Bilhete confirmado", f"{reg.event.title} — o teu bilhete já está na app.",
                url=reg.event.get_absolute_url(), tag=f"ticket-{reg.pk}")


def _full_name(user):
    return user.get_full_name() or user.display_name


def buy_ticket(user, event, price_id="", payment_method="") -> Registration:
    """Inscreve o membro: cria o bilhete na ETK e o espelho aqui. Levanta TicketError com texto para o membro."""
    if not event.is_external:
        raise TicketError("Este evento não é gerido pela ETK.")
    if not event.is_published or event.is_past:
        raise TicketError("As inscrições para este evento não estão abertas.")
    phone = user.phone_e164
    if not phone:
        raise TicketError("Indica o teu telemóvel (84/85/86/87… ) no perfil: é com ele que o bilhete fica associado.")
    existing = Registration.objects.filter(event=event, user=user).first()
    if existing and existing.status in (Registration.Status.CONFIRMED, Registration.Status.PENDING):
        raise TicketError("Já tens inscrição neste evento." if existing.is_active else "Tens um pagamento por concluir neste evento.")
    if event.members_only and not user.is_premium:
        raise TicketError("Este evento é exclusivo para membros premium.")

    prices = {p["id"]: p for p in event.sellable_prices}
    if not prices:
        raise TicketError("Bilhetes esgotados.")
    price = prices.get(price_id) if price_id else (next(iter(prices.values())) if len(prices) == 1 else None)
    if price is None:
        raise TicketError("Escolhe o tipo de bilhete.")
    method = payment_method.lower()
    if price["amount"] > 0 and method not in PAYMENT_METHODS:
        raise TicketError("Escolhe como queres pagar.")

    # A ETK deduplica por referência: leva o telemóvel para que bases diferentes (staging, restauros) nunca partilhem bilhetes
    reference = f"rwb:{user.pk}:{phone}:{event.external_id}"
    try:
        ticket = etk.create_ticket(
            price_id=price["id"], event_id=event.external_id, phone=phone, full_name=_full_name(user), email=user.email,
            payment_method=method if price["amount"] > 0 else "", external_reference=reference)
    except etk.EtkRejected as exc:
        raise TicketError(str(exc)) from exc
    except etk.EtkError as exc:
        logger.warning("Falha da ETK ao criar bilhete: %s", exc)
        # Pode ter ficado a meio (resposta perdida, gateway lento): se a ETK chegou a criar o bilhete, aproveita-o
        ticket = _recover_ticket(phone, event, reference)
        if ticket is None:
            raise TicketError("Não foi possível falar com o serviço de bilhetes. Tenta novamente daqui a pouco.") from exc

    if ticket.get("phone") != phone:  # defesa: nunca espelhar o bilhete de outra pessoa
        logger.error("A ETK devolveu o bilhete %s de outro telemóvel para o membro %s", ticket.get("id"), user.pk)
        raise TicketError("Não foi possível emitir o bilhete. Contacta o clube.")
    reg = upsert_registration(ticket, user, via_app=True)
    if reg is None:  # nunca devia acontecer (evento e membro existem)
        raise TicketError("Bilhete criado, mas não foi possível registá-lo. Contacta o clube.")
    if reg.ticket_payment in ANNOUNCE_STATES:  # pré-inscrição só se anuncia quando a presença for confirmada
        _announce_confirmed(reg)
    return reg


def _recover_ticket(phone, event, reference):
    try:
        for t in etk.fetch_tickets(phone=phone, event_id=event.external_id, timeout=6):
            if t.get("externalReference") == reference and t.get("payment") in ("paid", "pending", "preregistered"):
                return t
    except etk.EtkError:
        pass
    return None


def refresh_registration(reg, timeout=8):
    """Pergunta à ETK o estado actual do bilhete (para o ecrã «a aguardar pagamento»)."""
    if not reg.external_ticket_id:
        return reg
    try:
        return upsert_registration(etk.get_ticket(reg.external_ticket_id, timeout=timeout), reg.user) or reg
    except etk.EtkError:
        return reg  # mantém o último estado conhecido


def confirm_presence(user, event) -> Registration:
    """Pré-inscrição: confirma a presença na ETK."""
    reg = Registration.objects.filter(event=event, user=user, external_ticket_id__isnull=False).first()
    if reg is None or reg.ticket_payment != "preregistered":
        raise TicketError("Não tens uma pré-inscrição por confirmar neste evento.")
    try:
        # A confirmação exige o telemóvel do bilhete (pode não ser o do perfil se o bilhete foi ligado por email)
        phone = etk.get_ticket(reg.external_ticket_id).get("phone") or user.phone_e164
        ticket = etk.confirm_ticket(reg.external_ticket_id, phone)
    except etk.EtkError as exc:
        raise TicketError(str(exc) if isinstance(exc, etk.EtkRejected) else "Não foi possível confirmar agora. Tenta novamente.") from exc
    reg = upsert_registration(ticket, user) or reg
    if reg.ticket_payment in ANNOUNCE_STATES:
        _announce_confirmed(reg)
    return reg


def refresh_member(member, timeout=4):
    """Traz para aqui os bilhetes que o membro tem na ETK (compras feitas no site). Para a ficha lida pelo staff."""
    if not member.phone_e164:
        return []
    return [r for r in (upsert_registration(t, member) for t in etk.fetch_tickets(phone=member.phone_e164, timeout=timeout)) if r]


def sync_tickets(full=False) -> dict:
    """Espelha os bilhetes alterados desde a última sincronização (ou todos). Para correr de poucos em poucos minutos."""
    started = timezone.now()
    since = None
    if not full:
        cursor = SyncCursor.objects.filter(name="etk_tickets").first()
        if cursor:
            since = (cursor.synced_at - timedelta(minutes=2)).isoformat()
    tickets = etk.fetch_tickets(since=since)
    matched = sum(1 for t in tickets if upsert_registration(t))
    # O cursor avança mesmo que os bilhetes sejam de quem não é membro (senão voltavam a ser lidos em cada execução)
    SyncCursor.objects.update_or_create(name="etk_tickets", defaults={"synced_at": started})
    # Reservas por pagar que a ETK já libertou (ou que ficaram sem notícia) são limpas a pedido, bilhete a bilhete
    stale = Registration.objects.filter(status=Registration.Status.PENDING, ticket_expires_at__lt=timezone.now())
    for reg in stale:
        refresh_registration(reg)
    return {"fetched": len(tickets), "matched": matched}

