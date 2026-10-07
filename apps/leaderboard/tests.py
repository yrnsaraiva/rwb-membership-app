from datetime import timedelta
from decimal import Decimal

from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.activity import services as activity

from .services import get_leaderboard


class LeaderboardTests(TestCase):
    def setUp(self):
        cache.clear()
        self.a = User.objects.create_user("a@x.mz", "x", first_name="Ana")
        self.b = User.objects.create_user("b@x.mz", "x", first_name="Bruno")
        self.c = User.objects.create_user("c@x.mz", "x", first_name="Carla", show_on_leaderboard=False)
        today = timezone.localdate()
        for user, km in ((self.a, "10"), (self.b, "5"), (self.c, "50")):
            activity.log_run(user, date=today, distance_km=Decimal(km), duration=timedelta(minutes=int(float(km) * 6)))

    def test_order_and_privacy(self):
        rows = get_leaderboard("mes", "pontos")
        self.assertEqual([r["name"] for r in rows], ["Ana", "Bruno"])
        self.assertEqual(rows[0]["rank"], 1)
        self.assertEqual(rows[0]["score"], 100)

    def test_km_metric(self):
        rows = get_leaderboard("geral", "km")
        self.assertEqual(rows[0]["score"], Decimal("10"))

    def test_cache_invalidated_on_new_run(self):
        get_leaderboard("mes", "pontos")
        activity.log_run(self.b, date=timezone.localdate(), distance_km=Decimal("20"), duration=timedelta(minutes=120))
        rows = get_leaderboard("mes", "pontos")
        self.assertEqual(rows[0]["name"], "Bruno")

    def test_ties_share_rank(self):
        activity.log_run(self.b, date=timezone.localdate(), distance_km=Decimal("5"), duration=timedelta(minutes=30))
        rows = get_leaderboard("mes", "pontos")
        self.assertEqual([r["rank"] for r in rows], [1, 1])

    def test_view(self):
        resp = self.client.get(reverse("leaderboard:index"))
        self.assertContains(resp, "Ana")
        self.assertNotContains(resp, "Carla")
        self.assertEqual(self.client.get(reverse("leaderboard:index") + "?periodo=geral&metrica=km").status_code, 200)
