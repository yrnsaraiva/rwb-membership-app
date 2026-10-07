from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.activity import services as activity
from apps.activity.models import PointTransaction
from apps.events import services as event_services
from apps.events.models import Event


class PanelTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user("s@x.mz", "x", first_name="Staff", is_staff=True)
        self.member = User.objects.create_user("m@x.mz", "x", first_name="Membro")
        self.event = Event.objects.create(title="Treino", location="Costa do Sol",
                                          starts_at=timezone.now() + timedelta(hours=2), capacity=20)

    def test_members_cannot_access(self):
        self.client.force_login(self.member)
        resp = self.client.get(reverse("panel:index"))
        self.assertEqual(resp.status_code, 302)

    def test_pages_render(self):
        self.client.force_login(self.staff)
        activity.log_run(self.member, date=timezone.localdate(), distance_km=Decimal("50"), duration=timedelta(hours=2))
        event_services.register(self.member, self.event)
        for name, args in [("panel:index", []), ("panel:members", []), ("panel:member_detail", [self.member.pk]),
                           ("panel:events", []), ("panel:event_create", []), ("panel:event_edit", [self.event.pk]),
                           ("panel:event_registrations", [self.event.pk]), ("panel:runs", []),
                           ("panel:subscriptions", [])]:
            resp = self.client.get(reverse(name, args=args))
            self.assertEqual(resp.status_code, 200, name)
        self.assertContains(self.client.get(reverse("panel:runs")), "Membro")  # 50 km => suspeita

    def test_csv_exports(self):
        self.client.force_login(self.staff)
        resp = self.client.get(reverse("panel:members") + "?formato=csv")
        self.assertIn("m@x.mz", resp.content.decode("utf-8"))
        resp = self.client.get(reverse("panel:event_registrations", args=[self.event.pk]) + "?formato=csv")
        self.assertEqual(resp.status_code, 200)

    def test_create_event(self):
        self.client.force_login(self.staff)
        start = timezone.localtime() + timedelta(days=7)
        resp = self.client.post(reverse("panel:event_create"), {
            "title": "Night Run", "kind": "race", "location": "Baixa", "starts_at": start.strftime("%Y-%m-%dT%H:%M"),
            "price_mzn": "0", "is_published": "on", "distances": "5 km · 10 km",
        })
        event = Event.objects.get(title="Night Run")
        self.assertRedirects(resp, reverse("panel:event_registrations", args=[event.pk]))
        self.assertEqual(event.created_by, self.staff)

    def test_checkin_via_qr_verify_page(self):
        reg = event_services.register(self.member, self.event)
        self.client.force_login(self.staff)
        resp = self.client.get(self.member.get_verify_url())
        self.assertContains(resp, "Marcar presença")
        self.client.post(reverse("panel:registration_checkin", args=[reg.pk]), {"next": self.member.get_verify_url()})
        self.assertTrue(PointTransaction.objects.filter(user=self.member, reason="event_checkin").exists())

    def test_invalidate_run(self):
        run = activity.log_run(self.member, date=timezone.localdate(), distance_km=Decimal("5"), duration=timedelta(minutes=30))
        self.client.force_login(self.staff)
        self.client.post(reverse("panel:run_toggle_valid", args=[run.pk]), {"note": "duplicada"})
        run.refresh_from_db()
        self.assertFalse(run.is_valid)
        self.assertEqual(activity.member_stats(self.member)["points"], 0)

    def test_points_adjustment(self):
        self.client.force_login(self.staff)
        self.client.post(reverse("panel:member_detail", args=[self.member.pk]), {"amount": "25", "description": "Voluntário"})
        self.assertEqual(activity.member_stats(self.member)["points"], 25)


class AdminTests(TestCase):
    def test_unfold_admin_pages(self):
        admin_user = User.objects.create_superuser("root@x.mz", "x", first_name="Root")
        self.client.force_login(admin_user)
        for url in ["/django-admin/", "/django-admin/accounts/user/", "/django-admin/accounts/user/add/",
                    f"/django-admin/accounts/user/{admin_user.pk}/change/", "/django-admin/shop/product/",
                    "/django-admin/shop/product/add/", "/django-admin/shop/order/", "/django-admin/events/event/add/",
                    "/django-admin/billing/subscription/", "/django-admin/auth/group/"]:
            self.assertEqual(self.client.get(url).status_code, 200, url)

    def test_admin_create_user(self):
        admin_user = User.objects.create_superuser("root@x.mz", "x", first_name="Root")
        self.client.force_login(admin_user)
        resp = self.client.post("/django-admin/accounts/user/add/", {
            "email": "novo@x.mz", "first_name": "Novo", "last_name": "Membro",
            "password1": "Corrida!2026x", "password2": "Corrida!2026x", "usable_password": "true",
        })
        self.assertEqual(resp.status_code, 302, getattr(resp, "context", None) and resp.context["adminform"].form.errors)
        self.assertTrue(User.objects.filter(email="novo@x.mz").exists())
