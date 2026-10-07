from decimal import Decimal

import django.core.validators
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("events", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="Run",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("date", models.DateField(verbose_name="data")),
                ("distance_km", models.DecimalField(decimal_places=2, max_digits=6, validators=[django.core.validators.MinValueValidator(Decimal("0.1"))], verbose_name="distância (km)")),
                ("duration", models.DurationField(verbose_name="duração")),
                ("pace_sec_per_km", models.PositiveIntegerField(blank=True, db_index=True, editable=False, null=True, verbose_name="ritmo (s/km)")),
                ("title", models.CharField(blank=True, max_length=80, verbose_name="título")),
                ("notes", models.TextField(blank=True, max_length=500, verbose_name="notas")),
                ("is_valid", models.BooleanField(default=True, help_text="Desmarcar para invalidar (moderação) — remove os pontos.", verbose_name="válida")),
                ("moderation_note", models.CharField(blank=True, max_length=200, verbose_name="nota de moderação")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("event", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="runs", to="events.event", verbose_name="evento")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="runs", to=settings.AUTH_USER_MODEL, verbose_name="membro")),
            ],
            options={
                "verbose_name": "corrida",
                "verbose_name_plural": "corridas",
                "ordering": ["-date", "-created_at"],
                "indexes": [models.Index(fields=["user", "date"], name="run_user_date_idx")],
            },
        ),
        migrations.CreateModel(
            name="PointTransaction",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("amount", models.IntegerField(verbose_name="pontos")),
                ("reason", models.CharField(choices=[("run", "Corrida"), ("streak_bonus", "Bónus de streak"), ("event_checkin", "Presença em evento"), ("adjustment", "Ajuste manual")], max_length=20, verbose_name="motivo")),
                ("description", models.CharField(blank=True, max_length=160, verbose_name="descrição")),
                ("reference_date", models.DateField(blank=True, null=True, verbose_name="data de referência")),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True, verbose_name="data")),
                ("registration", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="point_transactions", to="events.registration")),
                ("run", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="point_transactions", to="activity.run")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="point_transactions", to=settings.AUTH_USER_MODEL, verbose_name="membro")),
            ],
            options={
                "verbose_name": "movimento de pontos",
                "verbose_name_plural": "movimentos de pontos",
                "ordering": ["-created_at"],
                "constraints": [models.UniqueConstraint(condition=models.Q(("reason", "streak_bonus")), fields=("user", "reference_date"), name="one_streak_bonus_per_day")],
            },
        ),
    ]
