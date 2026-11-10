"""Editor usability changes retain upload and permission boundaries."""
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse

from .models import Actor, Episode, Movie, Order, Plan, Room, User


class AdminMetadataTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_superuser('editor-admin', 'editor-admin@example.test', 'Test-password-174!')
        cls.staff = User.objects.create_user('editor-staff', 'editor-staff@example.test', is_staff=True)
        cls.movie = Movie.objects.create(title='Example movie', slug='example-movie', description='Example', published=True)
        cls.episode = Episode.objects.create(movie=cls.movie, title='First episode', status='ready', duration=600, source='originals/private-movie.mp4')
        cls.room = Room.objects.create(name='Friday movie night', host=cls.admin, episode=cls.episode)
        cls.plan = Plan.objects.create(name='Monthly', price=59000, days=30)
        cls.order = Order.objects.create(user=cls.staff, plan=cls.plan, amount=59000, days=30)
        cls.actor = Actor.objects.create(name='Searchable actor', bio='Actor biography')
        Actor.objects.create(name='Different performer')

    def setUp(self):
        self.client.force_login(self.admin)

    def test_private_episode_editor_never_renders_or_accepts_replacement_source(self):
        response = self.client.get(reverse('admin:cinema_episode_change', args=[self.episode.pk]))
        self.assertEqual(response.status_code, 200)
        form = response.context['adminform'].form
        self.assertNotIn('source', form.fields)
        self.assertNotIn('status', form.fields)
        self.assertNotIn('duration', form.fields)
        self.assertNotContains(response, self.episode.source.name)

    def test_room_list_uses_readable_room_host_and_movie_information(self):
        response = self.client.get(reverse('admin:cinema_room_changelist'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.room.name)
        self.assertContains(response, self.movie.title)
        self.assertContains(response, self.admin.username)
        self.assertContains(response, f'<a href="{reverse("admin:cinema_room_change", args=[self.room.pk])}">{self.room.name}</a>', html=True)

    def test_actor_search_filters_actual_results(self):
        response = self.client.get(reverse('admin:cinema_actor_changelist'), {'q': 'Searchable'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(list(response.context['cl'].result_list), [self.actor])

    def test_order_editor_cannot_settle_payments_or_grant_vip(self):
        change_url = reverse('admin:cinema_order_change', args=[self.order.pk])
        response = self.client.get(change_url)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context['adminform'].form.fields)
        self.assertEqual(self.client.get(reverse('admin:cinema_order_add')).status_code, 403)
        self.assertEqual(self.client.get(reverse('admin:cinema_order_delete', args=[self.order.pk])).status_code, 403)
        self.client.post(change_url, {'amount': 1, 'days': 365, 'status': 'paid', '_save': 'Save'})
        self.order.refresh_from_db()
        self.staff.refresh_from_db()
        self.assertEqual((self.order.amount, self.order.days, self.order.status), (59000, 30, 'pending'))
        self.assertIsNone(self.staff.vip_until)

    def test_account_editor_retains_django_model_permission_checks(self):
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get(reverse('admin:cinema_user_changelist')).status_code, 403)
        self.assertEqual(self.client.get(reverse('admin:cinema_user_add')).status_code, 403)
        self.assertEqual(self.client.post(reverse('admin:cinema_user_change', args=[self.staff.pk]), {'is_superuser': 'on'}).status_code, 403)
        self.staff.refresh_from_db()
        self.assertFalse(self.staff.is_superuser)
        self.staff.user_permissions.add(Permission.objects.get(content_type__app_label='cinema', content_type__model='user', codename='view_user'))
        self.assertEqual(self.client.get(reverse('admin:cinema_user_changelist')).status_code, 200)
        self.assertEqual(self.client.get(reverse('admin:cinema_user_add')).status_code, 403)
        self.assertEqual(self.client.post(reverse('admin:cinema_user_change', args=[self.staff.pk]), {'is_superuser': 'on'}).status_code, 403)

    def test_grouped_movie_form_preserves_model_validation(self):
        response = self.client.post(reverse('admin:cinema_movie_add'), {
            'title': 'Invalid source score', 'slug': 'invalid-source-score', 'description': 'Example',
            'kind': 'movie', 'year': '2026', 'country': 'Việt Nam', 'artwork': 'orbit',
            'imdb_rating': '8.2', 'published': 'on',
        })
        self.assertEqual(response.status_code, 200)
        self.assertIn('imdb_id', response.context['adminform'].form.errors)
        self.assertFalse(Movie.objects.filter(slug='invalid-source-score').exists())

    def test_actual_editor_responses_retain_vietnamese_labels_through_upload_form_subclasses(self):
        for url in (reverse('admin:cinema_movie_add'), reverse('admin:cinema_movie_change', args=[self.movie.pk])):
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200)
                for name, label in (('title', 'Tên phim'), ('slug', 'Đường dẫn'), ('description', 'Giới thiệu phim'), ('kind', 'Loại phim'), ('year', 'Năm phát hành'), ('country', 'Quốc gia'), ('poster', 'Ảnh bìa'), ('actors', 'Diễn viên'), ('published', 'Hiển thị trong thư viện')):
                    self.assertEqual(response.context['adminform'].form.fields[name].label, label)
                    suffix = '' if name == 'published' else ':'
                    self.assertContains(response, f'for="id_{name}">{label}{suffix}</label>')
                self.assertContains(response, 'Tự tạo từ tên phim; dùng chữ thường, số và dấu gạch nối.')
        episode = self.client.get(reverse('admin:cinema_episode_add'))
        self.assertContains(episode, 'for="id_title">Tên tập phim:</label>')
        self.assertContains(episode, 'for="id_source">File phim gốc:</label>')
