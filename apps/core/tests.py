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
