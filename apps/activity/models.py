from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.urls import reverse


class RunQuerySet(models.QuerySet):
    def valid(self):
        return self.filter(is_valid=True)


class Run(models.Model):
    """Corrida registada manualmente pelo membro (RF-04)."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="runs", verbose_name="membro")
    date = models.DateField("data")
    distance_km = models.DecimalField("distância (km)", max_digits=6, decimal_places=2,
                                      validators=[MinValueValidator(Decimal("0.1"))])
    duration = models.DurationField("duração")
    pace_sec_per_km = models.PositiveIntegerField("ritmo (s/km)", null=True, blank=True, editable=False, db_index=True)
    title = models.CharField("título", max_length=80, blank=True)
    notes = models.TextField("notas", blank=True, max_length=500)
    event = models.ForeignKey("events.Event", on_delete=models.SET_NULL, null=True, blank=True,
                              related_name="runs", verbose_name="evento")
    is_valid = models.BooleanField("válida", default=True, help_text="Desmarcar para invalidar (moderação) — remove os pontos.")
    moderation_note = models.CharField("nota de moderação", max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = RunQuerySet.as_manager()

    class Meta:
        verbose_name = "corrida"
        verbose_name_plural = "corridas"
        ordering = ["-date", "-created_at"]
        indexes = [models.Index(fields=["user", "date"], name="run_user_date_idx")]

    def __str__(self):
        return f"{self.user} · {self.distance_km} km · {self.date:%d/%m/%Y}"

    def save(self, *args, **kwargs):
        self.pace_sec_per_km = self.compute_pace()
        super().save(*args, **kwargs)

    def compute_pace(self):
        km = float(self.distance_km or 0)
        if km <= 0 or not self.duration:
            return None
        return int(round(self.duration.total_seconds() / km))

    @property
    def pace_seconds(self):
        """Ritmo em segundos por km."""
        return self.pace_sec_per_km if self.pace_sec_per_km is not None else self.compute_pace()

    @property
    def points(self):
        return sum(t.amount for t in self.point_transactions.all())

    def get_absolute_url(self):
        return reverse("activity:run_list")


class PointTransaction(models.Model):
    """Livro de pontos: cada ganho/perda de pontos fica registado aqui (RF-05)."""

    class Reason(models.TextChoices):
        RUN = "run", "Corrida"
        STREAK_BONUS = "streak_bonus", "Bónus de streak"
        EVENT_CHECKIN = "event_checkin", "Presença em evento"
        ADJUSTMENT = "adjustment", "Ajuste manual"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="point_transactions",
                             verbose_name="membro")
    amount = models.IntegerField("pontos")
    reason = models.CharField("motivo", max_length=20, choices=Reason.choices)
    description = models.CharField("descrição", max_length=160, blank=True)
    run = models.ForeignKey(Run, on_delete=models.CASCADE, null=True, blank=True, related_name="point_transactions")
    registration = models.ForeignKey("events.Registration", on_delete=models.CASCADE, null=True, blank=True,
                                     related_name="point_transactions")
    reference_date = models.DateField("data de referência", null=True, blank=True)
    created_at = models.DateTimeField("data", auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = "movimento de pontos"
        verbose_name_plural = "movimentos de pontos"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "reference_date"],
                condition=models.Q(reason="streak_bonus"),
                name="one_streak_bonus_per_day",
            ),
        ]

    def __str__(self):
        return f"{self.user} {self.amount:+d} ({self.get_reason_display()})"
