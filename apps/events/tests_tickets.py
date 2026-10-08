"""Entrada de bilhetes da ETK. Formato das respostas: ticketing.models.Ticket.to_api() e check_in() do repositório etk-api."""
from datetime import timedelta
from unittest import mock

from django.test import TestCase, override_settings
from django.utils import timezone

from apps.accounts.models import User
from apps.accounts.phone import normalize_phone
from apps.activity.models import PointTransaction
from apps.events import etk, ticket_checkin
from apps.events.models import Event, Registration

QR = "TCKT17913835229979|0123456789abcdef"
ETK = {"ETK_BASE": "https://etk.example", "ETK_API_KEY": "etk_live_x", "ETK_ENABLED": True}


def ticket(phone="258841234567", email="", entered=False, event_id="EVNT1", payment="paid"):
    return {"id": "TCKT1", "eventId": event_id, "event": {"id": event_id, "name": "Corrida Paga", "date": "2026-10-20T06:00:00Z"},
            "price": {"id": "PRC1", "name": "Geral"}, "phone": phone, "fullName": "Ana Sitoe", "email": email,
            "payment": payment, "entered": entered, "qrValue": QR}


def etk_reply(result="ok", message="Entrada autorizada.", t=None):
    # a ETK devolve o bilhete já com `entered=true` quando a entrada é dada (ou já tinha sido)
    default = ticket(entered=result in ("ok", "already_entered"))
    return {"result": result, "message": message, "ticket": t or default}


class PhoneTests(TestCase):
    def test_normalize(self):
        for raw in ("+258 84 123 4567", "84 123 4567", "00258841234567", "258841234567", "841234567"):
            self.assertEqual(normalize_phone(raw), "258841234567", raw)
        for raw in ("", "12345", "+27 82 123 4567", "+258 12 345", None, "+258 21 123 456", "880 123 456", "258 80 123 4567"):
            self.assertEqual(normalize_phone(raw), "", raw)

    def test_user_phone_is_normalized_on_save_and_update(self):
        u = User.objects.create_user("a@x.mz", "Corrida!2026x", first_name="A", phone="+258 84 123 4567")
        self.assertEqual(u.phone_e164, "258841234567")
        u.phone = "82 000 0000"
        u.save()
        self.assertEqual(User.objects.get(pk=u.pk).phone_e164, "258820000000")


@override_settings(**ETK)
class TicketCheckInTests(TestCase):
    def setUp(self):
        self.event = Event.objects.create(title="Corrida Paga", location="Marginal", external_id="EVNT1",
                                          starts_at=timezone.now() + timedelta(hours=1))
        self.ana = User.objects.create_user("ana@x.mz", "Corrida!2026x", first_name="Ana", phone="+258 84 123 4567")

    def checkin(self, reply):
        with mock.patch("apps.events.ticket_checkin.etk.check_in_ticket", return_value=reply) as m:
            return ticket_checkin.check_in_by_qr(QR), m

    def test_member_gets_presence_and_points_once(self):
        out, m = self.checkin(etk_reply())
        m.assert_called_once_with(QR)
        self.assertEqual((out.result, out.member, out.points, out.registered), ("ok", self.ana, 100, True))
        reg = Registration.objects.get(user=self.ana, event=self.event)
        self.assertIsNotNone(reg.checked_in_at)
        self.assertEqual(PointTransaction.objects.filter(user=self.ana, reason="event_checkin").count(), 1)
        # a ETK diz que já entrou: não paga pontos outra vez
        out, _ = self.checkin(etk_reply("already_entered", t=ticket(entered=True)))
        self.assertEqual((out.result, out.points), ("already_entered", 0))
        self.assertEqual(PointTransaction.objects.filter(user=self.ana, reason="event_checkin").count(), 1)

    def test_already_entered_in_etk_still_gives_missing_local_points(self):
        out, _ = self.checkin(etk_reply("already_entered", t=ticket(entered=True)))
        self.assertEqual(out.points, 100)  # entrou por outra porta/antes de a app saber

    def test_holder_not_a_member(self):
        out, _ = self.checkin(etk_reply(t=ticket(phone="258827654321")))
        self.assertEqual((out.result, out.member, out.points), ("ok", None, 0))
        self.assertTrue(out.admitted)
        self.assertEqual(Registration.objects.count(), 0)

    def test_matches_by_email_when_phone_differs(self):
        out, _ = self.checkin(etk_reply(t=ticket(phone="258827654321", email="ANA@x.mz")))
        self.assertEqual(out.member, self.ana)

    def test_ambiguous_phone_gives_no_points(self):
        User.objects.create_user("outra@x.mz", "Corrida!2026x", first_name="Outra", phone="84 123 4567")
        out, _ = self.checkin(etk_reply())
        self.assertEqual((out.result, out.member, out.points), ("ok", None, 0))

    def test_not_paid_and_unknown_do_not_touch_local_data(self):
        for result in ("not_paid", "not_found", "invalid_qr"):
            out, _ = self.checkin(etk_reply(result))
            self.assertFalse(out.admitted)
            self.assertEqual(out.points, 0)
        self.assertEqual(Registration.objects.count(), 0)

    def test_event_not_synced_still_admits_without_points(self):
        out, _ = self.checkin(etk_reply(t=ticket(event_id="EVNT-OUTRO")))
        self.assertEqual((out.result, out.member, out.points), ("ok", self.ana, 0))

    def test_cancelled_local_registration_becomes_the_ticket_mirror(self):
        Registration.objects.create(event=self.event, user=self.ana, status=Registration.Status.CANCELLED)
        out, _ = self.checkin(etk_reply())
        self.assertEqual(out.points, 100)
        self.assertTrue(Registration.objects.get(user=self.ana).is_active)

    def test_garbage_qr_never_reaches_etk_and_etk_down_is_reported(self):
        with mock.patch("apps.events.ticket_checkin.etk.check_in_ticket") as m:
            self.assertEqual(ticket_checkin.check_in_by_qr("hello").result, "invalid_qr")
            self.assertEqual(ticket_checkin.check_in_by_qr("TCKT1|zz").result, "invalid_qr")
        m.assert_not_called()
        with mock.patch("apps.events.ticket_checkin.etk.check_in_ticket", side_effect=etk.EtkError("down")):
            out = ticket_checkin.check_in_by_qr(QR)
        self.assertEqual((out.result, out.admitted), ("error", False))


