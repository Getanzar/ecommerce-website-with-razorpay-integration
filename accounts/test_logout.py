from html.parser import HTMLParser

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse


class LogoutFormParser(HTMLParser):
    def __init__(self, action):
        super().__init__()
        self.action = action
        self.in_logout = False
        self.token = None
        self.method = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "form":
            self.in_logout = attrs.get("action") == self.action
            if self.in_logout:
                self.method = attrs.get("method")
        if tag == "input" and self.in_logout and attrs.get("name") == "csrfmiddlewaretoken":
            self.token = attrs.get("value")

    def handle_endtag(self, tag):
        if tag == "form":
            self.in_logout = False


class WebsiteLogoutTests(TestCase):
    def test_storefront_logout_form_ends_session_with_csrf(self):
        client = Client(enforce_csrf_checks=True)
        user = get_user_model().objects.create_user("logout-buyer", password="test-password")
        client.force_login(user)
        response = client.get("/")
        self.assertEqual(response.status_code, 200)
        parser = LogoutFormParser(reverse("logout"))
        parser.feed(response.content.decode())
        self.assertEqual(parser.method, "post")
        self.assertTrue(parser.token)
        self.assertEqual(client.post(reverse("logout")).status_code, 403)
        self.assertIn("_auth_user_id", client.session)
        response = client.post(reverse("logout"), {"csrfmiddlewaretoken": parser.token})
        self.assertRedirects(response, "/")
        self.assertNotIn("_auth_user_id", client.session)

    def test_get_logout_does_not_end_session(self):
        user = get_user_model().objects.create_user("logout-get-buyer")
        self.client.force_login(user)
        self.assertEqual(self.client.get(reverse("logout")).status_code, 405)
        self.assertIn("_auth_user_id", self.client.session)
