"""Cria dados de demonstração: planos, eventos, membros e corridas. Uso: python manage.py seed_demo"""
import random
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.activity import services as activity
from apps.billing.models import Plan
from apps.events.models import Event
from apps.shop.models import Category, Product, ProductVariant

NAMES = [
    ("Ana", "Macuácua"), ("Bruno", "Sitoe"), ("Carla", "Nhantumbo"), ("Délcio", "Cossa"), ("Edna", "Mondlane"),
    ("Fábio", "Langa"), ("Graça", "Tembe"), ("Hélio", "Chissano"), ("Inês", "Matsinhe"), ("Jorge", "Mabunda"),
]


class Command(BaseCommand):
    help = "Popula a base de dados com dados de demonstração."

    def add_arguments(self, parser):
        parser.add_argument("--password", default="corrida2026", help="Palavra-passe dos membros demo")

    def handle(self, *args, **opts):
        User = get_user_model()
        Plan.objects.get_or_create(slug="mensal", defaults={
            "name": "Premium Mensal", "price_mzn": Decimal("500"), "duration_days": 30, "order": 1,
            "description": "Tudo o que o clube oferece, mês a mês.",
            "benefits": "Acesso a eventos exclusivos\nDesconto em provas parceiras\nKit de boas-vindas\nBadge premium no ranking",
        })
        Plan.objects.get_or_create(slug="anual", defaults={
            "name": "Premium Anual", "price_mzn": Decimal("5000"), "duration_days": 365, "order": 2, "is_featured": True,
            "description": "Dois meses grátis face ao plano mensal.",
            "benefits": "Tudo do plano mensal\n2 meses grátis\nT-shirt oficial RWB\nPrioridade nas inscrições",
        })

        now = timezone.now().replace(minute=0, second=0, microsecond=0)
        events = [
            ("Corrida de Sábado na Marginal", Event.Kind.GROUP_RUN, 3, "Marginal de Maputo", "5 km · 10 km", 80),
            ("Treino de Intervalos — Costa do Sol", Event.Kind.TRAINING, 5, "Costa do Sol", "6 km", 30),
            ("RWB 10K Night Run", Event.Kind.RACE, 18, "Praça da Independência", "5 km · 10 km", 250),
            ("Pequeno-almoço pós-corrida", Event.Kind.SOCIAL, 10, "Café Continental", "", 40),
            ("Long Run de Domingo", Event.Kind.GROUP_RUN, -4, "Jardim dos Namorados", "15 km · 21 km", None),
        ]
        for title, kind, days, place, distances, cap in events:
            starts = (now + timedelta(days=days)).replace(hour=6)
            Event.objects.get_or_create(title=title, defaults={
                "kind": kind, "starts_at": starts, "ends_at": starts + timedelta(hours=2), "location": place,
                "distances": distances, "capacity": cap,
                "summary": "Todos os ritmos são bem-vindos. Ninguém fica para trás.",
                "description": "Encontro 15 minutos antes para aquecimento em grupo.\n\nTraz água e boa energia!",
            })

        apparel, _ = Category.objects.get_or_create(slug="vestuario", defaults={"name": "Vestuário", "order": 1})
        acc, _ = Category.objects.get_or_create(slug="acessorios", defaults={"name": "Acessórios", "order": 2})
        catalogue = [
            ("T-shirt técnica RWB", apparel, "1200", None, ["S", "M", "L", "XL"], True,
             "Tecido respirável de secagem rápida, com o logótipo do clube no peito."),
            ("Singlet de prova RWB", apparel, "950", "1100", ["S", "M", "L"], False, "Leve e cortado para dias de prova."),
            ("Hoodie Running Club", apparel, "2500", None, ["M", "L", "XL"], True, "Para o aquecimento e o pós-corrida."),
            ("Boné RWB", acc, "700", None, ["Tamanho único"], False, "Aba curva, ajustável, amarelo e preto."),
            ("Garrafa 750 ml", acc, "600", None, ["Tamanho único"], False, "Sem BPA, com tampa de bico."),
        ]
        for i, (name, cat, price, old, sizes, featured, summary) in enumerate(catalogue):
            product, created = Product.objects.get_or_create(name=name, defaults={
                "category": cat, "price_mzn": Decimal(price), "compare_at_price_mzn": Decimal(old) if old else None,
                "is_featured": featured, "summary": summary, "order": i,
            })
            if created:
                for j, size in enumerate(sizes):
                    ProductVariant.objects.create(product=product, name=size, stock=0 if size == "XL" else 12, order=j,
                                                  sku=f"RWB-{product.pk:03d}-{size[:3].upper()}")

        pwd = opts["password"]
        today = timezone.localdate()
        rnd = random.Random(42)
        for i, (first, last) in enumerate(NAMES):
            email = f"{first.lower()}.{last.lower()}@exemplo.co.mz".replace("é", "e").replace("ê", "e").replace("á", "a").replace("ç", "c")
            user, created = User.objects.get_or_create(email=email, defaults={"first_name": first, "last_name": last,
                                                                              "phone": f"+258 84 {1000000 + i * 7919}"})
            if not created:
                continue
            user.set_password(pwd)
            user.save()
            for d in range(30):
                if rnd.random() < 0.45 - i * 0.02:
                    km = Decimal(str(round(rnd.uniform(3, 14), 2)))
                    pace = rnd.randint(290, 420)
                    activity.log_run(user, date=today - timedelta(days=d), distance_km=km,
                                     duration=timedelta(seconds=int(float(km) * pace)))
        self.stdout.write(self.style.SUCCESS(f"Dados demo criados. Membros demo com palavra-passe '{pwd}'."))
