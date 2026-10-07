"""Sincronização com a ETK. O formato das respostas é o de catalog.models.Event.to_api() no repositório etk-api."""
from datetime import timedelta
from unittest import mock

import requests
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.accounts.models import User
from apps.events import etk, services
from apps.events.models import Event

ETK = {"ETK_BASE": "https://etk.example", "ETK_API_KEY": "etk_live_x", "ETK_ENABLED": True,
       "ETK_PUBLIC_EVENT_URL": "https://site.example/eventos/{id}"}


def remote_event(n=1, amount=0.0, available=40, status="published", **over):
    data = {
        "id": f"EVNT{n}", "name": f"Evento {n}", "description": "Primeira linha.\nSegunda.", "category": "social_run",
        "date": (timezone.now() + timedelta(days=7)).isoformat().replace("+00:00", "Z"), "imageUrl": "https://img.example/a.jpg",
        "status": status, "location": {"province": "Maputo", "details": "Marginal"},
        "prices": [{"id": "PRC1", "name": "Geral", "amount": amount, "currency": "MZN", "status": "active", "available": available}],
        "totalTicketsPurchased": 10,
    }
    data.update(over)
    return data


def envelope(*events):
    return {"status": "success", "message": "Events retrieved successfully", "data": list(events)}


def fake_get(body, status=200):
    resp = mock.Mock(status_code=status)
    resp.json.return_value = body
    return mock.patch("apps.events.etk.requests.request", return_value=resp)


@override_settings(**ETK)
class SyncTests(TestCase):
    def test_creates_maps_fields_and_is_idempotent(self):
        with fake_get(envelope(remote_event(1, amount=0, available=40))) as get:
            result = etk.sync_events()
        self.assertEqual((result.created, result.updated), (1, 0))
        call = get.call_args
        self.assertEqual(call.args[:2], ("GET", "https://etk.example/back/borrow/external/events"))
        self.assertEqual(call.kwargs["headers"]["Authorization"], "Bearer etk_live_x")
        e = Event.objects.get()
        self.assertEqual((e.external_id, e.title, e.kind, e.location), ("EVNT1", "Evento 1", "group_run", "Marginal, Maputo"))
        self.assertEqual(e.summary, "Primeira linha.")
        self.assertEqual(e.cover_url, "https://img.example/a.jpg")
        self.assertEqual(e.external_url, "https://site.example/eventos/EVNT1")
        self.assertEqual(e.capacity, 50)  # evento grátis: 10 vendidos + 40 disponíveis
        self.assertFalse(e.has_paid_ticket)
        with fake_get(envelope(remote_event(1))):
            result = etk.sync_events()
        self.assertEqual((result.created, result.updated, Event.objects.count()), (0, 1, 1))

    def test_local_only_fields_survive_sync(self):
        with fake_get(envelope(remote_event(1))):
            etk.sync_events()
        Event.objects.update(checkin_points=250, members_only=True, meeting_point="Portão 2", distances="5 km · 10 km")
        with fake_get(envelope(remote_event(1, name="Novo nome"))):
            etk.sync_events()
        e = Event.objects.get()
        self.assertEqual((e.title, e.checkin_points, e.members_only, e.meeting_point, e.distances),
                         ("Novo nome", 250, True, "Portão 2", "5 km · 10 km"))
        self.assertEqual(e.slug, "evento-1")  # o endereço público não muda se o nome mudar

    @override_settings(VAPID_PUBLIC_KEY="pub", VAPID_PRIVATE_KEY="priv")
    def test_first_sync_does_not_push_but_later_new_events_do(self):
        from apps.notifications.models import PushSubscription

        user = User.objects.create_user("p@x.mz", "Corrida!2026x", first_name="P")
        PushSubscription.objects.create(user=user, endpoint="https://push.example/1", p256dh="p", auth="a")
        with mock.patch("pywebpush.webpush") as push, self.captureOnCommitCallbacks(execute=True):
            with fake_get(envelope(remote_event(1))):
                etk.sync_events()
        push.assert_not_called()  # primeira sincronização: não envia dezenas de avisos de uma vez
        with mock.patch("pywebpush.webpush") as push, self.captureOnCommitCallbacks(execute=True):
            with fake_get(envelope(remote_event(1), remote_event(2))):
                etk.sync_events()
        self.assertEqual(push.call_count, 1)
        self.assertIn("Evento 2", push.call_args.kwargs["data"])

    def test_unpublished_in_etk_is_hidden_here(self):
        with fake_get(envelope(remote_event(1), remote_event(2))):
            etk.sync_events()
        with fake_get(envelope(remote_event(1))):  # o 2 deixou de ser publicado
            result = etk.sync_events()
        self.assertEqual(result.unpublished, 1)
        self.assertFalse(Event.objects.get(external_id="EVNT2").is_published)
        with fake_get(envelope(remote_event(1), remote_event(2, status="cancelled"))):
            etk.sync_events()
        self.assertFalse(Event.objects.get(external_id="EVNT2").is_published)

    def test_local_events_without_external_id_are_never_pruned(self):
        local = Event.objects.create(title="Local", location="X", starts_at=timezone.now() + timedelta(days=2))
        with fake_get(envelope(remote_event(1))):
            etk.sync_events()
        local.refresh_from_db()
        self.assertTrue(local.is_published)

    def test_bad_event_is_skipped_others_still_sync(self):
        with fake_get(envelope({"id": "EVNT9", "name": "Sem data"}, remote_event(1))):
            result = etk.sync_events()
        self.assertEqual((result.created, len(result.skipped)), (1, 1))

    def test_errors_never_touch_the_database(self):
        with fake_get(envelope(remote_event(1))):
            etk.sync_events()
        for kwargs in ({"body": {}, "status": 401}, {"body": {}, "status": 500}, {"body": {"status": "error"}},
                       {"body": {"status": "success", "data": "x"}}):
            with fake_get(**kwargs), self.assertRaises(etk.EtkError):
                etk.sync_events()
        with mock.patch("apps.events.etk.requests.request", side_effect=requests.ConnectionError("down")), \
                self.assertRaises(etk.EtkError):
            etk.sync_events()
        self.assertTrue(Event.objects.get().is_published)

    def test_command_reports_and_fails_cleanly(self):
        with fake_get(envelope(remote_event(1))):
            call_command("sync_etk_events", stdout=mock.Mock())
        with override_settings(ETK_ENABLED=False), self.assertRaises(CommandError):
            call_command("sync_etk_events", stdout=mock.Mock())


