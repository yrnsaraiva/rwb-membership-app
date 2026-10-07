"""Inscrições nos eventos da ETK: o bilhete é emitido, cobrado e validado na ETK; aqui fica o espelho."""
from datetime import timedelta
from unittest import mock

from django.core import mail
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.activity.models import PointTransaction
from apps.events import etk, services, tickets
from apps.events.models import Event, Registration

ETK = {"ETK_BASE": "https://etk.example", "ETK_API_KEY": "etk_live_x", "ETK_ENABLED": True}
QR = "TCKT100|0123456789abcdef"


def price(id="PRC1", amount=0.0, available=10, name="Geral", status="active"):
    return {"id": id, "name": name, "amount": amount, "currency": "MZN", "status": status, "available": available}


def ticket(id="TCKT100", payment="paid", amount=0.0, phone="258841234567", event_id="EVNT1", entered=False, **extra):
    return {"id": id, "eventId": event_id, "event": {"id": event_id, "name": "Corrida"}, "price": {"id": "PRC1", "name": "Geral"},
            "amount": amount, "phone": phone, "email": "", "fullName": "Ana", "payment": payment, "entered": entered,
            "qrValue": QR, "expiresAt": None, "checkoutUrl": "", **extra}


@override_settings(**ETK)
class BuyTicketTests(TestCase):
    def setUp(self):
        self.event = Event.objects.create(title="Corrida", location="Marginal", external_id="EVNT1", ticket_prices=[price()],
                                          starts_at=timezone.now() + timedelta(days=3))
        self.ana = User.objects.create_user("ana@x.mz", "Corrida!2026x", first_name="Ana", last_name="S", phone="+258 84 123 4567")

    def buy(self, reply, **kw):
        with mock.patch("apps.events.tickets.etk.create_ticket", return_value=reply) as m, \
                self.captureOnCommitCallbacks(execute=True):
            return tickets.buy_ticket(self.ana, self.event, **kw), m

    def test_free_ticket_is_confirmed_immediately_with_email(self):
        reg, m = self.buy(ticket())
        self.assertEqual((reg.status, reg.ticket_payment, reg.ticket_qr, reg.via_app), ("confirmed", "paid", QR, True))
        kw = m.call_args.kwargs
        self.assertEqual((kw["price_id"], kw["event_id"], kw["phone"], kw["email"], kw["payment_method"]),
                         ("PRC1", "EVNT1", "258841234567", "ana@x.mz", ""))
        self.assertEqual(kw["external_reference"], f"rwb:{self.ana.pk}:258841234567:EVNT1")  # evita bilhetes duplicados em retries
        self.assertEqual(len(mail.outbox), 1)

    def test_paid_ticket_via_emola_stays_pending_until_paid(self):
        Event.objects.update(ticket_prices=[price(amount=300.0)])
        self.event.refresh_from_db()
        reply = ticket(payment="pending", amount=300.0, paymentInstructions="Aprova o pedido no e-Mola.",
                       expiresAt=(timezone.now() + timedelta(minutes=15)).isoformat())
        reg, m = self.buy(reply, payment_method="emola")
        self.assertEqual((reg.status, reg.ticket_payment, reg.ticket_instructions), ("pending", "pending", "Aprova o pedido no e-Mola."))
        self.assertEqual(m.call_args.kwargs["payment_method"], "emola")
        self.assertEqual(len(mail.outbox), 0)  # ainda não há bilhete
        self.assertFalse(reg.is_active)
        # o pagamento entra: a sondagem confirma, envia email e abre o QR
        with mock.patch("apps.events.tickets.etk.get_ticket", return_value=ticket(amount=300.0)), \
                self.captureOnCommitCallbacks(execute=True):
            reg = tickets.refresh_registration(reg)
        self.assertEqual((reg.status, reg.ticket_qr), ("confirmed", QR))
        self.assertEqual(len(mail.outbox), 1)
        with mock.patch("apps.events.tickets.etk.get_ticket", return_value=ticket(amount=300.0)), \
                self.captureOnCommitCallbacks(execute=True):
            tickets.refresh_registration(reg)
        self.assertEqual(len(mail.outbox), 1)  # só avisa uma vez

    def test_declined_or_failed_payment_frees_the_member_to_try_again(self):
        Event.objects.update(ticket_prices=[price(amount=300.0)])
        self.event.refresh_from_db()
        reg, _ = self.buy(ticket(payment="pending", amount=300.0), payment_method="emola")
        with mock.patch("apps.events.tickets.etk.get_ticket", return_value=ticket(payment="failed", amount=300.0)):
            reg = tickets.refresh_registration(reg)
        self.assertEqual(reg.status, "cancelled")
        reg2, _ = self.buy(ticket(id="TCKT101", payment="pending", amount=300.0), payment_method="mpesa")
        self.assertEqual((reg2.pk, reg2.external_ticket_id), (reg.pk, "TCKT101"))  # mesma inscrição, novo bilhete

    def test_validation_messages(self):
        with self.assertRaisesMessage(tickets.TicketError, "Escolhe como queres pagar"):
            Event.objects.update(ticket_prices=[price(amount=300.0)])
            self.event.refresh_from_db()
            self.buy(ticket(), price_id="PRC1")
        no_phone = User.objects.create_user("b@x.mz", "Corrida!2026x", first_name="B")
        with self.assertRaisesMessage(tickets.TicketError, "telemóvel"):
            tickets.buy_ticket(no_phone, self.event)
        self.event.ticket_prices = [price("A", name="Normal"), price("B", name="VIP")]
        self.event.save()
        with self.assertRaisesMessage(tickets.TicketError, "Escolhe o tipo de bilhete"):
            tickets.buy_ticket(self.ana, self.event)
        self.event.ticket_prices = [price(available=0)]
        self.event.save()
        with self.assertRaisesMessage(tickets.TicketError, "esgotados"):
            tickets.buy_ticket(self.ana, self.event)

    def test_cannot_buy_twice_or_when_closed_or_premium_only(self):
        self.buy(ticket())
        with self.assertRaisesMessage(tickets.TicketError, "Já tens inscrição"):
            tickets.buy_ticket(self.ana, self.event)
        other = User.objects.create_user("c@x.mz", "Corrida!2026x", first_name="C", phone="82 000 0001")
        self.event.members_only = True
        self.event.save()
        with self.assertRaisesMessage(tickets.TicketError, "premium"):
            tickets.buy_ticket(other, self.event)
        self.event.members_only, self.event.is_published = False, False
        self.event.save()
        with self.assertRaisesMessage(tickets.TicketError, "não estão abertas"):
            tickets.buy_ticket(other, self.event)

    def test_lost_response_is_recovered_by_external_reference(self):
        """O gateway demorou e o pedido deu timeout, mas a ETK chegou a criar o bilhete: aproveita-o em vez de falhar."""
        mine = ticket(externalReference=f"rwb:{self.ana.pk}:258841234567:EVNT1")
        other = ticket(id="TCKT999", externalReference="rwb:99:EVNT1")
        with mock.patch("apps.events.tickets.etk.create_ticket", side_effect=etk.EtkError("timeout")), \
                mock.patch("apps.events.tickets.etk.fetch_tickets", return_value=[other, mine]) as f:
            reg = tickets.buy_ticket(self.ana, self.event)
        self.assertEqual((reg.external_ticket_id, reg.status), ("TCKT100", "confirmed"))
        self.assertEqual((f.call_args.kwargs["phone"], f.call_args.kwargs["event_id"]), ("258841234567", "EVNT1"))

    def test_lost_response_with_no_ticket_found_is_a_friendly_error(self):
        with mock.patch("apps.events.tickets.etk.create_ticket", side_effect=etk.EtkError("timeout")), \
                mock.patch("apps.events.tickets.etk.fetch_tickets", return_value=[ticket(payment="failed", externalReference=f"rwb:{self.ana.pk}:258841234567:EVNT1")]):
            with self.assertRaisesMessage(tickets.TicketError, "Não foi possível falar"):
                tickets.buy_ticket(self.ana, self.event)

    def test_ticket_of_another_phone_is_never_mirrored(self):
        """Se a deduplicação da ETK devolvesse o bilhete de outra pessoa (referência repetida), não é espelhado."""
        with mock.patch("apps.events.tickets.etk.create_ticket", return_value=ticket(phone="258827654321")):
            with self.assertRaisesMessage(tickets.TicketError, "Contacta o clube"):
                tickets.buy_ticket(self.ana, self.event)
        self.assertFalse(Registration.objects.exists())

    def test_card_is_an_accepted_method(self):
        Event.objects.update(ticket_prices=[price(amount=300.0)])
        self.event.refresh_from_db()
        reg, m = self.buy(ticket(payment="pending", amount=300.0, checkoutUrl="https://pay.example/c/1"), payment_method="card")
        self.assertEqual(m.call_args.kwargs["payment_method"], "card")
        self.assertEqual(reg.ticket_checkout_url, "https://pay.example/c/1")

    def test_etk_rejection_and_outage_become_friendly_errors(self):
        with mock.patch("apps.events.tickets.etk.create_ticket", side_effect=etk.EtkRejected("Bilhetes esgotados.")):
            with self.assertRaisesMessage(tickets.TicketError, "Bilhetes esgotados."):
                tickets.buy_ticket(self.ana, self.event)
        with mock.patch("apps.events.tickets.etk.create_ticket", side_effect=etk.EtkError("timeout")):
            with self.assertRaisesMessage(tickets.TicketError, "Não foi possível falar"):
                tickets.buy_ticket(self.ana, self.event)
        self.assertFalse(Registration.objects.exists())

    def test_local_registration_and_cancel_are_blocked_for_etk_events(self):
        with self.assertRaises(services.RegistrationError):
            services.register(self.ana, self.event)
        self.buy(ticket())
        with self.assertRaisesMessage(services.RegistrationError, "organização"):
            services.cancel(self.ana, self.event)

    def test_preregistration_then_confirm(self):
        self.event.registration_mode = "preregistration"
        self.event.confirmation_opens_at = timezone.now() - timedelta(hours=1)
        self.event.confirmation_deadline = timezone.now() + timedelta(days=1)
        self.event.save()
        reg, _ = self.buy(ticket(payment="preregistered"))
        self.assertEqual((reg.status, reg.ticket_payment), ("confirmed", "preregistered"))
        self.assertEqual(len(mail.outbox), 0)  # ainda não há lugar garantido: nada de «inscrição confirmada»
        # o bilhete foi ligado por email e tem outro telemóvel: a confirmação tem de usar o do bilhete
        with mock.patch("apps.events.tickets.etk.get_ticket", return_value=ticket(payment="preregistered", phone="258827654321")), \
                mock.patch("apps.events.tickets.etk.confirm_ticket", return_value=ticket()) as c, \
                self.captureOnCommitCallbacks(execute=True):
            reg = tickets.confirm_presence(self.ana, self.event)
        c.assert_called_once_with("TCKT100", "258827654321")
        self.assertEqual(reg.ticket_payment, "paid")
        self.assertEqual(len(mail.outbox), 1)  # agora sim
        with self.assertRaises(tickets.TicketError):
            tickets.confirm_presence(self.ana, self.event)


