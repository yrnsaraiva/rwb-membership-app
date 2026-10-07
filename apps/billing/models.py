"""
Planos e subscrições premium (RF-07).

Fase actual: SEM integração de pagamento. O membro pede a subscrição, paga fora da app
(numerário, transferência, M-Pesa manual) e um administrador activa-a no painel.
A integração M-Pesa C2B (fase seguinte) irá criar um modelo Payment ligado a Subscription
e activar a subscrição automaticamente no callback — os campos abaixo já o preveem.
"""
from datetime import timedelta

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone


class Plan(models.Model):
    name = models.CharField("nome", max_length=60)
    slug = models.SlugField(unique=True)
    price_mzn = models.DecimalField("preço (MZN)", max_digits=10, decimal_places=2)
    duration_days = models.PositiveIntegerField("duração (dias)", default=30)
    description = models.CharField("descrição curta", max_length=200, blank=True)
    benefits = models.TextField("benefícios", blank=True, help_text="Um benefício por linha.")
    is_active = models.BooleanField("activo", default=True)
    is_featured = models.BooleanField("destacado", default=False)
    order = models.PositiveSmallIntegerField("ordem", default=0)

    class Meta:
        verbose_name = "plano"
        verbose_name_plural = "planos"
        ordering = ["order", "price_mzn"]

    def __str__(self):
        return f"{self.name} ({self.price_mzn} MZN)"

    @property
    def benefit_list(self):
        return [b.strip() for b in self.benefits.splitlines() if b.strip()]


class SubscriptionQuerySet(models.QuerySet):
    def active(self):
        now = timezone.now()
        return self.filter(status=Subscription.Status.ACTIVE, starts_at__lte=now).filter(
            Q(ends_at__isnull=True) | Q(ends_at__gt=now)
        )

    def pending(self):
        return self.filter(status=Subscription.Status.PENDING)


class Subscription(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pendente"
        ACTIVE = "active", "Activa"
        CANCELLED = "cancelled", "Cancelada"
        EXPIRED = "expired", "Expirada"

    class Method(models.TextChoices):
        MANUAL = "manual", "Manual (confirmado pelo clube)"
        CASH = "cash", "Numerário"
        BANK = "bank", "Transferência bancária"
        MPESA_MANUAL = "mpesa_manual", "M-Pesa (confirmação manual)"
        MPESA_C2B = "mpesa_c2b", "M-Pesa C2B (automático — fase 2)"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="subscriptions",
                             verbose_name="membro")
    plan = models.ForeignKey(Plan, on_delete=models.PROTECT, related_name="subscriptions", verbose_name="plano")
    status = models.CharField("estado", max_length=12, choices=Status.choices, default=Status.PENDING)
    payment_method = models.CharField("método de pagamento", max_length=20, choices=Method.choices, default=Method.MANUAL)
    payment_reference = models.CharField("referência do pagamento", max_length=80, blank=True)
    amount_mzn = models.DecimalField("valor (MZN)", max_digits=10, decimal_places=2)
    starts_at = models.DateTimeField("início", null=True, blank=True)
    ends_at = models.DateTimeField("fim", null=True, blank=True)
    notes = models.TextField("notas internas", blank=True)
    activated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                     related_name="+", verbose_name="activada por")
    created_at = models.DateTimeField("pedido em", auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = SubscriptionQuerySet.as_manager()

    class Meta:
        verbose_name = "subscrição"
        verbose_name_plural = "subscrições"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user} · {self.plan.name} · {self.get_status_display()}"

    @property
    def is_current(self):
        now = timezone.now()
        return (self.status == self.Status.ACTIVE and self.starts_at and self.starts_at <= now
                and (self.ends_at is None or self.ends_at > now))

    @property
    def days_left(self):
        if not self.is_current or not self.ends_at:
            return None
        return max((self.ends_at - timezone.now()).days, 0)

    def activate(self, by=None, method=None, reference=""):
        """Activa (ou renova) a subscrição. Se já houver uma activa, estende a partir do fim dessa."""
        now = timezone.now()
        current = Subscription.objects.active().filter(user=self.user).exclude(pk=self.pk).order_by("-ends_at").first()
        start = current.ends_at if current and current.ends_at and current.ends_at > now else now
        self.status = self.Status.ACTIVE
        self.starts_at = start
        self.ends_at = start + timedelta(days=self.plan.duration_days)
        self.activated_by = by
        if method:
            self.payment_method = method
        if reference:
            self.payment_reference = reference
        self.save()
        from apps.notifications import services as push

        push.notify(self.user, "Premium activo", f"O plano {self.plan.name} está activo até {self.ends_at:%d/%m/%Y}.",
                    url="/premium/", tag=f"subscription-{self.pk}")
