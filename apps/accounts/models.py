import uuid
from functools import cached_property

from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models
from django.urls import reverse
from django.utils import timezone


class UserManager(BaseUserManager):
    use_in_migrations = True

    def _create_user(self, email, password, **extra_fields):
        if not email:
            raise ValueError("O email é obrigatório.")
        email = self.normalize_email(email).lower()
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        if not extra_fields.get("is_staff") or not extra_fields.get("is_superuser"):
            raise ValueError("Superutilizador tem de ter is_staff=True e is_superuser=True.")
        return self._create_user(email, password, **extra_fields)


def avatar_upload_to(instance, filename):
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "jpg"
    return f"avatars/{instance.card_token}.{ext}"


class User(AbstractUser):
    """Membro do clube. Autentica por email; tem número de sócio único e cartão digital (RF-01)."""

    username = None
    email = models.EmailField("email", unique=True)
    member_number = models.CharField("número de sócio", max_length=20, unique=True, null=True, blank=True, editable=False)
    phone = models.CharField("telemóvel", max_length=20, blank=True)
    city = models.CharField("cidade", max_length=80, blank=True, default="Maputo")
    date_of_birth = models.DateField("data de nascimento", null=True, blank=True)
    bio = models.TextField("sobre mim", blank=True, max_length=500)
    avatar = models.ImageField("fotografia", upload_to=avatar_upload_to, blank=True)
    card_token = models.UUIDField("token do cartão", default=uuid.uuid4, unique=True, editable=False)
    show_on_leaderboard = models.BooleanField("aparecer no ranking", default=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["first_name", "last_name"]

    objects = UserManager()

    class Meta:
        verbose_name = "membro"
        verbose_name_plural = "membros"
        ordering = ["first_name", "last_name"]

    def __str__(self):
        return self.display_name

    def save(self, *args, **kwargs):
        if self.email:
            self.email = self.email.lower()
        super().save(*args, **kwargs)
        if not self.member_number:
            # Número sequencial legível, derivado da chave primária: RWB-00042
            self.member_number = f"RWB-{self.pk:05d}"
            type(self).objects.filter(pk=self.pk).update(member_number=self.member_number)

    def set_password(self, raw_password):
        super().set_password(raw_password)
        if self.pk:  # mudar a palavra-passe revoga o token da API (dispositivos perdidos/roubados)
            from rest_framework.authtoken.models import Token

            Token.objects.filter(user_id=self.pk).delete()

    def regenerate_card_token(self):
        """Invalida o QR/link antigo do cartão (cartão partilhado ou fotografado)."""
        self.card_token = uuid.uuid4()
        self.save(update_fields=["card_token"])

    @property
    def display_name(self):
        full = self.get_full_name().strip()
        return full or self.email.split("@")[0]

    @property
    def initials(self):
        parts = [p for p in [self.first_name, self.last_name] if p]
        if not parts:
            return self.email[:2].upper()
        return "".join(p[0] for p in parts[:2]).upper()

    @cached_property
    def is_premium(self):
        from apps.billing.models import Subscription

        return Subscription.objects.active().filter(user=self).exists()

    def get_absolute_url(self):
        return reverse("accounts:profile")

    def get_verify_url(self):
        return reverse("accounts:verify", args=[self.card_token])

    @property
    def member_since(self):
        return timezone.localtime(self.date_joined).date()
