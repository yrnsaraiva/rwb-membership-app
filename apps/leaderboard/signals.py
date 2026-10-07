from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from apps.activity.models import PointTransaction, Run

from .services import bump_version


@receiver([post_save, post_delete], sender=PointTransaction)
@receiver([post_save, post_delete], sender=Run)
def invalidate_leaderboard(sender, **kwargs):
    bump_version()
