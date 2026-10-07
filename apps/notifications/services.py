"""Envio de notificações Web Push (VAPID). Ponto único: o resto da app só chama notify()/broadcast().

O envio é feito em segundo plano (thread) para não atrasar o pedido do utilizador; falhas nunca partem o fluxo.
Subscrições que o serviço push diz estarem mortas (404/410) são apagadas; as que falham repetidamente também.
"""
import json
import logging
from concurrent.futures import ThreadPoolExecutor

from django.conf import settings
from django.db import close_old_connections, transaction
from django.utils import timezone

from .models import PushSubscription

logger = logging.getLogger(__name__)
MAX_FAILURES = 5
_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="push")


def is_enabled() -> bool:
    return bool(settings.VAPID_PUBLIC_KEY and settings.VAPID_PRIVATE_KEY)


def build_payload(title, body, url="/", tag=None) -> str:
    return json.dumps({"title": title, "body": body, "url": url, "tag": tag}, ensure_ascii=False)


def _send_one(sub_id, payload) -> bool:
    from pywebpush import WebPushException, webpush

    sub = PushSubscription.objects.filter(pk=sub_id).first()
    if sub is None:
        return False
    try:
        webpush(subscription_info=sub.as_webpush(), data=payload, vapid_private_key=settings.VAPID_PRIVATE_KEY,
                vapid_claims={"sub": settings.VAPID_CONTACT}, ttl=60 * 60 * 12, timeout=10)
    except WebPushException as exc:
        status = getattr(getattr(exc, "response", None), "status_code", None)
        if status in (404, 410):  # subscrição cancelada ou expirada
            sub.delete()
        else:
            logger.warning("Push falhou (%s) para a subscrição %s: %s", status, sub_id, exc)
            sub.failures += 1
            if sub.failures >= MAX_FAILURES:
                sub.delete()
            else:
                sub.save(update_fields=["failures"])
        return False
    except Exception:  # noqa: BLE001
        logger.exception("Erro inesperado a enviar push para %s", sub_id)
        return False
    sub.failures = 0
    sub.last_success_at = timezone.now()
    sub.save(update_fields=["failures", "last_success_at"])
    return True


def _deliver(sub_ids, payload):
    close_old_connections()
    try:
        return sum(_send_one(pk, payload) for pk in sub_ids)
    finally:
        close_old_connections()


def _dispatch(sub_ids, payload):
    if not sub_ids:
        return 0
    if getattr(settings, "PUSH_SYNC", False):  # testes e comandos agendados
        return _deliver(sub_ids, payload)
    _executor.submit(_deliver, sub_ids, payload)
    return len(sub_ids)


def notify(users, title, body, url="/", tag=None) -> int:
    """Envia a um ou vários membros (depois do commit da transacção actual). Devolve nº de dispositivos alvo."""
    if not is_enabled():
        return 0
    users = [users] if hasattr(users, "pk") else list(users)
    sub_ids = list(PushSubscription.objects.filter(user__in=users, user__is_active=True).values_list("pk", flat=True))
    payload = build_payload(title, body, url, tag)
    transaction.on_commit(lambda: _dispatch(sub_ids, payload))
    return len(sub_ids)


def broadcast(title, body, url="/", tag=None) -> int:
    """Envia a todos os membros com notificações activas."""
    if not is_enabled():
        return 0
    sub_ids = list(PushSubscription.objects.filter(user__is_active=True).values_list("pk", flat=True))
    payload = build_payload(title, body, url, tag)
    transaction.on_commit(lambda: _dispatch(sub_ids, payload))
    return len(sub_ids)
