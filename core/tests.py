from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase
from django.urls import URLResolver, get_resolver, reverse


settings.SECRET_KEY = "test-only-not-a-production-secret"


class InitialRoutingTests(SimpleTestCase):
    def test_home_page_is_available_and_contains_brand_name(self):
        response = self.client.get(reverse("core:home"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "سَنَد")

    def test_all_initial_routes_are_available(self):
        route_names = [
            "core:home",
            "accounts:index",
            "patients:index",
            "radiology:index",
            "followups:index",
            "notifications:index",
        ]

        for route_name in route_names:
            with self.subTest(route_name=route_name):
                response = self.client.get(reverse(route_name))
                self.assertNotIn(response.status_code, {404, 500})

        admin_response = self.client.get(reverse("admin:index"))
        self.assertNotIn(admin_response.status_code, {404, 500})

    def test_application_namespaces_are_unique(self):
        namespaces = [
            pattern.namespace
            for pattern in get_resolver().url_patterns
            if isinstance(pattern, URLResolver) and pattern.namespace
        ]

        self.assertEqual(len(namespaces), len(set(namespaces)))
        self.assertEqual(
            set(namespaces),
            {
                "admin",
                "core",
                "accounts",
                "patients",
                "radiology",
                "followups",
                "notifications",
            },
        )


class AuthenticatedHomeTests(TestCase):
    def test_authenticated_user_goes_directly_to_workspace(self):
        user = get_user_model().objects.create_user(username="workspace-user")
        self.client.force_login(user)

        response = self.client.get(reverse("core:home"))

        self.assertRedirects(response, reverse("accounts:index"))
