from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.events.models import Registration
from apps.notifications import services


class Command(BaseCommand):
    help = "Lembra os inscritos de eventos que começam nas próximas N horas (correr de hora a hora)."

    def add_arguments(self, parser):
        parser.add_argument("--hours", type=int, default=24)

    def handle(self, *args, **opts):
        settings.PUSH_SYNC = True  # o processo acaba logo a seguir: envia no próprio comando
        now = timezone.now()
        regs = (Registration.objects.filter(
            status=Registration.Status.CONFIRMED, reminder_sent_at__isnull=True,
            event__is_published=True, event__starts_at__gt=now, event__starts_at__lte=now + timedelta(hours=opts["hours"]))
            .select_related("event", "user"))
        sent = 0
        for reg in regs:
            when = timezone.localtime(reg.event.starts_at).strftime("%H:%M")
            day = "hoje" if timezone.localtime(reg.event.starts_at).date() == timezone.localdate() else "amanhã"
            services.notify(reg.user, f"Lembrete: {reg.event.title}", f"{day.capitalize()} às {when} · {reg.event.location}",
                            url=f"/eventos/{reg.event.slug}/", tag=f"reminder-{reg.event_id}")
            Registration.objects.filter(pk=reg.pk).update(reminder_sent_at=now)
            sent += 1
        self.stdout.write(self.style.SUCCESS(f"{sent} lembrete(s) processado(s)."))
