import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

import apps.events.models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Event",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title", models.CharField(max_length=140, verbose_name="título")),
                ("slug", models.SlugField(blank=True, max_length=160, unique=True)),
                ("kind", models.CharField(choices=[("group_run", "Corrida de grupo"), ("race", "Prova"), ("training", "Treino"), ("social", "Social")], default="group_run", max_length=20, verbose_name="tipo")),
                ("summary", models.CharField(blank=True, max_length=200, verbose_name="resumo")),
                ("description", models.TextField(blank=True, verbose_name="descrição")),
                ("location", models.CharField(max_length=160, verbose_name="local")),
                ("meeting_point", models.CharField(blank=True, max_length=160, verbose_name="ponto de encontro")),
                ("map_url", models.URLField(blank=True, verbose_name="link do mapa")),
                ("starts_at", models.DateTimeField(verbose_name="início")),
                ("ends_at", models.DateTimeField(blank=True, null=True, verbose_name="fim")),
                ("distances", models.CharField(blank=True, help_text="Ex.: 5 km · 10 km", max_length=80, verbose_name="distâncias")),
                ("capacity", models.PositiveIntegerField(blank=True, help_text="Vazio = sem limite", null=True, verbose_name="vagas")),
                ("registration_opens_at", models.DateTimeField(blank=True, null=True, verbose_name="abertura das inscrições")),
                ("registration_closes_at", models.DateTimeField(blank=True, null=True, verbose_name="fecho das inscrições")),
                ("price_mzn", models.DecimalField(decimal_places=2, default=0, help_text="Informativo no MVP — pagamento feito fora da app.", max_digits=10, verbose_name="preço (MZN)")),
                ("members_only", models.BooleanField(default=False, verbose_name="só membros premium")),
                ("checkin_points", models.PositiveIntegerField(blank=True, help_text="Vazio = valor por defeito do clube", null=True, verbose_name="pontos por presença")),
                ("cover", models.ImageField(blank=True, upload_to=apps.events.models.cover_upload_to, verbose_name="imagem de capa")),
                ("is_published", models.BooleanField(default=True, verbose_name="publicado")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to=settings.AUTH_USER_MODEL, verbose_name="criado por")),
            ],
            options={
                "verbose_name": "evento",
                "verbose_name_plural": "eventos",
                "ordering": ["starts_at"],
                "indexes": [models.Index(fields=["is_published", "starts_at"], name="event_published_start_idx")],
            },
        ),
        migrations.CreateModel(
            name="Registration",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("status", models.CharField(choices=[("confirmed", "Confirmada"), ("cancelled", "Cancelada")], default="confirmed", max_length=12, verbose_name="estado")),
                ("distance", models.CharField(blank=True, max_length=20, verbose_name="distância escolhida")),
                ("checked_in_at", models.DateTimeField(blank=True, null=True, verbose_name="presença registada em")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="inscrito em")),
                ("cancelled_at", models.DateTimeField(blank=True, null=True, verbose_name="cancelado em")),
                ("event", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="registrations", to="events.event", verbose_name="evento")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="registrations", to=settings.AUTH_USER_MODEL, verbose_name="membro")),
            ],
            options={
                "verbose_name": "inscrição",
                "verbose_name_plural": "inscrições",
                "ordering": ["created_at"],
                "constraints": [models.UniqueConstraint(fields=("event", "user"), name="unique_registration_per_event")],
            },
        ),
    ]
