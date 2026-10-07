from django.apps import AppConfig


class LeaderboardConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.leaderboard"
    label = "leaderboard"
    verbose_name = "Ranking"

    def ready(self):
        from . import signals  # noqa: F401
