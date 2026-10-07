"""Webhook da ETK. Corpo e cabeçalhos iguais aos de ticketing/webhooks.py (etk-api)."""
import hashlib
import hmac
import json
from datetime import timedelta
from unittest import mock

from django.test import TestCase, override_settings
from django.utils import timezone

from apps.accounts.models import User
from apps.events import tickets
from apps.events.models import Event, Registration, WebhookDelivery

SECRET = "s3cret"
URL = "/webhooks/etk/"


def body_for(event="ticket.paid", **ticket):
    data = {"id": "TCKT1", "eventId": "EVNT1", "event": {"id": "EVNT1", "name": "Corrida"}, "price": {"id": "P", "name": "Geral"},
            "amount": 0.0, "phone": "258841234567", "email": "", "fullName": "Ana", "payment": "paid", "entered": False,
            "qrValue": "TCKT1|0123456789abcdef", "expiresAt": None, "checkoutUrl": "",
            "updatedAt": "2026-10-07T10:00:00Z", **ticket}
    return json.dumps({"event": event, "data": data}, separators=(",", ":")).encode()  # igual à ETK


def sign(body, secret=SECRET):
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


@override_settings(ETK_WEBHOOK_SECRET=SECRET, ETK_ENABLED=True)
class WebhookTests(TestCase):
    def setUp(self):
        self.event = Event.objects.create(title="Corrida", location="X", external_id="EVNT1",
                                          starts_at=timezone.now() + timedelta(days=2))
        self.ana = User.objects.create_user("ana@x.mz", "Corrida!2026x", first_name="Ana", phone="84 123 4567")
        self.n = 0

    def post(self, body, delivery="1", signature=None, **headers):
        return self.client.post(URL, data=body, content_type="application/json",
                                HTTP_X_ETK_SIGNATURE=sign(body) if signature is None else signature,
                                HTTP_X_ETK_DELIVERY_ID=delivery, **headers)

    def test_paid_creates_the_registration_instantly(self):
        resp = self.post(body_for())
        self.assertEqual((resp.status_code, resp.json()["status"]), (200, "ok"))
        reg = Registration.objects.get()
        self.assertEqual((reg.user, reg.status, reg.ticket_payment, reg.external_ticket_id), (self.ana, "confirmed", "paid", "TCKT1"))
        self.assertEqual(reg.ticket_updated_at.isoformat(), "2026-10-07T10:00:00+00:00")

    def test_refund_cancels_it(self):
        self.post(body_for(), delivery="1")
        self.post(body_for("ticket.refunded", payment="refunded", updatedAt="2026-10-07T11:00:00Z"), delivery="2")
        self.assertEqual(Registration.objects.get().status, "cancelled")

    def test_stale_or_out_of_order_delivery_cannot_resurrect_a_refunded_ticket(self):
        self.post(body_for("ticket.refunded", payment="refunded", updatedAt="2026-10-07T11:00:00Z"), delivery="2")
        self.post(body_for(payment="paid", updatedAt="2026-10-07T10:00:00Z"), delivery="1")  # chegou depois, mas é mais antigo
        self.assertEqual(Registration.objects.get().status, "cancelled")

    def test_pending_payment_completing_sends_confirmation_for_app_purchases(self):
        reg = tickets.upsert_registration(json.loads(body_for(payment="pending", updatedAt="2026-10-07T09:00:00Z"))["data"], self.ana,
                                          via_app=True)
        self.assertEqual(reg.status, "pending")
        with self.captureOnCommitCallbacks(execute=True):
            self.post(body_for(updatedAt="2026-10-07T09:30:00Z"))
        from django.core import mail

        self.assertEqual(len(mail.outbox), 1)
        reg.refresh_from_db()
        self.assertEqual((reg.status, bool(reg.ticket_qr)), ("confirmed", True))

    def test_signature_is_required_and_checked(self):
        body = body_for()
        for sig in ("", "deadbeef", sign(body, "outro-segredo"), sign(body).upper()[:-1] + "0"):
            self.assertEqual(self.post(body, signature=sig).status_code, 401, sig)
        tampered = body.replace(b"Ana", b"Eve")
        self.assertEqual(self.post(tampered, signature=sign(body)).status_code, 401)
        self.assertFalse(Registration.objects.exists())
        self.assertEqual(self.post(body, signature=sign(body).upper()).status_code, 200)  # hex em maiúsculas também vale

    @override_settings(ETK_WEBHOOK_SECRET="")
    def test_disabled_without_secret(self):
        body = body_for()
        self.assertEqual(self.post(body, signature=sign(body, "")).status_code, 404)

    def test_get_is_not_allowed_and_csrf_is_not_required(self):
        self.assertEqual(self.client.get(URL).status_code, 405)
        from django.test import Client

        self.assertEqual(Client(enforce_csrf_checks=True).post(URL, data=body_for(), content_type="application/json").status_code, 401)

    def test_duplicate_delivery_is_acknowledged_once(self):
        body = body_for()
        self.assertEqual(self.post(body, delivery="7").json()["status"], "ok")
        self.assertEqual(self.post(body, delivery="7").json()["status"], "duplicate")
        self.assertEqual(WebhookDelivery.objects.count(), 1)

    def test_malformed_payloads_and_unknown_events(self):
        for body in (b"not json", json.dumps({"event": "ticket.paid"}).encode(), json.dumps({"event": "ticket.paid", "data": {}}).encode()):
            self.assertEqual(self.post(body).status_code, 400)
        self.assertEqual(self.post(body_for("invite.created")).json()["status"], "ignored")
        no_header = self.client.post(URL, data=body_for(), content_type="application/json", HTTP_X_ETK_SIGNATURE=sign(body_for()))
        self.assertEqual(no_header.status_code, 400)
        big = b"x" * (256 * 1024 + 1)
        self.assertEqual(self.post(big).status_code, 401)

    def test_non_member_is_acknowledged_without_creating_anything(self):
        resp = self.post(body_for(phone="258827654321"))
        self.assertEqual((resp.status_code, resp.json()["status"]), (200, "ok"))
        self.assertFalse(Registration.objects.exists())

    def test_unknown_event_asks_etk_to_retry_later(self):
        resp = self.post(body_for(eventId="EVNT-NOVO"))
        self.assertEqual(resp.status_code, 503)
        self.assertFalse(WebhookDelivery.objects.exists())  # não fica marcado como tratado

    def test_processing_failure_returns_500_and_is_not_marked_done(self):
        with mock.patch("apps.events.webhooks.tickets.upsert_registration", side_effect=RuntimeError("boom")):
            self.assertEqual(self.post(body_for(), delivery="9").status_code, 500)
        self.assertFalse(WebhookDelivery.objects.exists())
        self.assertEqual(self.post(body_for(), delivery="9").json()["status"], "ok")  # a repetição da ETK já funciona