@override_settings(**ETK)
class MirrorTests(TestCase):
    def setUp(self):
        self.event = Event.objects.create(title="Corrida", location="X", external_id="EVNT1", ticket_prices=[price()],
                                          starts_at=timezone.now() + timedelta(days=1))
        self.ana = User.objects.create_user("ana@x.mz", "Corrida!2026x", first_name="Ana", phone="84 123 4567")

    def test_website_purchase_appears_without_email_or_push(self):
        reg = tickets.upsert_registration(ticket())
        self.assertEqual((reg.user, reg.status, reg.via_app), (self.ana, "confirmed", False))
        self.assertEqual(len(mail.outbox), 0)

    def test_non_member_and_unknown_event_are_ignored(self):
        self.assertIsNone(tickets.upsert_registration(ticket(phone="258827654321")))
        self.assertIsNone(tickets.upsert_registration(ticket(event_id="EVNT-X")))
        self.assertFalse(Registration.objects.exists())

    def test_entry_given_elsewhere_pays_points_once(self):
        tickets.upsert_registration(ticket())
        for _ in range(2):
            reg = tickets.upsert_registration(ticket(entered=True))
        self.assertTrue(reg.ticket_entered)
        self.assertIsNotNone(reg.checked_in_at)
        self.assertEqual(PointTransaction.objects.filter(user=self.ana, reason="event_checkin").count(), 1)

    def test_second_ticket_of_same_member_does_not_replace_the_first(self):
        first = tickets.upsert_registration(ticket())
        again = tickets.upsert_registration(ticket(id="TCKT200"))
        self.assertEqual(again.pk, first.pk)
        self.assertEqual(Registration.objects.get().external_ticket_id, "TCKT100")

    def test_refund_cancels_the_registration(self):
        tickets.upsert_registration(ticket())
        reg = tickets.upsert_registration(ticket(payment="refunded"))
        self.assertEqual(reg.status, "cancelled")
        self.assertFalse(reg.is_active)

    def test_sync_tickets_uses_since_after_first_run_and_command_reports(self):
        from io import StringIO

        from django.core.management import call_command

        with mock.patch("apps.events.tickets.etk.fetch_tickets", return_value=[ticket(), ticket(id="T2", phone="258827654321")]) as f:
            out = StringIO()
            call_command("sync_etk_tickets", stdout=out)
        f.assert_called_once_with(since=None)
        self.assertIn("2 bilhete(s) lido(s), 1 ligado(s)", out.getvalue())
        with mock.patch("apps.events.tickets.etk.fetch_tickets", return_value=[]) as f:
            tickets.sync_tickets()
        self.assertIsNotNone(f.call_args.kwargs["since"])

    def test_cursor_advances_even_when_tickets_belong_to_non_members(self):
        from apps.events.models import SyncCursor

        with mock.patch("apps.events.tickets.etk.fetch_tickets", return_value=[ticket(phone="258827654321")]):
            tickets.sync_tickets()
        self.assertTrue(SyncCursor.objects.filter(name="etk_tickets").exists())
        with mock.patch("apps.events.tickets.etk.fetch_tickets", side_effect=etk.EtkError("down")):
            before = SyncCursor.objects.get(name="etk_tickets").synced_at
            with self.assertRaises(etk.EtkError):
                tickets.sync_tickets()
        self.assertEqual(SyncCursor.objects.get(name="etk_tickets").synced_at, before)  # falhou: não avança

    def test_full_sync_ignores_the_cursor(self):
        with mock.patch("apps.events.tickets.etk.fetch_tickets", return_value=[]):
            tickets.sync_tickets()
        with mock.patch("apps.events.tickets.etk.fetch_tickets", return_value=[]) as f:
            tickets.sync_tickets(full=True)
        f.assert_called_once_with(since=None)

    def test_expired_pending_reservations_are_rechecked(self):
        reg = tickets.upsert_registration(ticket(payment="pending", expiresAt=(timezone.now() - timedelta(minutes=1)).isoformat()))
        self.assertEqual(reg.status, "pending")
        with mock.patch("apps.events.tickets.etk.fetch_tickets", return_value=[]), \
                mock.patch("apps.events.tickets.etk.get_ticket", return_value=ticket(payment="failed")):
            tickets.sync_tickets()
        reg.refresh_from_db()
        self.assertEqual(reg.status, "cancelled")


