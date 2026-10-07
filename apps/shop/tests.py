from datetime import timedelta
from decimal import Decimal

from django.core import mail
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.billing.models import Plan, Subscription
from apps.events.models import Event

from . import services
from .models import Order, Product, ProductVariant


@override_settings(RWB_PREMIUM_SHOP_DISCOUNT=10, RWB_SHOP_DELIVERY_FEE=150, RWB_SHOP_MPESA_NUMBER="84 000 0000")
class ShopTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("a@x.mz", "x", first_name="Ana", last_name="Sitoe", phone="+258840000000")
        self.staff = User.objects.create_user("s@x.mz", "x", first_name="Staff", is_staff=True)
        self.product = Product.objects.create(name="T-shirt técnica", price_mzn=Decimal("1200"))
        self.m = ProductVariant.objects.create(product=self.product, name="M", stock=2)
        self.xl = ProductVariant.objects.create(product=self.product, name="XL", stock=0)
        self.event = Event.objects.create(title="Treino", location="Marginal", starts_at=timezone.now() + timedelta(days=2))

    def add(self, variant, qty=1):
        return self.client.post(reverse("shop:cart_add", args=[self.product.slug]), {"variant": variant.pk, "quantity": qty})

    def checkout(self, **kw):
        data = {"fulfilment": "event", "pickup_event": self.event.pk, "customer_name": "Ana Sitoe", "phone": "+258840000000"}
        data.update(kw)
        with self.captureOnCommitCallbacks(execute=True):
            return self.client.post(reverse("shop:checkout"), data)

    def test_pages_render(self):
        self.assertContains(self.client.get(reverse("shop:list")), "T-shirt técnica")
        resp = self.client.get(self.product.get_absolute_url())
        self.assertContains(resp, "Adicionar ao carrinho")
        self.assertContains(resp, "1 080 MZN")  # preço premium (10%)
        self.assertEqual(self.client.get(reverse("shop:cart")).status_code, 200)

    def test_cannot_add_out_of_stock_or_more_than_stock(self):
        self.add(self.xl)
        self.assertEqual(self.client.session.get("rwb_cart"), None)
        self.add(self.m, 3)
        self.assertIsNone(self.client.session.get("rwb_cart"))

    def test_guest_cart_then_checkout_requires_login(self):
        self.add(self.m, 2)
        self.assertEqual(self.client.session["rwb_cart"], {str(self.m.pk): 2})
        resp = self.client.get(reverse("shop:checkout"))
        self.assertEqual(resp.status_code, 302)
        self.assertIn(reverse("accounts:login"), resp["Location"])

    def test_full_order_flow(self):
        self.client.force_login(self.user)
        self.add(self.m, 2)
        resp = self.checkout()
        order = Order.objects.get()
        self.assertRedirects(resp, order.get_absolute_url())
        self.assertEqual(order.total_mzn, Decimal("2400"))
        self.assertEqual(order.pickup_event, self.event)
        self.m.refresh_from_db()
        self.assertEqual(self.m.stock, 0)  # stock reservado
        self.assertEqual(self.client.session["rwb_cart"], {})
        self.assertTrue(any(order.number in m.subject for m in mail.outbox))
        self.assertContains(self.client.get(order.get_absolute_url()), "84 000 0000")

        # staff marca como pago → pronto → entregue
        self.client.force_login(self.staff)
        self.client.post(reverse("panel:order_action", args=[order.pk]), {"action": "paid", "payment_reference": "MP123"})
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.PAID)
        self.assertEqual(order.payment_reference, "MP123")
        self.client.post(reverse("panel:order_action", args=[order.pk]), {"action": "ready"})
        self.client.post(reverse("panel:order_action", args=[order.pk]), {"action": "completed"})
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.COMPLETED)
        self.assertEqual(self.client.get(reverse("panel:orders") + "?estado=todas").status_code, 200)

    def test_delivery_fee_and_address_required(self):
        self.client.force_login(self.user)
        self.add(self.m)
        resp = self.checkout(fulfilment="delivery", pickup_event="")
        self.assertContains(resp, "Indica a morada")
        self.checkout(fulfilment="delivery", pickup_event="", delivery_address="Av. Julius Nyerere 100")
        order = Order.objects.get()
        self.assertEqual(order.delivery_fee_mzn, Decimal("150"))
        self.assertEqual(order.total_mzn, Decimal("1350"))
        self.assertIsNone(order.pickup_event)

    def test_premium_discount(self):
        plan = Plan.objects.create(name="Mensal", slug="mensal", price_mzn=500, duration_days=30)
        Subscription.objects.create(user=self.user, plan=plan, amount_mzn=500).activate()
        self.client.force_login(self.user)
        self.add(self.m)
        self.checkout()
        order = Order.objects.get()
        self.assertEqual(order.subtotal_mzn, Decimal("1200"))
        self.assertEqual(order.discount_mzn, Decimal("120"))
        self.assertEqual(order.total_mzn, Decimal("1080"))

    def test_stock_race_detected_at_checkout(self):
        self.client.force_login(self.user)
        self.add(self.m, 2)
        ProductVariant.objects.filter(pk=self.m.pk).update(stock=1)  # alguém comprou entretanto
        resp = self.checkout()
        self.assertRedirects(resp, reverse("shop:cart"))
        self.assertEqual(Order.objects.count(), 0)

    def test_member_cancel_restores_stock(self):
        self.client.force_login(self.user)
        self.add(self.m, 2)
        self.checkout()
        order = Order.objects.get()
        self.client.post(reverse("shop:order_cancel", args=[order.pk]))
        order.refresh_from_db()
        self.m.refresh_from_db()
        self.assertEqual(order.status, Order.Status.CANCELLED)
        self.assertEqual(self.m.stock, 2)

    def test_cannot_see_other_members_order(self):
        self.client.force_login(self.user)
        self.add(self.m)
        self.checkout()
        order = Order.objects.get()
        other = User.objects.create_user("b@x.mz", "x")
        self.client.force_login(other)
        self.assertEqual(self.client.get(order.get_absolute_url()).status_code, 404)

    def test_stale_orders_cancelled(self):
        self.client.force_login(self.user)
        self.add(self.m, 1)
        self.checkout()
        Order.objects.update(created_at=timezone.now() - timedelta(days=5))
        call_command("cancel_stale_orders", "--days", "3", verbosity=0)
        self.assertEqual(Order.objects.get().status, Order.Status.CANCELLED)
        self.m.refresh_from_db()
        self.assertEqual(self.m.stock, 2)

    def test_invalid_transitions(self):
        order = Order.objects.create(user=self.user, customer_name="A", phone="1")
        with self.assertRaises(services.ShopError):
            services.advance(order, Order.Status.COMPLETED)

    def test_cart_update_and_remove(self):
        self.add(self.m, 1)
        self.client.post(reverse("shop:cart"), {f"qty_{self.m.pk}": "2"})
        self.assertEqual(self.client.session["rwb_cart"][str(self.m.pk)], 2)
        self.client.post(reverse("shop:cart"), {"remove": str(self.m.pk)})
        self.assertEqual(self.client.session["rwb_cart"], {})


class ThemeAndBrandTests(TestCase):
    def test_theme_toggle_and_logo_present(self):
        resp = self.client.get("/")
        self.assertContains(resp, "data-theme-toggle")
        self.assertContains(resp, "wordmark-yellow.png")
        self.assertContains(resp, "wordmark-ink.png")
