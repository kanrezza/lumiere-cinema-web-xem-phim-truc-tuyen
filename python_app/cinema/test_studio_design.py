"""Dashboard data and navigation obey the same model permissions as admin."""
from datetime import timedelta
from types import SimpleNamespace

from django.contrib.auth.models import AnonymousUser, Permission
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from .models import Actor, Category, Episode, Movie, Order, Plan, Report, User
from .studio import build_dashboard_context, build_navigation
from .templatetags.studio_navigation import studio_menu, studio_model_label, studio_page_title


class StudioContextTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_superuser('studio-admin', 'studio-admin@example.test', 'Test-password-93!')
        cls.staff = User.objects.create_user('studio-editor', 'studio-editor@example.test', is_staff=True)
        cls.viewer = User.objects.create_user('studio-viewer', 'studio-viewer@example.test')
        cls.vip = User.objects.create_user('studio-vip', 'studio-vip@example.test', vip_until=timezone.now() + timedelta(days=10))
        User.objects.create_user('studio-inactive', 'studio-inactive@example.test', is_active=False, vip_until=timezone.now() + timedelta(days=10))
        cls.movie = Movie.objects.create(title='Studio feature', slug='studio-feature', description='Feature', published=True)
        Movie.objects.create(title='Draft feature', slug='draft-feature', description='Draft')
        cls.episode = Episode.objects.create(movie=cls.movie, number=1, title='Ready', status='ready')
        for number, state in enumerate(('pending', 'processing', 'failed'), 2):
            Episode.objects.create(movie=cls.movie, number=number, title=state, status=state)
        cls.plan = Plan.objects.create(name='VIP', price=59000, days=30)
        Order.objects.create(user=cls.vip, plan=cls.plan, amount=59000, days=30, status='paid')
        Order.objects.create(user=cls.vip, plan=cls.plan, amount=599000, days=365, status='pending')
        Order.objects.create(user=cls.vip, plan=cls.plan, amount=100000, days=30, status='failed')
        Report.objects.create(user=cls.vip, episode=cls.episode, description='Pending report')
        Report.objects.create(user=cls.vip, episode=cls.episode, description='Resolved report', resolved=True)

    def grant(self, *names):
        self.staff.user_permissions.add(*Permission.objects.filter(codename__in=names))
        return User.objects.get(pk=self.staff.pk)

    def test_superuser_metrics_only_count_actual_paid_orders_and_active_vips(self):
        context = build_dashboard_context(self.admin)
        self.assertEqual(context['movies_count'], 2)
        self.assertEqual(context['published_movies_count'], 1)
        self.assertEqual(context['draft_count'], 1)
        self.assertEqual(context['users_count'], 5)
        self.assertEqual(context['vip_count'], 1)
        self.assertEqual(context['paid_count'], 1)
        self.assertEqual(context['revenue'], 59000)
        self.assertEqual(context['ready_episodes_count'], 1)
        self.assertEqual(context['processing_episodes_count'], 2)
        self.assertEqual(context['failed_episodes_count'], 1)
        self.assertEqual(context['unresolved_reports_count'], 1)
        self.assertEqual(list(context['reports'].values_list('description', flat=True)), ['Pending report'])

    def test_unprivileged_accounts_get_no_dashboard_data_or_navigation(self):
        for user in (AnonymousUser(), self.viewer, self.vip):
            with self.subTest(user=str(user)), self.assertNumQueries(0):
                context = build_dashboard_context(user)
                self.assertFalse(context['has_permission'])
                self.assertIsNone(context['movies_count'])
                self.assertIsNone(context['revenue'])
                self.assertEqual(context['episodes'], [])
                self.assertEqual(context['orders'], [])
                self.assertEqual(build_navigation(user), [])

    def test_staff_without_model_permissions_cannot_see_aggregate_or_row_data(self):
        context = build_dashboard_context(self.staff)
        self.assertTrue(context['has_permission'])
        self.assertFalse(context['dashboard_available'])
        for name in ('movies_count', 'users_count', 'vip_count', 'revenue', 'ready_episodes_count', 'unresolved_reports_count'):
            self.assertIsNone(context[name])
        self.assertEqual(context['episodes'], [])
        self.assertEqual(context['orders'], [])
        self.assertEqual(context['reports'], [])
        self.assertEqual([item['label'] for section in build_navigation(self.staff) for item in section['items']], ['Tổng quan'])

    def test_model_permissions_only_expose_the_authorized_domain(self):
        staff = self.grant('view_movie', 'view_episode')
        context = build_dashboard_context(staff)
        self.assertEqual(context['movies_count'], 2)
        self.assertEqual(context['ready_episodes_count'], 1)
        self.assertFalse(context['can_add_movie'])
        self.assertIsNone(context['users_count'])
        self.assertIsNone(context['revenue'])
        self.assertEqual(context['orders'], [])
        menu = build_navigation(staff, reverse('admin:cinema_movie_add'))
        items = [item for section in menu for item in section['items']]
        self.assertEqual([item['label'] for item in items], ['Tổng quan', 'Phim', 'Tập phim'])
        self.assertTrue(next(item for item in items if item['label'] == 'Phim')['active'])

    def test_add_only_permission_opens_add_form_and_never_exposes_inventory(self):
        staff = self.grant('add_movie')
        context = build_dashboard_context(staff)
        self.assertTrue(context['can_add_movie'])
        self.assertFalse(context['can_manage_movies'])
        self.assertIsNone(context['movies_count'])
        item = build_navigation(staff)[1]['items'][0]
        self.assertEqual(item['url'], reverse('admin:cinema_movie_add'))

    def test_metadata_only_staff_keep_their_navigation_without_other_domain_totals(self):
        staff = self.grant('view_actor')
        context = build_dashboard_context(staff)
        self.assertTrue(context['dashboard_available'])
        self.assertIsNone(context['movies_count'])
        self.assertIsNone(context['users_count'])
        self.assertIsNone(context['revenue'])
        self.assertEqual([item['label'] for section in build_navigation(staff) for item in section['items']], ['Tổng quan', 'Diễn viên'])

    def test_order_view_permission_exposes_payments_without_user_inventory(self):
        staff = self.grant('view_order')
        context = build_dashboard_context(staff)
        self.assertTrue(context['can_view_orders'])
        self.assertEqual(context['revenue'], 59000)
        self.assertEqual(context['paid_count'], 1)
        self.assertEqual(context['orders'].count(), 3)
        self.assertIsNone(context['users_count'])
        self.assertIsNone(context['vip_count'])

    def test_navigation_never_runs_content_count_queries(self):
        self.admin.get_all_permissions()
        with self.assertNumQueries(0):
            menu = build_navigation(self.admin, '/studio/')
        self.assertTrue(menu[0]['items'][0]['active'])
        self.assertEqual(menu[-1]['items'][0]['label'], 'Nhóm quyền')

    def test_inactive_superuser_is_not_a_studio_user(self):
        self.admin.is_active = False
        context = build_dashboard_context(self.admin)
        self.assertFalse(context['has_permission'])
        self.assertIsNone(context['revenue'])
        self.assertEqual(build_navigation(self.admin), [])

    def test_template_tags_localize_display_without_mutating_model_metadata(self):
        original_name = Movie._meta.verbose_name
        request = SimpleNamespace(user=self.admin, path='/admin/cinema/movie/')
        self.assertTrue(studio_menu({'request': request}))
        self.assertEqual(studio_model_label(Movie._meta), 'Phim')
        self.assertEqual(studio_page_title({'request': request, 'opts': Movie._meta, 'cl': object()}), 'Phim')
        self.assertEqual(studio_page_title({'opts': Movie._meta, 'add': True}), 'Thêm phim')
        self.assertEqual(studio_page_title({'opts': Movie._meta, 'change': True}), 'Chỉnh sửa phim')
        self.assertEqual(studio_page_title({'request': SimpleNamespace(path='/admin/login/')}), 'Đăng nhập quản trị')
        self.assertEqual(studio_page_title({'title': 'Xóa bản ghi'}), 'Xóa bản ghi')
        self.assertEqual(Movie._meta.verbose_name, original_name)

    def test_both_dashboard_routes_render_the_same_shell_and_actual_metrics(self):
        self.client.force_login(self.admin)
        for url in (reverse('studio'), reverse('admin:index')):
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200)
                self.assertTemplateUsed(response, 'studio/dashboard.html')
                self.assertTemplateUsed(response, 'admin/base_site.html')
                self.assertContains(response, 'id="studio-sidebar"')
                self.assertContains(response, 'studio.css')
                self.assertContains(response, 'theme.js')
                self.assertContains(response, 'Tổng quan hệ thống')
                self.assertContains(response, '59.000')
                self.assertEqual(response.context['movies_count'], 2)
                self.assertEqual(response.context['revenue'], 59000)
                self.assertEqual(response.context['paid_count'], 1)

    def test_anonymous_users_are_redirected_to_the_appropriate_login(self):
        response = self.client.get(reverse('studio'))
        self.assertRedirects(response, reverse('login') + '?next=' + reverse('studio'), fetch_redirect_response=False)
        response = self.client.get(reverse('admin:index'))
        self.assertRedirects(response, reverse('admin:login') + '?next=' + reverse('admin:index'), fetch_redirect_response=False)

    def test_normal_user_cannot_open_dashboard_or_admin_lists(self):
        self.client.force_login(self.viewer)
        self.assertEqual(self.client.get(reverse('studio')).status_code, 403)
        self.assertEqual(self.client.get(reverse('admin:cinema_movie_changelist')).status_code, 302)

    def test_http_staff_dashboard_does_not_disclose_unauthorized_stats_or_navigation(self):
        staff = self.grant('view_movie')
        self.client.force_login(staff)
        response = self.client.get(reverse('studio'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'aria-label="Quản lý thư viện phim"')
        self.assertNotContains(response, 'href="' + reverse('admin:cinema_user_changelist') + '"')
        self.assertNotContains(response, 'href="' + reverse('admin:cinema_order_changelist') + '"')
        self.assertNotContains(response, 'Doanh thu xác nhận')
        self.assertNotContains(response, '59.000')
        self.assertIsNone(response.context['users_count'])
        self.assertIsNone(response.context['revenue'])
        self.assertEqual(self.client.get(reverse('admin:cinema_user_changelist')).status_code, 403)

    def test_admin_actor_create_update_preserves_validation_and_search_fields(self):
        self.client.force_login(self.admin)
        url = reverse('admin:cinema_actor_add')
        invalid = self.client.post(url, {'name': '', 'bio': 'Missing name'})
        self.assertEqual(invalid.status_code, 200)
        self.assertTrue(invalid.context['adminform'].form.errors)
        self.assertFalse(Actor.objects.exists())
        response = self.client.post(url, {'name': 'Diễn viên thử', 'bio': 'A test-only biography', '_save': 'Lưu'})
        self.assertRedirects(response, reverse('admin:cinema_actor_changelist'), fetch_redirect_response=False)
        actor = Actor.objects.get(name='Diễn viên thử')
        self.assertEqual(actor.search_name, 'dien vien thu')
        response = self.client.post(reverse('admin:cinema_actor_change', args=[actor.pk]), {
            'name': 'Tên đã đổi', 'bio': 'Updated biography', '_save': 'Lưu',
        })
        self.assertEqual(response.status_code, 302)
        actor.refresh_from_db()
        self.assertEqual(actor.name, 'Tên đã đổi')
        self.assertEqual(actor.search_name, 'ten da doi')

    def test_admin_writes_still_enforce_csrf_and_model_permissions(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.admin)
        url = reverse('admin:cinema_category_add')
        self.assertEqual(client.post(url, {'name': 'Test genre', 'slug': 'test-genre'}).status_code, 403)
        self.assertFalse(Category.objects.exists())
        self.assertEqual(client.get(url).status_code, 200)
        token = client.cookies['csrftoken'].value
        self.assertEqual(client.post(url, {'name': 'Test genre', 'slug': 'test-genre'}, HTTP_X_CSRFTOKEN=token).status_code, 302)
        self.assertTrue(Category.objects.filter(slug='test-genre').exists())
        staff = self.grant('view_actor')
        self.client.force_login(staff)
        self.assertEqual(self.client.post(reverse('admin:cinema_actor_add'), {'name': 'Unauthorized', 'bio': ''}).status_code, 403)
        self.assertFalse(Actor.objects.filter(name='Unauthorized').exists())

    def test_movie_list_keeps_search_filter_and_sort_behavior(self):
        self.client.force_login(self.admin)
        Movie.objects.filter(pk=self.movie.pk).update(year=2008)
        url = reverse('admin:cinema_movie_changelist')
        response = self.client.get(url, {'q': 'Studio', 'published__exact': '1', 'o': '2'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual([movie.pk for movie in response.context['cl'].result_list], [self.movie.pk])
        self.assertContains(response, 'Studio feature')
        self.assertNotContains(response, '>Draft feature<')
        self.assertContains(response, f'<a href="{url}">Xem tất cả</a>', html=True)
        response = self.client.get(url, {'o': '2'})
        self.assertEqual([movie.title for movie in response.context['cl'].result_list], ['Studio feature', 'Draft feature'])

    def test_movie_form_uses_searchable_relations_and_keeps_admin_media(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse('admin:cinema_movie_add'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'admin-autocomplete')
        self.assertContains(response, 'admin/js/autocomplete.js')
        self.assertContains(response, 'admin/js/prepopulate.js')
        self.assertContains(response, 'admin/js/vendor/select2/select2.full')
        self.assertNotContains(response, 'admin/js/SelectFilter2.js')
        self.assertContains(response, 'Thông tin cơ bản')
        self.assertContains(response, 'Thể loại và diễn viên')
