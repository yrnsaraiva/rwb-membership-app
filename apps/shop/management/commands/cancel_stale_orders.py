from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.shop.models import Order
from apps.shop.services import cancel_order


class Command(BaseCommand):
    help = "Cancela encomendas por pagar há mais de N dias e devolve o stock (correr diariamente)."

    def add_arguments(self, parser):
        parser.add_argument("--days", type=int, default=settings.RWB_SHOP_HOLD_DAYS)

    def handle(self, *args, **opts):
        limit = timezone.now() - timedelta(days=opts["days"])
        n = 0
        for order in Order.objects.filter(status=Order.Status.PENDING, created_at__lt=limit):
            cancel_order(order, reason=f"sem pagamento após {opts['days']} dias")
            n += 1
        self.stdout.write(self.style.SUCCESS(f"{n} encomenda(s) cancelada(s)."))
