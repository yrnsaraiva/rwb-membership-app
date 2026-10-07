"""Envio de emails transaccionais (Hostinger SMTP em produção, consola em desenvolvimento)."""
import logging

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string

logger = logging.getLogger(__name__)


def send_templated_email(template, to, context=None, fail_silently=True):
    """
    Renderiza templates/emails/<template>_subject.txt, <template>.txt e <template>.html.
    Falhas de SMTP nunca devem partir o fluxo do utilizador (ex.: inscrição num evento).
    """
    context = {"site_url": settings.SITE_URL, "site_name": settings.SITE_NAME, **(context or {})}
    recipients = [to] if isinstance(to, str) else list(to)
    try:
        subject = render_to_string(f"emails/{template}_subject.txt", context).strip().replace("\n", " ")
        text = render_to_string(f"emails/{template}.txt", context)
        html = render_to_string(f"emails/{template}.html", context)
        msg = EmailMultiAlternatives(subject, text, settings.DEFAULT_FROM_EMAIL, recipients)
        msg.attach_alternative(html, "text/html")
        msg.send()
        return True
    except Exception:  # noqa: BLE001
        logger.exception("Falha ao enviar email '%s' para %s", template, recipients)
        if not fail_silently:
            raise
        return False


def notify_staff(subject, body):
    staff = list(get_user_model().objects.filter(is_staff=True, is_active=True).values_list("email", flat=True))
    if not staff:
        return False
    return send_templated_email("staff_notice", staff, {"subject": subject, "body": body})