@override_settings(**ETK)
class TicketEndpointsTests(TestCase):
    def setUp(self):
        self.event = Event.objects.create(title="Corrida Paga", location="Marginal", external_id="EVNT1",
                                          starts_at=timezone.now() + timedelta(hours=1))
        self.ana = User.objects.create_user("ana@x.mz", "Corrida!2026x", first_name="Ana", phone="84 123 4567")
        self.staff = User.objects.create_user("s@x.mz", "Corrida!2026x", first_name="S", is_staff=True)

    def test_scan_endpoint_requires_staff(self):
        self.assertEqual(self.client.post("/painel/bilhetes/entrada/", {"qrValue": QR}).status_code, 403)
        self.client.force_login(self.ana)
        self.assertEqual(self.client.post("/painel/bilhetes/entrada/", {"qrValue": QR}).status_code, 403)

    def test_scan_endpoint_returns_json(self):
        self.client.force_login(self.staff)
        with mock.patch("apps.events.ticket_checkin.etk.check_in_ticket", return_value=etk_reply()):
            data = self.client.post("/painel/bilhetes/entrada/", {"qrValue": QR}).json()
        self.assertEqual((data["result"], data["points"], data["member"]["member_number"]), ("ok", 100, self.ana.member_number))

    def test_api_endpoint(self):
        from rest_framework.test import APIClient

        api = APIClient()
        self.assertEqual(api.post("/api/v1/staff/tickets/check-in/", {"qrValue": QR}, format="json").status_code, 401)
        api.force_authenticate(self.ana)
        self.assertEqual(api.post("/api/v1/staff/tickets/check-in/", {"qrValue": QR}, format="json").status_code, 403)
        api.force_authenticate(self.staff)
        with mock.patch("apps.events.ticket_checkin.etk.check_in_ticket", return_value=etk_reply()):
            resp = api.post("/api/v1/staff/tickets/check-in/", {"qrValue": QR}, format="json")
        self.assertEqual((resp.status_code, resp.data["result"]), (200, "ok"))

    def test_member_card_page_mirrors_website_tickets_and_shows_entry_button(self):
        self.client.force_login(self.staff)
        with mock.patch("apps.events.tickets.etk.fetch_tickets", return_value=[ticket()]) as fetch:
            html = self.client.get(self.ana.get_verify_url()).content.decode()
        fetch.assert_called_once()
        self.assertEqual(fetch.call_args.kwargs["phone"], "258841234567")
        reg = Registration.objects.get(user=self.ana)
        self.assertEqual((reg.external_ticket_id, reg.ticket_payment, reg.status), ("TCKT1", "paid", "confirmed"))
        self.assertIn("Corrida Paga", html)
        self.assertIn("Dar entrada", html)

    def test_member_card_page_survives_etk_down_and_never_calls_it_for_non_staff(self):
        self.client.force_login(self.staff)
        with mock.patch("apps.events.tickets.etk.fetch_tickets", side_effect=etk.EtkError("down")):
            self.assertIn("Não foi possível consultar os bilhetes", self.client.get(self.ana.get_verify_url()).content.decode())
        self.client.force_login(self.ana)
        with mock.patch("apps.events.tickets.etk.fetch_tickets") as fetch:
            self.client.get(self.ana.get_verify_url())
        fetch.assert_not_called()

    def test_presence_button_for_ticket_registration_enters_through_etk(self):
        from apps.events import tickets

        reg = tickets.upsert_registration(ticket(), self.ana)
        self.client.force_login(self.staff)
        with mock.patch("apps.events.ticket_checkin.etk.check_in_ticket", return_value=etk_reply()) as c:
            resp = self.client.post(f"/painel/inscricoes/{reg.pk}/presenca/", follow=True)
        c.assert_called_once_with(QR)
        self.assertContains(resp, "Entrada autorizada")
        self.assertEqual(PointTransaction.objects.filter(user=self.ana, reason="event_checkin").count(), 1)
        # segunda vez: a entrada não se desfaz (já está na ETK)
        with mock.patch("apps.events.ticket_checkin.etk.check_in_ticket") as c:
            resp = self.client.post(f"/painel/inscricoes/{reg.pk}/presenca/", follow=True)
        c.assert_not_called()
        self.assertContains(resp, "já tem a entrada")
        self.assertEqual(PointTransaction.objects.filter(user=self.ana, reason="event_checkin").count(), 1)
