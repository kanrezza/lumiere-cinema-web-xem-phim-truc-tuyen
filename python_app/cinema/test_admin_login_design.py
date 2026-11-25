"""The custom Studio login preserves Django admin's authentication boundaries."""
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import SESSION_KEY
from django.core.cache import cache
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .models import User


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class AdminLoginExperienceTests(TestCase):
    password = 'Studio-test-password-25!'

    @classmethod
    def setUpTestData(cls):
        cls.staff = User.objects.create_user(
            'login-editor', 'login-editor@example.test', cls.password, is_staff=True,
        )
        cls.vip = User.objects.create_user(
            'login-vip', 'login-vip@example.test', cls.password,
            vip_until=timezone.now() + timedelta(days=30),
        )
        cls.inactive = User.objects.create_user(
            'login-inactive', 'login-inactive@example.test', cls.password,
            is_staff=True, is_active=False,
        )

    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        self.url = reverse('admin:login')

    def test_staff_login_preserves_destination_and_requires_csrf(self):
        client = Client(enforce_csrf_checks=True)
        destination = reverse('admin:cinema_movie_changelist') + '?q=film'
        page = client.get(self.url, {'next': destination})
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, 'id="login-form"')
        self.assertContains(page, 'name="csrfmiddlewaretoken"')
        self.assertContains(page, f'name="next" value="{destination}"')
        fields = {'username': self.staff.username, 'password': self.password, 'next': destination}
        self.assertEqual(client.post(self.url, fields).status_code, 403)
        response = client.post(self.url, fields, HTTP_X_CSRFTOKEN=client.cookies['csrftoken'].value)
        self.assertRedirects(response, destination, fetch_redirect_response=False)
        self.assertEqual(client.session[SESSION_KEY], str(self.staff.pk))

    def test_invalid_login_displays_errors_keeps_name_and_never_echoes_password(self):
        wrong_password = 'invalid-password-do-not-render'
        response = self.client.post(self.url, {
            'username': self.staff.username, 'password': wrong_password, 'next': reverse('admin:index'),
        })
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['form'].non_field_errors())
        self.assertContains(response, f'value="{self.staff.username}"')
        self.assertNotContains(response, wrong_password)
        self.assertNotIn(SESSION_KEY, self.client.session)

    def test_vip_and_inactive_staff_cannot_sign_in_to_admin(self):
        for user in (self.vip, self.inactive):
            with self.subTest(user=user.username):
                client = Client()
                response = client.post(self.url, {
                    'username': user.username, 'password': self.password, 'next': reverse('admin:index'),
                })
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.context['form'].non_field_errors())
                self.assertNotIn(SESSION_KEY, client.session)
                self.assertEqual(client.get(reverse('admin:index')).status_code, 302)

    def test_successful_login_does_not_redirect_to_an_external_next_url(self):
        response = self.client.post(self.url, {
            'username': self.staff.username, 'password': self.password, 'next': 'https://untrusted.example/collect',
        })
        self.assertRedirects(response, settings.LOGIN_REDIRECT_URL, fetch_redirect_response=False)
