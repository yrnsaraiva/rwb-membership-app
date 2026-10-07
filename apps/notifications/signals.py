"""Gatilhos automáticos de notificações: evento novo publicado."""
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone

from apps.events.models import Event

from . import services


@receiver(post_save, sender=Event)
def announce_new_event(sender, instance, created, raw=False, **kwargs):
    """Avisa todos uma única vez, quando o evento fica publicado e ainda é futuro (também se estava em rascunho)."""
    if raw or instance.announced_at or not instance.is_published or instance.starts_at <= timezone.now():
        return
    # Atómico: se dois pedidos publicarem ao mesmo tempo, só um anuncia
    now = timezone.now()
    if not Event.objects.filter(pk=instance.pk, announced_at__isnull=True).update(announced_at=now):
        return
    instance.announced_at = now  # um novo save() deste mesmo objecto não pode apagar a marca
    when = timezone.localtime(instance.starts_at).strftime("%d/%m às %H:%M")
    services.broadcast("Novo evento: " + instance.title, f"{when} · {instance.location}", url=f"/eventos/{instance.slug}/",
                       tag=f"event-{instance.pk}")
