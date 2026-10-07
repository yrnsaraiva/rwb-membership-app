"""Sincronização dos eventos a partir da API de bilhetes (ETK).

A ETK é a fonte dos eventos (nome, data, local, imagem, bilhetes). Aqui copiam-se para a tabela local para que
inscrições grátis, presenças, pontos, lembretes e push continuem a funcionar e a app não pare se a ETK estiver em baixo.
Campos que só existem no RWB (pontos de presença, só-premium, ponto de encontro, mapa, distâncias) nunca são sobrescritos.

Contrato da ETK (repositório etk-api): GET {ETK_BASE}/back/borrow/external/events com `Authorization: Bearer etk_live_...`
→ {"status": "success", "message": "...", "data": [{id, name, description, category, date, imageUrl, status, location:
{province, details}, prices: [{id, name, amount, currency, status, available}], totalTicketsPurchased, ...}]}
"""
import logging
from dataclasses import dataclass, field

import requests
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from .models import Event

logger = logging.getLogger(__name__)

KIND_BY_CATEGORY = {
    "social_run": Event.Kind.GROUP_RUN, "group_run": Event.Kind.GROUP_RUN, "run": Event.Kind.GROUP_RUN,
    "race": Event.Kind.RACE, "competition": Event.Kind.RACE,
    "training": Event.Kind.TRAINING, "workout": Event.Kind.TRAINING,
    "social": Event.Kind.SOCIAL,
}


class EtkError(Exception):
    """A ETK está indisponível, mal configurada ou respondeu fora do contrato (problema nosso/dela, não do pedido)."""


class EtkRejected(EtkError):
    """A ETK recusou o pedido por regra de negócio (esgotado, número inválido, pagamento recusado…). `str(exc)` é
    uma mensagem em português própria para mostrar ao utilizador."""


@dataclass
class SyncResult:
    created: int = 0
    updated: int = 0
    unpublished: int = 0
    skipped: list = field(default_factory=list)

    def __str__(self):
        extra = f", {len(self.skipped)} ignorado(s)" if self.skipped else ""
        return f"{self.created} criado(s), {self.updated} atualizado(s), {self.unpublished} despublicado(s){extra}"


def _request(method, path, *, params=None, json=None, timeout=None):
    """Pedido autenticado à ETK. Devolve o corpo JSON (envelope) ou levanta EtkError / EtkRejected."""
    if not settings.ETK_ENABLED:
        raise EtkError("ETK não configurada (defina ETK_BASE e ETK_API_KEY).")
    try:
        resp = requests.request(method, settings.ETK_BASE + path, params=params, json=json, timeout=timeout or settings.ETK_TIMEOUT,
                                headers={"Authorization": f"Bearer {settings.ETK_API_KEY}", "Accept": "application/json"})
    except requests.RequestException as exc:
        raise EtkError(f"Falha de rede ao contactar a ETK: {exc}") from exc
    if resp.status_code in (401, 403):
        raise EtkError("A ETK recusou a chave de API (ETK_API_KEY inválida ou revogada).")
    try:
        body = resp.json()
    except ValueError as exc:
        raise EtkError(f"Resposta da ETK ({resp.status_code}) não é JSON.") from exc
    if resp.status_code in (400, 402, 404, 409) and isinstance(body, dict):
        raise EtkRejected(str(body.get("message") or "Pedido recusado pela ETK."))
    if resp.status_code not in (200, 201):
        raise EtkError(f"A ETK respondeu {resp.status_code}.")
    if not isinstance(body, dict) or body.get("status") != "success":
        raise EtkError("Resposta da ETK fora do formato esperado.")
    return body


def fetch_events() -> list:
    data = _request("GET", settings.ETK_EVENTS_PATH).get("data")
    if not isinstance(data, list):
        raise EtkError("Resposta da ETK fora do formato esperado.")
    return data


def _location(data) -> str:
    loc = data.get("location") or {}
    parts = [str(loc.get("details") or "").strip(), str(loc.get("province") or "").strip()]
    return ", ".join(p for p in parts if p)[:160] or "A confirmar"


def _prices(data) -> list:
    return [{"id": p.get("id", ""), "name": p.get("name", ""), "amount": float(p.get("amount") or 0),
             "currency": p.get("currency", "MZN"), "status": p.get("status", ""), "available": int(p.get("available") or 0)}
            for p in data.get("prices") or []]


