from django.conf import settings
from django.db import models


class PushSubscription(models.Model):
    """Subscrição Web Push de um navegador/PWA instalada (um membro pode ter várias: telemóvel, PC…)."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="push_subscriptions",
                             verbose_name="membro")
    endpoint = models.CharField("endpoint", max_length=700, unique=True)
    p256dh = models.CharField(max_length=255)
    auth = models.CharField(max_length=255)
    user_agent = models.CharField("dispositivo", max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_success_at = models.DateTimeField("último envio com sucesso", null=True, blank=True)
    failures = models.PositiveSmallIntegerField("falhas seguidas", default=0)

    class Meta:
        verbose_name = "subscrição push"
        verbose_name_plural = "subscrições push"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user} · {self.user_agent[:40] or 'dispositivo'}"

    def as_webpush(self):
        return {"endpoint": self.endpoint, "keys": {"p256dh": self.p256dh, "auth": self.auth}}
