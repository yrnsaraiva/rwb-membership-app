from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User

from .models import Plan, Subscription


class BillingTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("a@x.mz", "x", first_name="A")
        self.staff = User.objects.create_user("s@x.mz", "x", first_name="S", is_staff=True)
        self.plan = Plan.objects.create(name="Mensal", slug="mensal", price_mzn=Decimal("500"), duration_days=30)

    def test_request_and_manual_activation(self):
        self.client.force_login(self.user)
        self.client.post(reverse("billing:request", args=["mensal"]))
        sub = Subscription.objects.get()
        self.assertEqual(sub.status, Subscription.Status.PENDING)
        self.assertFalse(User.objects.get(pk=self.user.pk).is_premium)

        self.client.force_login(self.staff)
        resp = self.client.post(reverse("panel:subscription_activate", args=[sub.pk]),
                                {"payment_method": "mpesa_manual", "payment_reference": "ABC123"})
        self.assertRedirects(resp, reverse("panel:subscriptions"))
        sub.refresh_from_db()
        self.assertEqual(sub.status, Subscription.Status.ACTIVE)
        self.assertEqual(sub.payment_reference, "ABC123")
        self.assertEqual(sub.activated_by, self.staff)
        self.assertTrue(User.objects.get(pk=self.user.pk).is_premium)

    def test_single_pending_request(self):
        self.client.force_login(self.user)
        self.client.post(reverse("billing:request", args=["mensal"]))
        self.client.post(reverse("billing:request", args=["mensal"]))
        self.assertEqual(Subscription.objects.count(), 1)

    def test_renewal_extends_from_current_end(self):
        first = Subscription.objects.create(user=self.user, plan=self.plan, amount_mzn=500)
        first.activate()
        second = Subscription.objects.create(user=self.user, plan=self.plan, amount_mzn=500)
        second.activate()
        self.assertEqual(second.starts_at, first.ends_at)

    def test_expired_not_premium(self):
        sub = Subscription.objects.create(user=self.user, plan=self.plan, amount_mzn=500, status="active",
                                          starts_at=timezone.now() - timedelta(days=40),
                                          ends_at=timezone.now() - timedelta(days=10))
        self.assertFalse(User.objects.get(pk=self.user.pk).is_premium)
        from django.core.management import call_command
        call_command("expire_subscriptions", verbosity=0)
        sub.refresh_from_db()
        self.assertEqual(sub.status, Subscription.Status.EXPIRED)

    def test_plans_page(self):
        self.assertContains(self.client.get(reverse("billing:plans")), "Mensal")
