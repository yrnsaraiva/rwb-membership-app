from datetime import timedelta

from django.core import mail
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.activity.models import PointTransaction

from . import services
from .models import Event, Registration


def make_event(**kw):
    defaults = {"title": "Corrida na Marginal", "location": "Marginal", "starts_at": timezone.now() + timedelta(days=3)}
    defaults.update(kw)
    return Event.objects.create(**defaults)


class EventServiceTests(TestCase):
    def setUp(self):
        self.u1 = User.objects.create_user("a@x.mz", "x", first_name="A")
        self.u2 = User.objects.create_user("b@x.mz", "x", first_name="B")

    def test_slug_unique(self):
        e1, e2 = make_event(), make_event()
        self.assertNotEqual(e1.slug, e2.slug)

    def test_capacity_enforced(self):
        event = make_event(capacity=1)
        services.register(self.u1, event)
        with self.assertRaises(services.RegistrationError):
            services.register(self.u2, event)

    def test_double_registration_blocked_and_reregister_after_cancel(self):
        event = make_event()
        services.register(self.u1, event)
        with self.assertRaises(services.RegistrationError):
            services.register(self.u1, event)
        services.cancel(self.u1, event)
        reg = services.register(self.u1, event)
        self.assertTrue(reg.is_active)
        self.assertEqual(Registration.objects.count(), 1)

    def test_cancel_frees_spot(self):
        event = make_event(capacity=1)
        services.register(self.u1, event)
        services.cancel(self.u1, event)
        services.register(self.u2, event)

    def test_closed_registration(self):
        event = make_event(registration_closes_at=timezone.now() - timedelta(hours=1))
        with self.assertRaises(services.RegistrationError):
            services.register(self.u1, event)

    def test_members_only(self):
        event = make_event(members_only=True)
        with self.assertRaises(services.RegistrationError):
            services.register(self.u1, event)

    def test_confirmation_email(self):
        event = make_event()
        with self.captureOnCommitCallbacks(execute=True):
            services.register(self.u1, event)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(event.title, mail.outbox[0].subject)

    def test_checkin_awards_points_once_and_undo(self):
        event = make_event(checkin_points=100)
        reg = services.register(self.u1, event)
        self.assertTrue(services.check_in(reg))
        self.assertFalse(services.check_in(reg))
        self.assertEqual(PointTransaction.objects.filter(user=self.u1).count(), 1)
        services.undo_check_in(reg)
        self.assertEqual(PointTransaction.objects.filter(user=self.u1).count(), 0)


class EventViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("a@x.mz", "x", first_name="A")
        self.event = make_event(capacity=10, distances="5 km · 10 km")

    def test_public_list_and_detail(self):
        self.assertContains(self.client.get(reverse("events:list")), self.event.title)
        self.assertContains(self.client.get(self.event.get_absolute_url()), "Criar conta")

    def test_register_flow(self):
        self.client.force_login(self.user)
        resp = self.client.post(reverse("events:register", args=[self.event.slug]), {"distance": "10 km"})
        self.assertRedirects(resp, self.event.get_absolute_url())
        reg = Registration.objects.get()
        self.assertEqual(reg.distance, "10 km")
        resp = self.client.get(self.event.get_absolute_url())
        self.assertContains(resp, "Estás inscrito")
        self.client.post(reverse("events:cancel", args=[self.event.slug]))
        reg.refresh_from_db()
        self.assertFalse(reg.is_active)

    def test_ics(self):
        resp = self.client.get(reverse("events:ics", args=[self.event.slug]))
        self.assertEqual(resp["Content-Type"], "text/calendar; charset=utf-8")
        self.assertIn(b"BEGIN:VEVENT", resp.content)

    def test_unpublished_hidden(self):
        hidden = make_event(title="Secreto", is_published=False)
        self.assertEqual(self.client.get(hidden.get_absolute_url()).status_code, 404)
