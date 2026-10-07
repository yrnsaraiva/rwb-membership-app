"""Receptor dos avisos da ETK (`ticket.paid`, `ticket.refunded`): o espelho das inscrições actualiza-se na hora.

Contrato (etk-api, ticketing/webhooks.py): POST JSON `{"event": "...", "data": <bilhete>}` com os cabeçalhos
`X-ETK-Signature` (HMAC-SHA256 em hex do corpo cru, com o segredo do organizador), `X-ETK-Event` e `X-ETK-Delivery-ID`.
A ETK repete a entrega (1, 5, 15, 60 min…) até receber 2xx, por isso respondemos 2xx a tudo o que já foi tratado ou não
nos diz respeito e 5xx só quando falhámos a processar.
"""
import hashlib
import hmac
import json
import logging

from django.conf import settings
from django.db import IntegrityError, transaction
from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from . import tickets
from .models import Event, WebhookDelivery

logger = logging.getLogger(__name__)
HANDLED = {"ticket.paid", "ticket.refunded"}
MAX_BODY = 256 * 1024


def signature_is_valid(body: bytes, header: str) -> bool:
    expected = hmac.new(settings.ETK_WEBHOOK_SECRET.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, (header or "").strip().lower())


@csrf_exempt
@require_POST
def etk_webhook(request):
    if not settings.ETK_WEBHOOK_SECRET:
        return HttpResponse(status=404)  # desligado até haver segredo: nunca aceitar avisos sem assinatura
    body = request.body
    if len(body) > MAX_BODY or not signature_is_valid(body, request.headers.get("X-ETK-Signature", "")):
        return HttpResponse(status=401)
    try:
        payload = json.loads(body)
        event, data = payload["event"], payload["data"]
        delivery_id = request.headers["X-ETK-Delivery-ID"][:40]
        if not isinstance(data, dict) or not data.get("id"):
            raise ValueError("bilhete em falta")
    except (ValueError, KeyError, TypeError):
        return HttpResponse(status=400)
    if event not in HANDLED:
        return JsonResponse({"status": "ignored"})
    if not Event.objects.filter(external_id=data.get("eventId")).exists():
        return HttpResponse(status=503)  # o evento ainda não foi sincronizado: a ETK volta a tentar mais tarde
    try:
        with transaction.atomic():
            # Se o processamento falhar, a marca desfaz-se e a ETK volta a tentar
            WebhookDelivery.objects.create(delivery_id=delivery_id, event=event, ticket_id=data["id"])
            tickets.upsert_registration(data)
    except IntegrityError:
        return JsonResponse({"status": "duplicate"})  # já tratado
    except Exception:  # noqa: BLE001
        logger.exception("Falha ao processar o aviso %s da ETK", delivery_id)
        return HttpResponse(status=500)
    return JsonResponse({"status": "ok"})
