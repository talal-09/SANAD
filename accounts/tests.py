from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from core.models import HealthcareFacility

from .models import Role, UserProfile


settings.SECRET_KEY = "test-only-not-a-production-secret"


class StaffAuthenticationTests(TestCase):
    def setUp(self):
        self.role, _ = Role.objects.get_or_create(name="طبيب أشعة", code="radiologist")
        self.facility = HealthcareFacility.objects.create(name="مستشفى الاختبار")

    def test_staff_can_register_logout_and_login(self):
        registration_data = {
            "username": "doctor1",
            "first_name": "طبيب",
            "last_name": "اختبار",
            "email": "doctor@example.com",
            "employee_id": "EMP-100",
            "role": self.role.pk,
            "facility": self.facility.pk,
            "phone_number": "0500000000",
            "job_title": "طبيب أشعة",
            "password1": "Strong-Test-Password-391!",
            "password2": "Strong-Test-Password-391!",
        }
        response = self.client.post(reverse("accounts:register"), registration_data)

        self.assertRedirects(response, reverse("accounts:index"))
        user = get_user_model().objects.get(username="doctor1")
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)
        self.assertTrue(UserProfile.objects.filter(user=user, employee_id="EMP-100").exists())

        self.client.post(reverse("accounts:logout"))
        response = self.client.post(
            reverse("accounts:login"),
            {"username": "doctor1", "password": "Strong-Test-Password-391!"},
        )
        self.assertRedirects(response, reverse("accounts:index"))

    def test_medical_pages_require_login(self):
        for route_name in ("patients:index", "radiology:index", "followups:index", "notifications:index"):
            with self.subTest(route_name=route_name):
                response = self.client.get(reverse(route_name))
                self.assertRedirects(response, f"{reverse('accounts:login')}?next={reverse(route_name)}")

    def test_login_rejects_external_next_redirect(self):
        user = get_user_model().objects.create_user(
            username="safe-redirect-doctor",
            password="Strong-Test-Password-391!",
        )
        UserProfile.objects.create(
            user=user,
            employee_id="SAFE-REDIRECT-1",
            role=self.role,
            facility=self.facility,
        )
        response = self.client.post(
            f"{reverse('accounts:login')}?next=https://attacker.example/steal",
            {"username": user.username, "password": "Strong-Test-Password-391!"},
        )
        self.assertRedirects(response, reverse("accounts:index"))

    @override_settings(ALLOW_PUBLIC_REGISTRATION=False)
    def test_public_registration_can_be_disabled_for_production(self):
        self.assertEqual(self.client.get(reverse("accounts:register")).status_code, 404)
        self.assertNotContains(self.client.get(reverse("core:home")), "إنشاء حساب جديد")

    @override_settings(LOGIN_MAX_ATTEMPTS=2, LOGIN_LOCKOUT_SECONDS=600)
    def test_repeated_failed_logins_are_rate_limited(self):
        url = reverse("accounts:login")
        credentials = {"username": "unknown", "password": "wrong-password"}
        self.assertEqual(self.client.post(url, credentials).status_code, 200)
        self.assertEqual(self.client.post(url, credentials).status_code, 200)
        response = self.client.post(url, credentials)
        self.assertEqual(response.status_code, 429)
        self.assertEqual(response["Retry-After"], "600")
        self.assertContains(response, "محاولات دخول كثيرة", status_code=429)

    def test_authenticated_medical_pages_are_not_cached(self):
        user = get_user_model().objects.create_user(username="cache-test-doctor")
        UserProfile.objects.create(
            user=user,
            employee_id="CACHE-1",
            role=self.role,
            facility=self.facility,
        )
        self.client.force_login(user)
        response = self.client.get(reverse("accounts:index"))
        self.assertEqual(response["Cache-Control"], "private, no-store")
        self.assertEqual(response["Permissions-Policy"], "camera=(), microphone=(), geolocation=()")
        self.assertIn("default-src 'self'", response["Content-Security-Policy"])
        self.assertIn("object-src 'none'", response["Content-Security-Policy"])
        self.assertNotIn("unsafe-inline", response["Content-Security-Policy"])

    def test_logout_post_requires_csrf_token(self):
        client = self.client_class(enforce_csrf_checks=True)
        user = get_user_model().objects.create_user(username="csrf-test-doctor")
        client.force_login(user)

        response = client.post(reverse("accounts:logout"))

        self.assertEqual(response.status_code, 403)

    def test_authentication_buttons_are_always_available_to_guests(self):
        response = self.client.get(reverse("core:home"))
        self.assertContains(response, reverse("accounts:register"))
        self.assertContains(response, reverse("accounts:login"))

    def test_administrative_staff_can_open_patients_but_not_radiology(self):
        role = Role.objects.get(code="administrative-staff")
        user = get_user_model().objects.create_user(username="administrative-user")
        UserProfile.objects.create(
            user=user,
            employee_id="ADMIN-1",
            role=role,
            facility=self.facility,
        )
        self.client.force_login(user)

        self.assertEqual(self.client.get(reverse("patients:index")).status_code, 200)
        self.assertEqual(self.client.get(reverse("radiology:index")).status_code, 403)
