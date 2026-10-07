from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.billing.models import Subscription


class Command(BaseCommand):
    help = "Marca como expiradas as subscrições activas cujo período terminou (correr diariamente)."

    def handle(self, *args, **options):
        n = Subscription.objects.filter(status=Subscription.Status.ACTIVE, ends_at__lte=timezone.now()).update(
            status=Subscription.Status.EXPIRED
        )
        self.stdout.write(self.style.SUCCESS(f"{n} subscrição(ões) expirada(s)."))
