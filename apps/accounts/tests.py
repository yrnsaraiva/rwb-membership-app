from django.core import mail
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from .models import User


class AccountTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_register_creates_member_number_and_logs_in(self):
        resp = self.client.post(reverse("accounts:register"), {
            "first_name": "Ana", "last_name": "Sitoe", "email": "ANA@Exemplo.co.mz", "phone": "+258840000000",
            "password1": "Corrida!2026x", "password2": "Corrida!2026x", "accept_terms": "on",
        })
        self.assertRedirects(resp, reverse("activity:dashboard"))
        user = User.objects.get()
        self.assertEqual(user.email, "ana@exemplo.co.mz")
        self.assertEqual(user.member_number, f"RWB-{user.pk:05d}")
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(user.member_number, mail.outbox[0].body)

    def test_duplicate_email_case_insensitive(self):
        User.objects.create_user("ana@exemplo.co.mz", "x", first_name="Ana", last_name="S")
        resp = self.client.post(reverse("accounts:register"), {
            "first_name": "Ana", "last_name": "S", "email": "Ana@exemplo.co.mz",
            "password1": "Corrida!2026x", "password2": "Corrida!2026x", "accept_terms": "on",
        })
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(User.objects.count(), 1)

    def test_login_with_email(self):
        User.objects.create_user("bruno@exemplo.co.mz", "Corrida!2026x", first_name="Bruno")
        resp = self.client.post(reverse("accounts:login"), {"username": "Bruno@exemplo.co.mz", "password": "Corrida!2026x"})
        self.assertRedirects(resp, reverse("activity:dashboard"))

    @override_settings(LOGIN_RATE_LIMIT_ATTEMPTS=3)
    def test_login_rate_limited(self):
        User.objects.create_user("c@exemplo.co.mz", "Corrida!2026x")
        url = reverse("accounts:login")
        for _ in range(3):
            self.client.post(url, {"username": "c@exemplo.co.mz", "password": "errada"})
        resp = self.client.post(url, {"username": "c@exemplo.co.mz", "password": "Corrida!2026x"})
        self.assertEqual(resp.status_code, 429)

    def test_card_and_verify(self):
        user = User.objects.create_user("d@exemplo.co.mz", "Corrida!2026x", first_name="Délcio")
        self.client.force_login(user)
        resp = self.client.get(reverse("accounts:card"))
        self.assertContains(resp, "<svg")
        self.assertContains(resp, user.member_number)
        self.client.logout()
        resp = self.client.get(user.get_verify_url())
        self.assertContains(resp, "Membro válido")

    def test_profile_pages(self):
        user = User.objects.create_user("e@exemplo.co.mz", "Corrida!2026x", first_name="Edna")
        self.client.force_login(user)
        self.assertEqual(self.client.get(reverse("accounts:profile")).status_code, 200)
        resp = self.client.post(reverse("accounts:profile_edit"), {
            "first_name": "Edna", "last_name": "Mondlane", "phone": "", "city": "Matola", "bio": "",
            "show_on_leaderboard": "on",
        })
        self.assertRedirects(resp, reverse("accounts:profile"))
        user.refresh_from_db()
        self.assertEqual(user.city, "Matola")

    def test_logout_requires_post(self):
        user = User.objects.create_user("f@exemplo.co.mz", "x")
        self.client.force_login(user)
        resp = self.client.post(reverse("accounts:logout"))
        self.assertEqual(resp.status_code, 302)


class RateLimitHardeningTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user("v@exemplo.co.mz", "Corrida!2026x", first_name="Vera")

    @override_settings(LOGIN_RATE_LIMIT_ATTEMPTS=3, TRUSTED_PROXY_COUNT=1)
    def test_forged_forwarded_for_does_not_reset_limit(self):
        url = reverse("accounts:login")
        for i in range(3):  # o atacante troca o 1.º valor do cabeçalho; o proxy acrescenta o IP real no fim
            self.client.post(url, {"username": "v@exemplo.co.mz", "password": "x"}, HTTP_X_FORWARDED_FOR=f"1.1.1.{i}, 9.9.9.9")
        resp = self.client.post(url, {"username": "v@exemplo.co.mz", "password": "x"}, HTTP_X_FORWARDED_FOR="2.2.2.2, 9.9.9.9")
        self.assertEqual(resp.status_code, 429)

    @override_settings(LOGIN_RATE_LIMIT_ATTEMPTS=3, TRUSTED_PROXY_COUNT=1)
    def test_attacker_cannot_lock_out_owner_from_another_ip(self):
        url = reverse("accounts:login")
        for _ in range(3):
            self.client.post(url, {"username": "v@exemplo.co.mz", "password": "x"}, HTTP_X_FORWARDED_FOR="9.9.9.9")
        resp = self.client.post(url, {"username": "v@exemplo.co.mz", "password": "Corrida!2026x"}, HTTP_X_FORWARDED_FOR="5.5.5.5")
        self.assertEqual(resp.status_code, 302)

    def test_regenerate_card_token_invalidates_old_link(self):
        self.client.force_login(self.user)
        old = self.user.card_token
        self.assertEqual(self.client.post(reverse("accounts:card_regenerate")).status_code, 302)
        self.user.refresh_from_db()
        self.assertNotEqual(self.user.card_token, old)
        self.assertEqual(self.client.get(reverse("accounts:verify", args=[old])).status_code, 404)
        self.assertEqual(self.client.get(reverse("accounts:verify", args=[self.user.card_token])).status_code, 200)
