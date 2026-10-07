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


class PwaInstallTests(TestCase):
    def test_ios_install_guide_and_splash_screens_are_in_pages(self):
        html = self.client.get("/").content.decode()
        self.assertIn("data-ios-install", html)
        self.assertIn("apple-touch-startup-image", html)
        self.assertIn("js/pwa.js", html)

    def test_splash_images_exist_for_every_link(self):
        import re
        from pathlib import Path

        from django.conf import settings

        html = self.client.get("/").content.decode()
        names = re.findall(r"img/splash/(splash-\d+x\d+\.png)", html)
        self.assertGreaterEqual(len(names), 10)
        for name in names:
            self.assertTrue((Path(settings.BASE_DIR) / "static/img/splash" / name).exists(), name)

    def test_manifest_has_stable_id(self):
        self.assertEqual(self.client.get("/manifest.webmanifest").json()["id"], "/")
