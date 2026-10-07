import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Plan",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=60, verbose_name="nome")),
                ("slug", models.SlugField(unique=True)),
                ("price_mzn", models.DecimalField(decimal_places=2, max_digits=10, verbose_name="preço (MZN)")),
                ("duration_days", models.PositiveIntegerField(default=30, verbose_name="duração (dias)")),
                ("description", models.CharField(blank=True, max_length=200, verbose_name="descrição curta")),
                ("benefits", models.TextField(blank=True, help_text="Um benefício por linha.", verbose_name="benefícios")),
                ("is_active", models.BooleanField(default=True, verbose_name="activo")),
                ("is_featured", models.BooleanField(default=False, verbose_name="destacado")),
                ("order", models.PositiveSmallIntegerField(default=0, verbose_name="ordem")),
            ],
            options={
                "verbose_name": "plano",
                "verbose_name_plural": "planos",
                "ordering": ["order", "price_mzn"],
            },
        ),
        migrations.CreateModel(
            name="Subscription",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("status", models.CharField(choices=[("pending", "Pendente"), ("active", "Activa"), ("cancelled", "Cancelada"), ("expired", "Expirada")], default="pending", max_length=12, verbose_name="estado")),
                ("payment_method", models.CharField(choices=[("manual", "Manual (confirmado pelo clube)"), ("cash", "Numerário"), ("bank", "Transferência bancária"), ("mpesa_manual", "M-Pesa (confirmação manual)"), ("mpesa_c2b", "M-Pesa C2B (automático — fase 2)")], default="manual", max_length=20, verbose_name="método de pagamento")),
                ("payment_reference", models.CharField(blank=True, max_length=80, verbose_name="referência do pagamento")),
                ("amount_mzn", models.DecimalField(decimal_places=2, max_digits=10, verbose_name="valor (MZN)")),
                ("starts_at", models.DateTimeField(blank=True, null=True, verbose_name="início")),
                ("ends_at", models.DateTimeField(blank=True, null=True, verbose_name="fim")),
                ("notes", models.TextField(blank=True, verbose_name="notas internas")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="pedido em")),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("activated_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to=settings.AUTH_USER_MODEL, verbose_name="activada por")),
                ("plan", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="subscriptions", to="billing.plan", verbose_name="plano")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="subscriptions", to=settings.AUTH_USER_MODEL, verbose_name="membro")),
            ],
            options={
                "verbose_name": "subscrição",
                "verbose_name_plural": "subscrições",
                "ordering": ["-created_at"],
            },
        ),
    ]