@override_settings(**ETK)
class PaidEventTests(TestCase):
    def setUp(self):
        with fake_get(envelope(remote_event(1, amount=300, available=5), remote_event(2, amount=0, available=40))):
            etk.sync_events()
        self.paid, self.free = Event.objects.get(external_id="EVNT1"), Event.objects.get(external_id="EVNT2")
        self.user = User.objects.create_user("a@x.mz", "Corrida!2026x", first_name="Ana")

    def test_paid_event_cannot_be_registered_here(self):
        with self.assertRaises(services.RegistrationError):
            services.register(self.user, self.paid)
        self.assertTrue(services.register(self.user, self.free))

    def test_paid_event_page_links_to_ticket_site(self):
        html = self.client.get(self.paid.get_absolute_url()).content.decode()
        self.assertIn("Comprar bilhete", html)
        self.assertIn("https://site.example/eventos/EVNT1", html)
        self.assertIn("300", html)
        self.assertNotIn("Confirmar inscrição", html)
        self.client.force_login(self.user)
        self.assertIn("Confirmar inscrição", self.client.get(self.free.get_absolute_url()).content.decode())

    def test_register_endpoint_rejects_paid_event(self):
        self.client.force_login(self.user)
        resp = self.client.post(f"/eventos/{self.paid.slug}/inscrever/")
        self.assertFalse(self.paid.registrations.exists())
        self.assertIn(resp.status_code, (302, 400))

    def test_api_exposes_ticket_info(self):
        data = self.client.get(f"/api/v1/events/{self.paid.slug}/").json()
        self.assertTrue(data["requires_ticket"])
        self.assertEqual(data["tickets_available"], 5)
        self.assertEqual(data["external_url"], "https://site.example/eventos/EVNT1")
        self.assertEqual(data["cover_url"], "https://img.example/a.jpg")


@override_settings(**ETK)
class PanelEtkTests(TestCase):
    def setUp(self):
        with fake_get(envelope(remote_event(1))):
            etk.sync_events()
        self.event = Event.objects.get()
        self.staff = User.objects.create_user("s@x.mz", "Corrida!2026x", first_name="S", is_staff=True)
        self.client.force_login(self.staff)

    def test_cannot_create_events_and_buttons_are_gone(self):
        self.assertEqual(self.client.get("/painel/eventos/novo/").status_code, 302)
        html = self.client.get("/painel/eventos/").content.decode()
        self.assertNotIn("Novo evento", html)
        self.assertIn("Sincronizar com a ETK", html)

    def test_external_event_only_allows_club_fields(self):
        resp = self.client.post(f"/painel/eventos/{self.event.pk}/editar/", {
            "title": "Hackeado", "checkin_points": "300", "members_only": "on", "meeting_point": "Portão", "distances": "5 km",
            "map_url": ""})
        self.assertEqual(resp.status_code, 302)
        self.event.refresh_from_db()
        self.assertEqual((self.event.title, self.event.checkin_points, self.event.members_only), ("Evento 1", 300, True))

    def test_sync_button_runs_sync(self):
        with fake_get(envelope(remote_event(1, name="Atualizado"))):
            self.client.post("/painel/eventos/sincronizar/")
        self.event.refresh_from_db()
        self.assertEqual(self.event.title, "Atualizado")
        with fake_get({}, status=500):
            resp = self.client.post("/painel/eventos/sincronizar/", follow=True)
        self.assertContains(resp, "Não foi possível sincronizar")
