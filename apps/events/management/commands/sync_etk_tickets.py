from django.core.management.base import BaseCommand, CommandError

from apps.events import etk, tickets


class Command(BaseCommand):
    help = ("Espelha os bilhetes da ETK nas inscrições (pagamentos concluídos, entradas dadas à porta, compras feitas no site). "
            "Correr de 5 em 5 minutos, depois do sync_etk_events.")

    def add_arguments(self, parser):
        parser.add_argument("--full", action="store_true", help="ler todos os bilhetes, não só os alterados desde a última vez")

    def handle(self, *args, **opts):
        try:
            result = tickets.sync_tickets(full=opts["full"])
        except etk.EtkError as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(self.style.SUCCESS(f"ETK: {result['fetched']} bilhete(s) lido(s), {result['matched']} ligado(s) a membros"))
