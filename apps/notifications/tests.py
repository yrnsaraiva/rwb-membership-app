from datetime import timedelta
from decimal import Decimal
from io import StringIO
from unittest import mock

from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.accounts.models import User
from apps.events import services as event_services
from apps.events.models import Event
from apps.shop import services as shop_services
from apps.shop.models import Order, Product, ProductVariant

from . import services
from .management.commands.generate_vapid_keys import generate_vapid_keys
from .models import PushSubscription

KEYS = {"VAPID_PUBLIC_KEY": "pub", "VAPID_PRIVATE_KEY": "priv"}
WEBPUSH = "pywebpush.webpush"


def subscribe(user, n=1):
    return PushSubscription.objects.create(user=user, endpoint=f"https://push.example/{user.pk}-{n}", p256dh="p", auth="a")


class PushServiceTests(TestCase):
    def setUp(self):
        self.ana = User.objects.create_user("ana@x.mz", "Corrida!2026x", first_name="Ana")
        self.rui = User.objects.create_user("rui@x.mz", "Corrida!2026x", first_name="Rui")

    def test_disabled_without_keys_sends_nothing(self):
        subscribe(self.ana)
        with mock.patch(WEBPUSH) as wp:
            self.assertEqual(services.notify(self.ana, "t", "b"), 0)
            self.assertEqual(services.broadcast("t", "b"), 0)
        wp.assert_not_called()

    @override_settings(**KEYS)
    def test_notify_only_targets_that_member_on_commit(self):
        subscribe(self.ana)
        subscribe(self.rui)
        with mock.patch(WEBPUSH) as wp, self.captureOnCommitCallbacks(execute=True):
            self.assertEqual(services.notify(self.ana, "Olá", "Corpo", url="/x/"), 1)
        self.assertEqual(wp.call_count, 1)
        kwargs = wp.call_args.kwargs
        self.assertEqual(kwargs["subscription_info"]["endpoint"], f"https://push.example/{self.ana.pk}-1")
        self.assertIn('"url": "/x/"', kwargs["data"])
        self.assertEqual(kwargs["vapid_private_key"], "priv")

    @override_settings(**KEYS)
    def test_dead_subscription_is_removed_and_flaky_one_counts_failures(self):
        from pywebpush import WebPushException

        dead, flaky = subscribe(self.ana, 1), subscribe(self.ana, 2)

        def fake(subscription_info, **kw):
            code = 410 if subscription_info["endpoint"] == dead.endpoint else 500
            raise WebPushException("boom", response=mock.Mock(status_code=code))

        with mock.patch(WEBPUSH, side_effect=fake), self.captureOnCommitCallbacks(execute=True):
            services.notify(self.ana, "t", "b")
        self.assertFalse(PushSubscription.objects.filter(pk=dead.pk).exists())
        flaky.refresh_from_db()
        self.assertEqual(flaky.failures, 1)

    @override_settings(**KEYS)
    def test_success_resets_failures(self):
        sub = subscribe(self.ana)
        PushSubscription.objects.filter(pk=sub.pk).update(failures=3)
        with mock.patch(WEBPUSH), self.captureOnCommitCallbacks(execute=True):
            services.notify(self.ana, "t", "b")
        sub.refresh_from_db()
        self.assertEqual((sub.failures, bool(sub.last_success_at)), (0, True))

    def test_generated_keys_are_valid_vapid(self):
        from py_vapid import Vapid

        public, private = generate_vapid_keys()
        self.assertTrue(public and private)
        vapid = Vapid.from_string(private)
        self.assertTrue(vapid.sign({"sub": "mailto:a@b.mz", "aud": "https://push.example"}))


@override_settings(**KEYS)
class PushTriggerTests(TestCase):
    def setUp(self):
        self.ana = User.objects.create_user("ana@x.mz", "Corrida!2026x", first_name="Ana")
        self.rui = User.objects.create_user("rui@x.mz", "Corrida!2026x", first_name="Rui")
        subscribe(self.ana)
        subscribe(self.rui)

    def test_new_event_is_announced_once_to_everyone(self):
        with mock.patch(WEBPUSH) as wp, self.captureOnCommitCallbacks(execute=True):
            event = Event.objects.create(title="Corrida do Faról", location="Marginal",
                                         starts_at=timezone.now() + timedelta(days=3))
        self.assertEqual(wp.call_count, 2)
        self.assertIn("Novo evento", wp.call_args.kwargs["data"])
        with mock.patch(WEBPUSH) as wp, self.captureOnCommitCallbacks(execute=True):
            event.title = "Outro título"
            event.save()
        wp.assert_not_called()

    def test_draft_is_announced_only_when_published(self):
        with mock.patch(WEBPUSH) as wp, self.captureOnCommitCallbacks(execute=True):
            event = Event.objects.create(title="Rascunho", location="X", starts_at=timezone.now() + timedelta(days=3),
                                         is_published=False)
        wp.assert_not_called()
        with mock.patch(WEBPUSH) as wp, self.captureOnCommitCallbacks(execute=True):
            event.is_published = True
            event.save()
        self.assertEqual(wp.call_count, 2)

    def test_order_ready_notifies_only_the_buyer(self):
        product = Product.objects.create(name="T-shirt", price_mzn=Decimal("1000"))
        variant = ProductVariant.objects.create(product=product, name="M", stock=3)
        order = Order.objects.create(user=self.ana, customer_name="Ana", phone="1", status=Order.Status.PAID,
                                     total_mzn=1000, subtotal_mzn=1000)
        order.items.create(variant=variant, product_name="T-shirt", variant_name="M", unit_price_mzn=1000,
                           list_price_mzn=1000, quantity=1)
        with mock.patch(WEBPUSH) as wp, self.captureOnCommitCallbacks(execute=True):
            shop_services.advance(order, Order.Status.READY)
        self.assertEqual(wp.call_count, 1)
        self.assertEqual(wp.call_args.kwargs["subscription_info"]["endpoint"], f"https://push.example/{self.ana.pk}-1")

    def test_event_reminders_sent_once(self):
        event = Event.objects.create(title="Treino", location="Marginal", starts_at=timezone.now() + timedelta(hours=5))
        far = Event.objects.create(title="Longe", location="X", starts_at=timezone.now() + timedelta(days=5))
        event_services.register(self.ana, event)
        event_services.register(self.ana, far)
        with mock.patch(WEBPUSH) as wp:
            with self.captureOnCommitCallbacks(execute=True):
                call_command("send_event_reminders", stdout=StringIO())
            self.assertEqual(wp.call_count, 1)
            self.assertIn("Lembrete: Treino", wp.call_args.kwargs["data"])
            with self.captureOnCommitCallbacks(execute=True):
                call_command("send_event_reminders", stdout=StringIO())
            self.assertEqual(wp.call_count, 1)  # não repete


class PushCardTests(TestCase):
    def test_profile_shows_push_card_only_when_vapid_configured(self):
        user = User.objects.create_user("p@x.mz", "Corrida!2026x", first_name="P")
        self.client.force_login(user)
        self.assertNotContains(self.client.get("/conta/perfil/"), "data-push")
        with override_settings(VAPID_PUBLIC_KEY="BPUBLICKEY"):
            self.assertContains(self.client.get("/conta/perfil/"), 'data-vapid-key="BPUBLICKEY"')
