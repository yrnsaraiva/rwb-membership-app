import uuid

import django.contrib.auth.models
import django.utils.timezone
from django.db import migrations, models

import apps.accounts.models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("auth", "0012_alter_user_first_name_max_length"),
    ]

    operations = [
        migrations.CreateModel(
            name="User",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("password", models.CharField(max_length=128, verbose_name="password")),
                ("last_login", models.DateTimeField(blank=True, null=True, verbose_name="last login")),
                ("is_superuser", models.BooleanField(default=False, help_text="Designates that this user has all permissions without explicitly assigning them.", verbose_name="superuser status")),
                ("first_name", models.CharField(blank=True, max_length=150, verbose_name="first name")),
                ("last_name", models.CharField(blank=True, max_length=150, verbose_name="last name")),
                ("is_staff", models.BooleanField(default=False, help_text="Designates whether the user can log into this admin site.", verbose_name="staff status")),
                ("is_active", models.BooleanField(default=True, help_text="Designates whether this user should be treated as active. Unselect this instead of deleting accounts.", verbose_name="active")),
                ("date_joined", models.DateTimeField(default=django.utils.timezone.now, verbose_name="date joined")),
                ("email", models.EmailField(max_length=254, unique=True, verbose_name="email")),
                ("member_number", models.CharField(blank=True, editable=False, max_length=20, null=True, unique=True, verbose_name="número de sócio")),
                ("phone", models.CharField(blank=True, max_length=20, verbose_name="telemóvel")),
                ("city", models.CharField(blank=True, default="Maputo", max_length=80, verbose_name="cidade")),
                ("date_of_birth", models.DateField(blank=True, null=True, verbose_name="data de nascimento")),
                ("bio", models.TextField(blank=True, max_length=500, verbose_name="sobre mim")),
                ("avatar", models.ImageField(blank=True, upload_to=apps.accounts.models.avatar_upload_to, verbose_name="fotografia")),
                ("card_token", models.UUIDField(default=uuid.uuid4, editable=False, unique=True, verbose_name="token do cartão")),
                ("show_on_leaderboard", models.BooleanField(default=True, verbose_name="aparecer no ranking")),
                ("groups", models.ManyToManyField(blank=True, help_text="The groups this user belongs to. A user will get all permissions granted to each of their groups.", related_name="user_set", related_query_name="user", to="auth.group", verbose_name="groups")),
                ("user_permissions", models.ManyToManyField(blank=True, help_text="Specific permissions for this user.", related_name="user_set", related_query_name="user", to="auth.permission", verbose_name="user permissions")),
            ],
            options={
                "verbose_name": "membro",
                "verbose_name_plural": "membros",
                "ordering": ["first_name", "last_name"],
            },
            managers=[
                ("objects", apps.accounts.models.UserManager()),
            ],
        ),
    ]
