from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse


class SignInLandingFlow(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="student@example.com", email="student@example.com",
            password="study-test-pass-123", first_name="Student"
        )

    def sign_in(self, suffix=""):
        return self.client.post(reverse("login") + suffix, {
            "email": "student@example.com", "password": "study-test-pass-123"
        })

    def test_first_visit_requires_sign_in(self):
        self.assertRedirects(self.client.get(reverse("landing")), reverse("login"))

    def test_login_opens_landing_and_navigation_pages_render(self):
        self.assertRedirects(self.sign_in(), reverse("landing"))
        response = self.client.get(reverse("landing"))
        self.assertContains(response, "Your learning.")
        for name in ("dashboard", "history", "profile"):
            self.assertContains(response, reverse(name))
            self.assertEqual(self.client.get(reverse(name)).status_code, 200)

    def test_safe_next_is_preserved(self):
        self.assertRedirects(self.sign_in("?next=/history/"), reverse("history"))

    def test_external_next_is_rejected(self):
        self.assertRedirects(self.sign_in("?next=https://example.com/"), reverse("landing"))

    def test_invalid_login_keeps_form_and_error(self):
        response = self.client.post(reverse("login"), {
            "email": "student@example.com", "password": "incorrect"
        })
        self.assertContains(response, "Email or password is incorrect.")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_logout_returns_to_sign_in(self):
        self.sign_in()
        response = self.client.post(reverse("logout"), follow=True)
        self.assertEqual(response.redirect_chain[-1][0], reverse("login"))
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_signup_opens_landing(self):
        response = self.client.post(reverse("signup"), {
            "name": "New Student", "email": "new@example.com",
            "password": "new-study-pass-284!", "confirm": "new-study-pass-284!"
        })
        self.assertRedirects(response, reverse("landing"))
