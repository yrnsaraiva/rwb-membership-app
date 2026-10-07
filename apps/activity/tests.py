from datetime import timedelta
from decimal import Decimal

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User

from . import services
from .models import PointTransaction, Run


class ActivityServiceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("a@x.mz", "x", first_name="A")
        self.today = timezone.localdate()

    def log(self, days_ago=0, km="5", minutes=30):
        return services.log_run(self.user, date=self.today - timedelta(days=days_ago),
                                distance_km=Decimal(km), duration=timedelta(minutes=minutes))

    def test_pace_and_points(self):
        run = self.log(km="5", minutes=27)
        self.assertEqual(run.pace_seconds, 324)  # 5:24/km
        self.assertEqual(services.format_pace(run.pace_seconds), "5:24")
        self.assertEqual(run.points, 50)

    def test_points_floor(self):
        self.assertEqual(services.points_for_distance(Decimal("5.99")), 59)

    def test_streaks(self):
        for d in (0, 1, 2, 5, 6):
            self.log(days_ago=d)
        self.assertEqual(services.current_streak(self.user), 3)
        self.assertEqual(services.longest_streak(services.run_dates(self.user)), 3)

    def test_streak_alive_if_ran_yesterday(self):
        self.log(days_ago=1)
        self.log(days_ago=2)
        self.assertEqual(services.current_streak(self.user), 2)

    def test_streak_broken(self):
        self.log(days_ago=2)
        self.assertEqual(services.current_streak(self.user), 0)

    @override_settings(RWB_STREAK_BONUS_EVERY=3, RWB_STREAK_BONUS_POINTS=50)
    def test_streak_bonus_once_per_day(self):
        self.log(days_ago=2)
        self.log(days_ago=1)
        self.log(days_ago=0)
        self.log(days_ago=0)  # segunda corrida no mesmo dia não duplica bónus
        bonus = PointTransaction.objects.filter(user=self.user, reason=PointTransaction.Reason.STREAK_BONUS)
        self.assertEqual(bonus.count(), 1)

    @override_settings(RWB_STREAK_BONUS_EVERY=2, RWB_STREAK_BONUS_POINTS=50)
    def test_delete_run_removes_points_and_bonus(self):
        self.log(days_ago=1)
        run = self.log(days_ago=0)
        self.assertTrue(PointTransaction.objects.filter(reason="streak_bonus").exists())
        services.delete_run(run)
        self.assertFalse(PointTransaction.objects.filter(reason="streak_bonus").exists())
        self.assertEqual(Run.objects.count(), 1)

    def test_moderation_toggle(self):
        run = self.log()
        services.set_run_validity(run, False, "GPS errado")
        self.assertEqual(services.member_stats(self.user)["points"], 0)
        services.set_run_validity(run, True)
        self.assertEqual(services.member_stats(self.user)["points"], 50)

    def test_weekly_activity_shape(self):
        self.log(km="7.5")
        week = services.weekly_activity(self.user)
        self.assertEqual(len(week), 7)
        today = [d for d in week if d["is_today"]][0]
        self.assertEqual(today["km"], Decimal("7.5"))
        self.assertEqual(today["height"], 100)

    def test_member_stats(self):
        self.log(km="10", minutes=50)
        stats = services.member_stats(self.user)
        self.assertEqual(stats["total_km"], Decimal("10"))
        self.assertEqual(stats["avg_pace_display"], "5:00")


class RunViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("a@x.mz", "x", first_name="A")
        self.client.force_login(self.user)

    def post_run(self, **kw):
        data = {"date": timezone.localdate().isoformat(), "distance_km": "5", "hours": "0", "minutes": "30", "seconds": "0"}
        data.update(kw)
        return self.client.post(reverse("activity:run_create"), data)

    def test_create_run(self):
        resp = self.post_run()
        self.assertRedirects(resp, reverse("activity:dashboard"))
        self.assertEqual(Run.objects.count(), 1)

    def test_reject_future_date(self):
        resp = self.post_run(date=(timezone.localdate() + timedelta(days=1)).isoformat())
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(Run.objects.count(), 0)

    def test_reject_impossible_pace(self):
        resp = self.post_run(distance_km="10", minutes="10")
        self.assertContains(resp, "Ritmo demasiado rápido")

    def test_reject_zero_duration(self):
        resp = self.post_run(minutes="0")
        self.assertContains(resp, "Indica a duração")

    def test_dashboard_and_history(self):
        self.post_run()
        self.assertContains(self.client.get(reverse("activity:dashboard")), "Últimas corridas")
        self.assertContains(self.client.get(reverse("activity:run_list")), "5,00")
        self.assertEqual(self.client.get(reverse("activity:points")).status_code, 200)

    def test_cannot_delete_other_users_run(self):
        other = User.objects.create_user("b@x.mz", "x")
        run = services.log_run(other, date=timezone.localdate(), distance_km=Decimal("3"), duration=timedelta(minutes=20))
        resp = self.client.post(reverse("activity:run_delete", args=[run.pk]))
        self.assertEqual(resp.status_code, 404)

    def test_dashboard_requires_login(self):
        self.client.logout()
        resp = self.client.get(reverse("activity:dashboard"))
        self.assertEqual(resp.status_code, 302)
