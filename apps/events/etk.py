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
    pass


@dataclass
class SyncResult:
    created: int = 0
    updated: int = 0
    unpublished: int = 0
    skipped: list = field(default_factory=list)

    def __str__(self):
        extra = f", {len(self.skipped)} ignorado(s)" if self.skipped else ""
        return f"{self.created} criado(s), {self.updated} atualizado(s), {self.unpublished} despublicado(s){extra}"


def fetch_events() -> list:
    if not settings.ETK_ENABLED:
        raise EtkError("ETK não configurada (defina ETK_BASE e ETK_API_KEY).")
    url = settings.ETK_BASE + settings.ETK_EVENTS_PATH
    try:
        resp = requests.get(url, headers={"Authorization": f"Bearer {settings.ETK_API_KEY}", "Accept": "application/json"},
                            timeout=settings.ETK_TIMEOUT)
    except requests.RequestException as exc:
        raise EtkError(f"Falha de rede ao contactar a ETK: {exc}") from exc
    if resp.status_code in (401, 403):
        raise EtkError("A ETK recusou a chave de API (ETK_API_KEY inválida ou revogada).")
    if resp.status_code != 200:
        raise EtkError(f"A ETK respondeu {resp.status_code}.")
    try:
        body = resp.json()
    except ValueError as exc:
        raise EtkError("Resposta da ETK não é JSON.") from exc
    if not isinstance(body, dict) or body.get("status") != "success" or not isinstance(body.get("data"), list):
        raise EtkError("Resposta da ETK fora do formato esperado.")
    return body["data"]


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
        "external_url": settings.ETK_PUBLIC_EVENT_URL.format(id=data["id"]) if settings.ETK_PUBLIC_EVENT_URL else "",
    }
    if prices and not any(p["amount"] > 0 for p in prices):
        # Evento grátis: a lotação definida na ETK passa a ser o limite das inscrições aqui
        fields["capacity"] = int(data.get("totalTicketsPurchased") or 0) + sum(p["available"] for p in prices if p["status"] == "active")
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