@override_settings(**ETK)
class WebAndApiTests(TestCase):
    def setUp(self):
        self.event = Event.objects.create(title="Corrida", location="Marginal", external_id="EVNT1", slug="corrida",
                                          ticket_prices=[price(amount=300.0)], starts_at=timezone.now() + timedelta(days=3))
        self.ana = User.objects.create_user("ana@x.mz", "Corrida!2026x", first_name="Ana", phone="84 123 4567")

    def test_page_shows_price_choice_and_methods_then_qr_after_paid(self):
        self.client.force_login(self.ana)
        html = self.client.get("/eventos/corrida/").content.decode()
        for needle in ("M-Pesa", "e-Mola", "mKesh", "300", "data-ticket-form"):
            self.assertIn(needle, html)
        with mock.patch("apps.events.tickets.etk.create_ticket", return_value=ticket(payment="pending", amount=300.0,
                                                                                    paymentInstructions="Aprova no e-Mola.")):
            resp = self.client.post("/eventos/corrida/inscrever/", {"price": "PRC1", "payment_method": "emola"}, follow=True)
        self.assertContains(resp, "A aguardar o pagamento")
        self.assertContains(resp, "data-ticket-poll")
        with mock.patch("apps.events.tickets.etk.get_ticket", return_value=ticket(amount=300.0)):
            status = self.client.get("/eventos/corrida/bilhete/").json()
            html = self.client.get("/eventos/corrida/").content.decode()
        self.assertEqual(status["status"], "confirmed")
        self.assertIn("Tens bilhete", html)
        self.assertIn("<svg", html)  # QR do bilhete
        self.assertNotIn("Confirmar inscrição", html)

    def test_page_asks_for_phone_when_missing_and_hides_form_for_visitors(self):
        no_phone = User.objects.create_user("b@x.mz", "Corrida!2026x", first_name="B")
        self.client.force_login(no_phone)
        self.assertContains(self.client.get("/eventos/corrida/"), "Falta o teu telemóvel")
        self.client.logout()
        html = self.client.get("/eventos/corrida/").content.decode()
        self.assertIn("Criar conta", html)
        self.assertNotIn("data-ticket-form", html)

    def test_web_errors_are_shown_as_messages(self):
        self.client.force_login(self.ana)
        resp = self.client.post("/eventos/corrida/inscrever/", {"price": "PRC1"}, follow=True)
        self.assertContains(resp, "Escolhe como queres pagar")

    def test_api_register_ticket_poll_and_cancel(self):
        api = APIClient()
        api.force_authenticate(self.ana)
        with mock.patch("apps.events.tickets.etk.create_ticket", return_value=ticket(payment="pending", amount=300.0,
                                                                                    paymentInstructions="Aprova.")):
            resp = api.post("/api/v1/events/corrida/register/", {"price": "PRC1", "payment_method": "mkesh"}, format="json")
        self.assertEqual(resp.status_code, 201, resp.content)
        self.assertEqual((resp.data["status"], resp.data["payment"], resp.data["qr_value"]), ("pending", "pending", ""))
        with mock.patch("apps.events.tickets.etk.get_ticket", return_value=ticket(amount=300.0)):
            resp = api.get("/api/v1/events/corrida/ticket/")
        self.assertEqual((resp.data["status"], resp.data["qr_value"]), ("confirmed", QR))
        self.assertEqual(api.post("/api/v1/events/corrida/cancel/").status_code, 400)
        bad = api.post("/api/v1/events/corrida/register/", {"payment_method": "bitcoin"}, format="json")
        self.assertEqual(bad.status_code, 400)

    def test_api_register_error_from_etk(self):
        api = APIClient()
        api.force_authenticate(self.ana)
        with mock.patch("apps.events.tickets.etk.create_ticket", side_effect=etk.EtkRejected("Pagamento recusado.")):
            resp = api.post("/api/v1/events/corrida/register/", {"price": "PRC1", "payment_method": "mpesa"}, format="json")
        self.assertEqual((resp.status_code, resp.data["detail"]), (400, "Pagamento recusado."))
