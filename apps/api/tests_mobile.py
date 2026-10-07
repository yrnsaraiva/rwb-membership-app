"""Endpoints para a app móvel: conta, staff, loja, premium e dispositivos."""
import re
from datetime import timedelta
from decimal import Decimal

from django.core import mail
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.activity.models import PointTransaction
from apps.billing.models import Plan, Subscription
from apps.events import services as event_services
from apps.events.models import Event, Registration
from apps.notifications.models import PushSubscription
from apps.shop.models import Order, Product, ProductVariant

PASSWORD = "Corrida!2026x"


class Base(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.user = User.objects.create_user("ana@x.mz", PASSWORD, first_name="Ana", last_name="S")
        self.staff = User.objects.create_user("staff@x.mz", PASSWORD, first_name="Rui", is_staff=True)


class AccountApiTests(Base):
    payload = {"first_name": "Bia", "last_name": "C", "email": "Bia@X.mz", "phone": "+258840000000",
               "password": PASSWORD, "accept_terms": True}

    def test_register_returns_token_and_sends_welcome(self):
        resp = self.client.post("/api/v1/auth/register/", self.payload, format="json")
        self.assertEqual(resp.status_code, 201, resp.content)
        self.assertTrue(resp.data["token"])
        self.assertEqual(resp.data["member"]["email"], "bia@x.mz")
        self.assertEqual(len(mail.outbox), 1)
        self.client.credentials(HTTP_AUTHORIZATION="Token " + resp.data["token"])
        self.assertEqual(self.client.get("/api/v1/me/").status_code, 200)

    def test_register_validation(self):
        bad = {**self.payload, "email": "ana@x.mz", "password": "123", "accept_terms": False}
        resp = self.client.post("/api/v1/auth/register/", bad, format="json")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("password", resp.data)
        self.assertIn("accept_terms", resp.data)
        resp = self.client.post("/api/v1/auth/register/", {**self.payload, "email": "ANA@x.mz"}, format="json")
        self.assertIn("email", resp.data)  # duplicado, sem distinguir maiúsculas

    def test_password_reset_flow(self):
        # conta desconhecida: mesma resposta, sem email
        resp = self.client.post("/api/v1/auth/password-reset/", {"email": "ninguem@x.mz"}, format="json")
        self.assertEqual(resp.status_code, 204)
        self.assertEqual(len(mail.outbox), 0)
        self.client.post("/api/v1/auth/password-reset/", {"email": "ana@x.mz"}, format="json")
        self.assertEqual(len(mail.outbox), 1)
        uid, token = re.search(r"/recuperar/([^/\s]+)/([^/\s]+)/", mail.outbox[0].body).groups()
        resp = self.client.post("/api/v1/auth/password-reset/confirm/",
                                {"uid": uid, "token": token, "password": "NovaSenha!2027"}, format="json")
        self.assertEqual(resp.status_code, 204, resp.content)
        self.assertTrue(User.objects.get(pk=self.user.pk).check_password("NovaSenha!2027"))
        again = self.client.post("/api/v1/auth/password-reset/confirm/",
                                 {"uid": uid, "token": token, "password": "Outra!2027xyz"}, format="json")
        self.assertEqual(again.status_code, 400)  # o token só serve uma vez

    def test_change_password_rotates_token(self):
        old = self.client.post("/api/v1/auth/token/", {"username": "ana@x.mz", "password": PASSWORD}, format="json").data["token"]
        self.client.credentials(HTTP_AUTHORIZATION="Token " + old)
        resp = self.client.post("/api/v1/me/password/", {"old_password": "errada", "new_password": "NovaSenha!2027"}, format="json")
        self.assertEqual(resp.status_code, 400)
        resp = self.client.post("/api/v1/me/password/", {"old_password": PASSWORD, "new_password": "NovaSenha!2027"}, format="json")
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertNotEqual(resp.data["token"], old)
        self.assertEqual(self.client.get("/api/v1/me/").status_code, 401)
        self.client.credentials(HTTP_AUTHORIZATION="Token " + resp.data["token"])
        self.assertEqual(self.client.get("/api/v1/me/").status_code, 200)

    def test_push_subscription_upsert_and_delete(self):
        self.client.force_authenticate(self.user)
        body = {"endpoint": "https://push.example/abc", "keys": {"p256dh": "k1", "auth": "a1"}, "expirationTime": None}
        self.assertEqual(self.client.post("/api/v1/me/push/", body, format="json").status_code, 201)
        self.assertEqual(self.client.post("/api/v1/me/push/", body, format="json").status_code, 200)
        self.assertEqual(PushSubscription.objects.count(), 1)
        # o mesmo telemóvel passa para outro membro: a subscrição deixa de pertencer ao anterior
        self.client.force_authenticate(self.staff)
        self.client.post("/api/v1/me/push/", body, format="json")
        self.assertEqual(PushSubscription.objects.get().user, self.staff)
        self.client.force_authenticate(self.user)
        self.client.delete("/api/v1/me/push/", {"endpoint": body["endpoint"]}, format="json")
        self.assertEqual(PushSubscription.objects.count(), 1)  # não apaga a de outro membro
        self.client.force_authenticate(self.staff)
        self.assertEqual(self.client.delete("/api/v1/me/push/", {"endpoint": body["endpoint"]}, format="json").status_code, 204)
        self.assertEqual(PushSubscription.objects.count(), 0)
        self.assertEqual(self.client.post("/api/v1/me/push/", {"endpoint": "nao-e-url", "keys": {}}, format="json").status_code, 400)

    @override_settings(VAPID_PUBLIC_KEY="pub", VAPID_PRIVATE_KEY="priv")
    def test_push_config_is_public(self):
        data = self.client.get("/api/v1/push/config/").data
        self.assertEqual(data, {"enabled": True, "public_key": "pub"})


class StaffApiTests(Base):
    def setUp(self):
        super().setUp()
        self.event = Event.objects.create(title="Treino", location="Marginal", starts_at=timezone.now() + timedelta(hours=2))
        self.reg = event_services.register(self.user, self.event)

    def test_requires_staff(self):
        url = f"/api/v1/staff/cards/{self.user.card_token}/"
        self.assertEqual(self.client.get(url).status_code, 401)
        self.client.force_authenticate(self.user)
        self.assertEqual(self.client.get(url).status_code, 403)

    def test_scan_and_checkin_awards_points_once(self):
        self.client.force_authenticate(self.staff)
        card = self.client.get(f"/api/v1/staff/cards/{self.user.card_token}/")
        self.assertEqual(card.status_code, 200)
        self.assertEqual(card.data["member"]["member_number"], self.user.member_number)
        self.assertEqual(card.data["registrations"][0]["id"], self.reg.pk)
        url = f"/api/v1/staff/registrations/{self.reg.pk}/checkin/"
        self.assertEqual(self.client.post(url).status_code, 200)
        self.assertEqual(self.client.post(url).status_code, 400)  # já marcada
        self.assertEqual(PointTransaction.objects.filter(user=self.user, reason="event_checkin").count(), 1)
        resp = self.client.delete(url)
        self.assertIsNone(resp.data["checked_in_at"])
        self.assertEqual(PointTransaction.objects.filter(user=self.user, reason="event_checkin").count(), 0)

    def test_unknown_card_is_404(self):
        self.client.force_authenticate(self.staff)
        self.assertEqual(self.client.get("/api/v1/staff/cards/6f9f1c0e-0000-4000-8000-000000000000/").status_code, 404)


class ShopApiTests(Base):
    def setUp(self):
        super().setUp()
        self.product = Product.objects.create(name="T-shirt RWB", price_mzn=Decimal("1000"))
        self.m = ProductVariant.objects.create(product=self.product, name="M", stock=3)
        self.event = Event.objects.create(title="Treino", location="Marginal", starts_at=timezone.now() + timedelta(days=2))
        self.order = {"items": [{"variant": self.m.pk, "quantity": 2}], "fulfilment": "event", "pickup_event": self.event.pk,
                      "customer_name": "Ana S", "phone": "+258840000000"}

    def test_catalog_is_public_and_shows_member_price(self):
        resp = self.client.get("/api/v1/shop/products/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["results"][0]["variants"][0]["unit_price_mzn"], "1000.00")
        sub = Subscription.objects.create(user=self.user, plan=Plan.objects.create(name="P", slug="p", price_mzn=100),
                                          amount_mzn=100)
        sub.activate()
        self.client.force_authenticate(self.user)
        resp = self.client.get(f"/api/v1/shop/products/{self.product.slug}/")
        self.assertEqual(resp.data["variants"][0]["unit_price_mzn"], "900.00")  # 10% premium

    def test_config_is_public(self):
        resp = self.client.get("/api/v1/shop/config/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["pickup_events"][0]["slug"], self.event.slug)

    def test_place_and_cancel_order_reserves_and_restores_stock(self):
        self.assertEqual(self.client.post("/api/v1/shop/orders/", self.order, format="json").status_code, 401)
        self.client.force_authenticate(self.user)
        resp = self.client.post("/api/v1/shop/orders/", self.order, format="json")
        self.assertEqual(resp.status_code, 201, resp.content)
        self.assertEqual(resp.data["total_mzn"], "2000.00")
        self.m.refresh_from_db()
        self.assertEqual(self.m.stock, 1)
        resp = self.client.post(f"/api/v1/shop/orders/{resp.data['id']}/cancel/")
        self.assertEqual(resp.status_code, 200)
        self.m.refresh_from_db()
        self.assertEqual(self.m.stock, 3)

    def test_validation_and_stock_errors(self):
        self.client.force_authenticate(self.user)
        resp = self.client.post("/api/v1/shop/orders/", {**self.order, "fulfilment": "delivery", "pickup_event": None},
                                format="json")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("delivery_address", resp.data)
        resp = self.client.post("/api/v1/shop/orders/", {**self.order, "items": [{"variant": self.m.pk, "quantity": 5}]},
                                format="json")
        self.assertEqual(resp.status_code, 400)  # só há 3
        self.assertIn("detail", resp.data)
        self.assertEqual(Order.objects.count(), 0)

    def test_cannot_see_or_cancel_others_orders(self):
        self.client.force_authenticate(self.user)
        oid = self.client.post("/api/v1/shop/orders/", self.order, format="json").data["id"]
        self.client.force_authenticate(self.staff)
        self.assertEqual(self.client.get(f"/api/v1/shop/orders/{oid}/").status_code, 404)
        self.assertEqual(self.client.post(f"/api/v1/shop/orders/{oid}/cancel/").status_code, 404)


class PremiumApiTests(Base):
    def setUp(self):
        super().setUp()
        self.plan = Plan.objects.create(name="Mensal", slug="mensal", price_mzn=500, benefits="A\nB")

    def test_plans_public(self):
        resp = self.client.get("/api/v1/premium/plans/")
        self.assertEqual(resp.data[0]["benefits"], ["A", "B"])

    def test_request_and_cancel(self):
        self.client.force_authenticate(self.user)
        self.assertFalse(self.client.get("/api/v1/premium/").data["is_premium"])
        resp = self.client.post("/api/v1/premium/", {"plan": "mensal"}, format="json")
        self.assertEqual(resp.status_code, 201, resp.content)
        self.assertEqual(self.client.post("/api/v1/premium/", {"plan": "mensal"}, format="json").status_code, 400)  # já pendente
        self.assertEqual(self.client.get("/api/v1/premium/").data["pending"]["plan"], "mensal")
        self.assertEqual(self.client.post(f"/api/v1/premium/requests/{resp.data['id']}/cancel/").status_code, 204)
        self.assertIsNone(self.client.get("/api/v1/premium/").data["pending"])

    def test_active_subscription_reported(self):
        Subscription.objects.create(user=self.user, plan=self.plan, amount_mzn=500).activate()
        self.client.force_authenticate(self.user)
        data = self.client.get("/api/v1/premium/").data
        self.assertTrue(data["is_premium"])
        self.assertGreater(data["current"]["days_left"], 25)
        self.assertEqual(Registration.objects.count(), 0)
