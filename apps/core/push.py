"""Notificações push. Ponto único de envio: o resto da app só chama send_push().

O transporte (FCM/APNs) ainda não está ligado: sem credenciais configuradas, send_push() não envia nada e devolve 0.
Quando o projecto Firebase existir, implementar _deliver() (FCM HTTP v1 cobre Android e iOS).
"""
import logging

from django.conf import settings

logger = logging.getLogger(__name__)


def _deliver(device, title, body, data):
    raise NotImplementedError("Transporte push por implementar (FCM).")


def send_push(user, title, body, data=None) -> int:
    """Envia para todos os dispositivos do membro. Devolve quantos foram entregues; nunca levanta excepções."""
    if not getattr(settings, "PUSH_ENABLED", False):
        return 0
    sent = 0
    for device in user.devices.all():
        try:
            _deliver(device, title, body, data or {})
            sent += 1
        except Exception:  # noqa: BLE001
            logger.exception("Falha ao enviar push para o dispositivo %s", device.pk)
    return sent
