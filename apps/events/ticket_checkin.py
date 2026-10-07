"""Entrada de quem comprou bilhete na ETK: marca a entrada na ETK e dá a presença (e os pontos) ao membro RWB.

O membro é reconhecido pelo telemóvel do bilhete (258…) e, se não bater, pelo email. Só se atribui a um membro quando a
correspondência é única: dois membros com o mesmo número não recebem pontos por engano.
"""
import re
from dataclasses import dataclass

from django.contrib.auth import get_user_model
from django.db import transaction

from apps.accounts.phone import normalize_phone

from . import etk
from . import services as event_services
from .models import Event, Registration

QR_PATTERN = re.compile(r"^TCKT\d+\|[0-9a-f]{16}$")
MESSAGES = {
    "ok": "Entrada autorizada",
    "already_entered": "Este bilhete já foi usado",
    "not_paid": "Bilhete sem pagamento confirmado",
    "not_found": "Bilhete não encontrado",
    "invalid_qr": "QR não reconhecido",
    "error": "Não foi possível falar com a ETK",
}


@dataclass
class Outcome:
    result: str
    message: str
    holder: str = ""
    event_title: str = ""
    member: object = None
    points: int = 0
    registered: bool = False

    @property
    def admitted(self):
        return self.result in ("ok", "already_entered")

    def as_dict(self):
        return {"result": self.result, "message": self.message, "holder": self.holder, "event": self.event_title,
                "member": {"name": self.member.display_name, "member_number": self.member.member_number} if self.member else None,
                "points": self.points, "registered": self.registered}


def find_member(phone="", email=""):
    """Membro activo com este telemóvel (ou, em alternativa, email) — só se for único."""
    User = get_user_model()
    normalized = normalize_phone(phone)
    if normalized:
        matches = list(User.objects.filter(phone_e164=normalized, is_active=True)[:2])
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            return None
    if email:
        return User.objects.filter(email__iexact=email.strip(), is_active=True).first()
    return None


@transaction.atomic
def _record_presence(member, event):
    """Inscreve (se faltar) e marca a presença; o check_in é idempotente, por isso nunca paga pontos duas vezes."""
    registration, created = Registration.objects.select_for_update().get_or_create(event=event, user=member)
    if not registration.is_active:
        registration.status = Registration.Status.CONFIRMED
        registration.cancelled_at = None
        registration.save(update_fields=["status", "cancelled_at"])
    awarded = event_services.check_in(registration)
    return (event.effective_checkin_points if awarded else 0), True


def check_in_by_qr(qr_value: str) -> Outcome:
    """Bilhete lido à porta (QR `TCKT…|assinatura`)."""
    qr_value = (qr_value or "").strip()
    if not QR_PATTERN.match(qr_value):
        return Outcome("invalid_qr", MESSAGES["invalid_qr"])
    try:
        res = etk.check_in_ticket(qr_value)
    except etk.EtkError:
        return Outcome("error", MESSAGES["error"])
    ticket = res["ticket"] or {}
    outcome = Outcome(res["result"], MESSAGES.get(res["result"], res["message"] or "Resultado desconhecido"),
                      holder=ticket.get("fullName") or "", event_title=(ticket.get("event") or {}).get("name", ""))
    if outcome.admitted:
        _attach_member(outcome, ticket)
    return outcome


def _attach_member(outcome: Outcome, ticket: dict):
    outcome.member = find_member(ticket.get("phone", ""), ticket.get("email", ""))
    event = Event.objects.filter(external_id=ticket.get("eventId")).first()
    if outcome.member and event:
        outcome.points, outcome.registered = _record_presence(outcome.member, event)


def tickets_for_member(member, timeout=4):
    """Bilhetes pagos do membro (por telemóvel) para eventos futuros/de hoje ainda sem entrada. [] se não tiver número."""
    if not member.phone_e164:
        return []
    return [t for t in etk.fetch_paid_tickets(phone=member.phone_e164, timeout=timeout) if not t.get("entered")]


def check_in_member_ticket(member, ticket_id: str) -> Outcome:
    """Staff leu o cartão do membro (não o bilhete): usa o QR do bilhete que a ETK tem para esse telemóvel."""
    try:
        tickets = [t for t in etk.fetch_paid_tickets(phone=member.phone_e164) if t.get("id") == ticket_id]
    except etk.EtkError:
        return Outcome("error", MESSAGES["error"])
    if not member.phone_e164 or not tickets:
        return Outcome("not_found", MESSAGES["not_found"])
    return check_in_by_qr(tickets[0]["qrValue"])