def map_event(data: dict) -> dict:
    """Campos do Event local que a ETK controla. Levanta ValueError se faltar o essencial."""
    starts_at = parse_datetime(str(data.get("date") or ""))
    if not data.get("id") or not data.get("name") or starts_at is None:
        raise ValueError("evento sem id, nome ou data válida")
    if timezone.is_naive(starts_at):
        starts_at = timezone.make_aware(starts_at, timezone.utc)
    prices = _prices(data)
    fields = {
        "title": str(data["name"])[:140],
        "description": data.get("description") or "",
        "kind": KIND_BY_CATEGORY.get(str(data.get("category") or "").lower(), Event.Kind.GROUP_RUN),
        "starts_at": starts_at,
        "location": _location(data),
        "image_url": data.get("imageUrl") or "",
        "ticket_prices": prices,
        "is_published": data.get("status") == "published",
        "registration_mode": data.get("registrationMode") or "",
        "confirmation_opens_at": parse_datetime(str(data.get("confirmationOpensAt") or "")),
        "confirmation_deadline": parse_datetime(str(data.get("confirmationDeadline") or "")),
        "external_url": settings.ETK_PUBLIC_EVENT_URL.format(id=data["id"]) if settings.ETK_PUBLIC_EVENT_URL else "",
    }
    return fields


def sync_events(prune=True) -> SyncResult:
    """Cria/atualiza os eventos da ETK. Com `prune`, despublica os eventos locais que a ETK já não publica."""
    remote = fetch_events()
    result = SyncResult()
    now = timezone.now()
    first_run = not Event.objects.filter(external_id__isnull=False).exists()
    seen = set()
    for data in remote:
        try:
            fields = map_event(data)
        except (ValueError, TypeError) as exc:
            logger.warning("Evento ETK ignorado (%s): %s", data.get("id") if isinstance(data, dict) else "?", exc)
            result.skipped.append(str(exc))
            continue
        external_id = data["id"]
        seen.add(external_id)
        with transaction.atomic():
            event = Event.objects.select_for_update().filter(external_id=external_id).first()
            if event is None:
                # Primeira sincronização: não anuncia por push dezenas de eventos de uma vez
                event = Event(external_id=external_id, summary=(fields["description"].split("\n")[0])[:200],
                              announced_at=now if first_run else None)
                result.created += 1
            else:
                result.updated += 1
            for name, value in fields.items():
                setattr(event, name, value)
            event.synced_at = now
            event.save()
    if prune and remote is not None:
        stale = Event.objects.filter(external_id__isnull=False, is_published=True).exclude(external_id__in=seen)
        result.unpublished = stale.update(is_published=False)
    return result


# --- Bilhetes e entrada --------------------------------------------------------------------
TICKETS_PATH = "/back/borrow/external/tickets"


def fetch_tickets(*, phone=None, event_id=None, payment=None, since=None, timeout=None) -> list:
    """Bilhetes emitidos com a nossa chave (a ETK devolve no máximo 500, os mais recentes primeiro)."""
    params = {k: v for k, v in {"phone": phone, "eventId": event_id, "payment": payment, "since": since}.items() if v}
    data = _request("GET", TICKETS_PATH, params=params, timeout=timeout).get("data")
    if not isinstance(data, list):
        raise EtkError("Resposta da ETK fora do formato esperado.")
    return data


def fetch_paid_tickets(phone=None, event_id=None, timeout=None) -> list:
    return fetch_tickets(phone=phone, event_id=event_id, payment="paid", timeout=timeout)


def get_ticket(ticket_id: str, timeout=None) -> dict:
    data = _request("GET", f"{TICKETS_PATH}/{ticket_id}", timeout=timeout).get("data")
    if not isinstance(data, dict):
        raise EtkError("Resposta da ETK fora do formato esperado.")
    return data


def create_ticket(*, price_id, event_id, phone, full_name="", email="", payment_method="", external_reference="") -> dict:
    """Emite o bilhete (e inicia o pagamento, se for pago). Devolve o bilhete + `paymentInstructions`."""
    payload = {"priceId": price_id, "eventId": event_id, "phone": phone, "fullName": full_name, "email": email,
               "paymentMethod": payment_method, "externalReference": external_reference}
    data = _request("POST", TICKETS_PATH, json={k: v for k, v in payload.items() if v}, timeout=max(settings.ETK_TIMEOUT, 30)).get("data")
    if not isinstance(data, dict) or "id" not in data:
        raise EtkError("Resposta da ETK fora do formato esperado.")
    return data


def confirm_ticket(ticket_id: str, phone: str) -> dict:
    """Confirma a presença de uma pré-inscrição."""
    data = _request("POST", f"{TICKETS_PATH}/{ticket_id}/confirm", json={"phone": phone}).get("data")
    if not isinstance(data, dict):
        raise EtkError("Resposta da ETK fora do formato esperado.")
    return data


def check_in_ticket(qr_value: str) -> dict:
    """Marca a entrada na ETK. Devolve {'result': ok|already_entered|not_paid|not_found|invalid_qr, 'message', 'ticket'}."""
    body = _request("POST", TICKETS_PATH + "/check-in", json={"qrValue": qr_value})
    data = body.get("data")
    if not isinstance(data, dict) or "result" not in data:
        raise EtkError("Resposta da ETK fora do formato esperado.")
    return {"result": data["result"], "message": body.get("message", ""), "ticket": data.get("ticket")}
