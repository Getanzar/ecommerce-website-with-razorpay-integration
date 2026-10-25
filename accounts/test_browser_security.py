from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse


class BrowserAuthenticationLimitsTests(TestCase):
    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)

    def test_website_login_limited_by_identity_across_ip_addresses(self):
        for index in range(10):
            response = self.client.post(reverse("login"), {"username": "example", "password": "incorrect"}, REMOTE_ADDR=f"192.0.2.{index}")
            self.assertNotEqual(response.status_code, 429)
        response = self.client.post(reverse("login"), {"username": "EXAMPLE", "password": "incorrect"}, REMOTE_ADDR="192.0.2.99")
        self.assertEqual(response.status_code, 429)
        self.assertEqual(response["Retry-After"], "60")
        self.assertEqual(self.client.get(reverse("login")).status_code, 200)

    def test_admin_login_is_limited_too(self):
        for _ in range(10):
            self.client.post(reverse("admin:login"), {"username": "admin", "password": "incorrect"})
        self.assertEqual(self.client.post(reverse("admin:login"), {"username": "admin", "password": "incorrect"}).status_code, 429)

    def test_email_actions_limited_without_blocking_normal_browse(self):
        for _ in range(5):
            self.client.post(reverse("signup"), {"email": "new@example.com"})
        self.assertEqual(self.client.post(reverse("signup"), {"email": "new@example.com"}).status_code, 429)
        self.assertEqual(self.client.get(reverse("home")).status_code, 200)
