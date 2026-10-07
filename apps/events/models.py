from django.conf import settings
from django.db import models
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify


class EventQuerySet(models.QuerySet):
    def published(self):
        return self.filter(is_published=True)

    def upcoming(self):
        return self.published().filter(starts_at__gte=timezone.now()).order_by("starts_at")

    def past(self):
        return self.published().filter(starts_at__lt=timezone.now()).order_by("-starts_at")

    def with_counts(self):
        return self.annotate(
            confirmed_count=models.Count("registrations", filter=Q(registrations__status=Registration.Status.CONFIRMED))
        )


def cover_upload_to(instance, filename):
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "jpg"
    return f"events/{instance.slug or 'evento'}-{timezone.now():%Y%m%d%H%M%S}.{ext}"


class Event(models.Model):
    class Kind(models.TextChoices):
        GROUP_RUN = "group_run", "Corrida de grupo"
        RACE = "race", "Prova"
        TRAINING = "training", "Treino"
        SOCIAL = "social", "Social"

    title = models.CharField("título", max_length=140)
    slug = models.SlugField(max_length=160, unique=True, blank=True)
    kind = models.CharField("tipo", max_length=20, choices=Kind.choices, default=Kind.GROUP_RUN)
    summary = models.CharField("resumo", max_length=200, blank=True)
    description = models.TextField("descrição", blank=True)
    location = models.CharField("local", max_length=160)
    meeting_point = models.CharField("ponto de encontro", max_length=160, blank=True)
    map_url = models.URLField("link do mapa", blank=True)
    starts_at = models.DateTimeField("início")
    ends_at = models.DateTimeField("fim", null=True, blank=True)
    distances = models.CharField("distâncias", max_length=80, blank=True, help_text="Ex.: 5 km · 10 km")
    capacity = models.PositiveIntegerField("vagas", null=True, blank=True, help_text="Vazio = sem limite")
    registration_opens_at = models.DateTimeField("abertura das inscrições", null=True, blank=True)
    registration_closes_at = models.DateTimeField("fecho das inscrições", null=True, blank=True)
    price_mzn = models.DecimalField("preço (MZN)", max_digits=10, decimal_places=2, default=0,
                                    help_text="Informativo no MVP — pagamento feito fora da app.")
    members_only = models.BooleanField("só membros premium", default=False)
    checkin_points = models.PositiveIntegerField("pontos por presença", null=True, blank=True,
                                                 help_text="Vazio = valor por defeito do clube")
    cover = models.ImageField("imagem de capa", upload_to=cover_upload_to, blank=True)
    is_published = models.BooleanField("publicado", default=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                   related_name="+", verbose_name="criado por")
    announced_at = models.DateTimeField("anunciado por push em", null=True, blank=True, editable=False)

    # Eventos vindos da API de bilhetes (ETK) — ver apps/events/etk.py. Estes campos só o sincronizador altera.
    external_id = models.CharField("ID na ETK", max_length=40, unique=True, null=True, blank=True, editable=False)
    external_url = models.URLField("página de bilhetes", blank=True, editable=False)
    image_url = models.URLField("imagem (URL)", blank=True, editable=False)
    ticket_prices = models.JSONField("bilhetes", default=list, blank=True, editable=False)
    synced_at = models.DateTimeField("sincronizado em", null=True, blank=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = EventQuerySet.as_manager()

    class Meta:
        verbose_name = "evento"
        verbose_name_plural = "eventos"
        ordering = ["starts_at"]
        indexes = [models.Index(fields=["is_published", "starts_at"], name="event_published_start_idx")]

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(self.title)[:140] or "evento"
            slug, n = base, 2
            while Event.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f"{base}-{n}"
                n += 1
            self.slug = slug
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("events:detail", args=[self.slug])

    # --- Origem externa (ETK) ------------------------------------------------------
    @property
    def is_external(self):
        return bool(self.external_id)

    @property
    def cover_url(self):
        if self.cover:
            return self.cover.url
        return self.image_url

    @property
    def has_paid_ticket(self):
        """Algum lote de bilhetes tem preço > 0: a inscrição faz-se (e paga-se) na ETK, não aqui."""
        return any(float(p.get("amount") or 0) > 0 for p in self.ticket_prices)

    @property
    def min_ticket_price(self):
        amounts = [float(p.get("amount") or 0) for p in self.ticket_prices if p.get("status") == "active"]
        return min(amounts) if amounts else 0

    @property
    def tickets_available(self):
        return sum(int(p.get("available") or 0) for p in self.ticket_prices if p.get("status") == "active")

    # --- Regras de vagas e inscrição -------------------------------------------
    @property
    def confirmed_total(self):
        if hasattr(self, "confirmed_count"):
            return self.confirmed_count
        return self.registrations.filter(status=Registration.Status.CONFIRMED).count()

    @property
    def spots_left(self):
        if self.capacity is None:
            return None
        return max(self.capacity - self.confirmed_total, 0)

    @property
    def is_full(self):
        return self.capacity is not None and self.spots_left == 0

    @property
    def is_past(self):
        return self.starts_at < timezone.now()

    @property
    def registration_is_open(self):
        now = timezone.now()
        if not self.is_published or self.is_past:
            return False
        if self.registration_opens_at and now < self.registration_opens_at:
            return False
        if self.registration_closes_at and now > self.registration_closes_at:
            return False
        return True

    @property
    def registration_opens_later(self):
        return bool(self.registration_opens_at and timezone.now() < self.registration_opens_at)

    @property
    def effective_checkin_points(self):
        if self.checkin_points is not None:
            return self.checkin_points
        return settings.RWB_EVENT_CHECKIN_POINTS


class Registration(models.Model):
    class Status(models.TextChoices):
        CONFIRMED = "confirmed", "Confirmada"
        CANCELLED = "cancelled", "Cancelada"

    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="registrations", verbose_name="evento")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="registrations", verbose_name="membro")
    status = models.CharField("estado", max_length=12, choices=Status.choices, default=Status.CONFIRMED)
    distance = models.CharField("distância escolhida", max_length=20, blank=True)
    checked_in_at = models.DateTimeField("presença registada em", null=True, blank=True)
    created_at = models.DateTimeField("inscrito em", auto_now_add=True)
    cancelled_at = models.DateTimeField("cancelado em", null=True, blank=True)
    reminder_sent_at = models.DateTimeField("lembrete enviado em", null=True, blank=True, editable=False)

    class Meta:
        verbose_name = "inscrição"
        verbose_name_plural = "inscrições"
        ordering = ["created_at"]
        constraints = [models.UniqueConstraint(fields=["event", "user"], name="unique_registration_per_event")]

    def __str__(self):
        return f"{self.user} → {self.event}"

    @property
    def is_active(self):
        return self.status == self.Status.CONFIRMED
