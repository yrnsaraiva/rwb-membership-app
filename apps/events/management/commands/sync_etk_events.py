from django.core.management.base import BaseCommand, CommandError

from apps.events import etk


class Command(BaseCommand):
    help = "Sincroniza os eventos da API de bilhetes (ETK). Correr de 10 em 10 minutos."

    def add_arguments(self, parser):
        parser.add_argument("--no-prune", action="store_true", help="não despublicar eventos que a ETK já não devolve")

    def handle(self, *args, **opts):
        try:
            result = etk.sync_events(prune=not opts["no_prune"])
        except etk.EtkError as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(self.style.SUCCESS(f"ETK: {result}"))
