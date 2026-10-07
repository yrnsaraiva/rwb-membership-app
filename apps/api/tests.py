from datetime import timedelta

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.events.models import Event


class ApiTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user("a@x.mz", "Corrida!2026x", first_name="Ana")
        self.event = Event.objects.create(title="Treino", location="Marginal", starts_at=timezone.now() + timedelta(days=1))
        self.client = APIClient()

    def test_token_auth_and_me(self):
        resp = self.client.post("/api/v1/auth/token/", {"username": "a@x.mz", "password": "Corrida!2026x"}, format="json")
        self.assertEqual(resp.status_code, 200, resp.content)
        self.client.credentials(HTTP_AUTHORIZATION="Token " + resp.data["token"])
        resp = self.client.get("/api/v1/me/")
        self.assertEqual(resp.data["member_number"], self.user.member_number)

    def test_events_public(self):
        resp = self.client.get("/api/v1/events/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["results"][0]["slug"], self.event.slug)

    def test_register_and_runs(self):
        self.client.force_authenticate(self.user)
        resp = self.client.post(f"/api/v1/events/{self.event.slug}/register/", {}, format="json")
        self.assertEqual(resp.status_code, 201, resp.content)
        resp = self.client.post(f"/api/v1/events/{self.event.slug}/register/", {}, format="json")
        self.assertEqual(resp.status_code, 400)
        resp = self.client.post("/api/v1/runs/", {"date": timezone.localdate().isoformat(), "distance_km": "5.00",
                                                  "duration_seconds": 1800}, format="json")
        self.assertEqual(resp.status_code, 201, resp.content)
        self.assertEqual(resp.data["points"], 50)
        self.assertEqual(resp.data["pace_seconds"], 360)
        resp = self.client.get("/api/v1/me/dashboard/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(self.client.get("/api/v1/leaderboard/").data["results"][0]["name"], "Ana")

    def test_runs_require_auth(self):
        self.assertIn(self.client.get("/api/v1/runs/").status_code, (401, 403))


class ApiHardeningTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user("a@x.mz", "Corrida!2026x", first_name="Ana")
        self.client = APIClient()

    def _login(self):
        return self.client.post("/api/v1/auth/token/", {"username": "a@x.mz", "password": "Corrida!2026x"}, format="json")

    def test_token_expires(self):
        from rest_framework.authtoken.models import Token
        key = self._login().data["token"]
        Token.objects.filter(key=key).update(created=timezone.now() - timedelta(days=31))
        self.client.credentials(HTTP_AUTHORIZATION="Token " + key)
        self.assertEqual(self.client.get("/api/v1/me/").status_code, 401)
        self.client.credentials()
        self.assertNotEqual(self._login().data["token"], key)  # novo login emite novo token

    def test_logout_revokes_token_and_password_change_too(self):
        key = self._login().data["token"]
        self.client.credentials(HTTP_AUTHORIZATION="Token " + key)
        self.assertEqual(self.client.post("/api/v1/auth/logout/").status_code, 204)
        self.assertEqual(self.client.get("/api/v1/me/").status_code, 401)
        key = self._login().data["token"]
        self.user.set_password("OutraSenha!2026")
        self.user.save()
        self.client.credentials(HTTP_AUTHORIZATION="Token " + key)
        self.assertEqual(self.client.get("/api/v1/me/").status_code, 401)

    @override_settings(LOGIN_RATE_LIMIT_ATTEMPTS=3)
    def test_token_login_is_rate_limited_per_account(self):
        for _ in range(3):
            self.client.post("/api/v1/auth/token/", {"username": "a@x.mz", "password": "errada"}, format="json")
        self.assertEqual(self._login().status_code, 429)

    @override_settings(RWB_MAX_RUNS_PER_DAY=2)
    def test_run_limits_and_duplicates(self):
        self.client.force_authenticate(self.user)
        day = timezone.localdate().isoformat()

        def post(km, s):
            return self.client.post("/api/v1/runs/", {"date": day, "distance_km": km, "duration_seconds": s}, format="json")

        self.assertEqual(post("5.00", 1800).status_code, 201)
        self.assertEqual(post("5.00", 1800).status_code, 400)  # duplicada
        self.assertEqual(post("6.00", 2400).status_code, 201)
        self.assertEqual(post("7.00", 3000).status_code, 400)  # 3.ª no dia
