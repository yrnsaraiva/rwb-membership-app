from django.contrib.auth import get_user_model
from django.test import TestCase


class CoreTests(TestCase):
    def test_home(self):
        self.assertContains(self.client.get("/"), "Corre")

    def test_pwa_endpoints(self):
        resp = self.client.get("/manifest.webmanifest")
        self.assertEqual(resp["Content-Type"], "application/manifest+json")
        self.assertIn(b"standalone", resp.content)
        resp = self.client.get("/sw.js")
        self.assertEqual(resp["Content-Type"], "application/javascript")
        self.assertEqual(self.client.get("/offline/").status_code, 200)

    def test_healthz(self):
        self.assertEqual(self.client.get("/healthz").json(), {"status": "ok"})

    def test_seed_demo(self):
        from django.core.management import call_command

        call_command("seed_demo", verbosity=0)
        self.assertEqual(self.client.get("/ranking/").status_code, 200)


class NativeShellTests(TestCase):
    def test_pages_load_native_bridge_and_auth_marker(self):
        resp = self.client.get("/")
        self.assertContains(resp, "js/native.js")
        self.assertNotContains(resp, 'name="rwb-auth"')
        user = get_user_model().objects.create_user("n@x.mz", "Corrida!2026x", first_name="N", is_staff=True)
        self.client.force_login(user)
        self.assertContains(self.client.get("/atividade/"), 'name="rwb-auth"')
        self.assertContains(self.client.get("/painel/"), "data-native-scan")
