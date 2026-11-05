from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import Category, Episode, History, Movie, Rating, Watchlist


class CatalogExperienceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.viewer = get_user_model().objects.create_user('catalog-viewer', 'catalog-viewer@example.test', 'Test-password-379!')
        cls.other = get_user_model().objects.create_user('catalog-other', 'catalog-other@example.test', 'Test-password-481!')
        cls.genre = Category.objects.create(name='Hoạt hình', slug='hoat-hinh')
        cls.ready = Movie.objects.create(title='A playable short', slug='playable-short', description='Animation', published=True)
        cls.ready.categories.add(cls.genre)
        Episode.objects.create(movie=cls.ready, number=1, title='Preparing', status='pending')
        cls.episode = Episode.objects.create(movie=cls.ready, number=2, title='Complete film', status='ready', duration=596)
        cls.unready = Movie.objects.create(title='A future short', slug='future-short', description='Animation', published=True)
        cls.unready.categories.add(cls.genre)
        cls.hidden = Movie.objects.create(title='Private film', slug='private-film', description='Animation', published=False)
        cls.hidden_episode = Episode.objects.create(movie=cls.hidden, title='Hidden', status='ready', duration=600)

    def test_home_features_a_real_playable_episode_over_newer_unready_titles(self):
        response = self.client.get(reverse('catalog'))
        self.assertEqual(response.status_code, 200)
        featured = response.context['featured']
        self.assertEqual(featured.pk, self.ready.pk)
        self.assertEqual(featured.ready_episode_id, self.episode.pk)
        self.assertEqual(featured.duration_minutes, 10)
        self.assertFalse(response.context['is_browsing'])
        shelf_movies = [movie.pk for shelf in response.context['shelves'] for movie in shelf['movies']]
        self.assertNotIn(self.hidden.pk, shelf_movies)
        self.assertEqual(response.context['continue_watching'], [])

    def test_every_featured_slide_has_a_ready_episode_while_upcoming_films_remain_discoverable(self):
        response = self.client.get(reverse('catalog'))
        self.assertEqual([film.pk for film in response.context['featured_movies']], [self.ready.pk])
        self.assertNotContains(response, 'id="feature-' + str(self.unready.pk) + '"')
        self.assertContains(response, reverse('movie', args=[self.unready.slug]))
        self.assertContains(response, 'Đang chuẩn bị')

    def test_catalog_without_ready_videos_keeps_cards_without_promoting_a_fake_feature(self):
        self.episode.status = 'processing'
        self.episode.save(update_fields=['status'])
        response = self.client.get(reverse('catalog'))
        self.assertIsNone(response.context['featured'])
        self.assertEqual(response.context['featured_movies'], [])
        self.assertNotContains(response, 'data-feature-stage')
        self.assertContains(response, reverse('movie', args=[self.ready.slug]))

    def test_browse_keeps_combined_filters_and_rating_order(self):
        second = Movie.objects.create(title='Another short', slug='another-short', description='Animation', published=True)
        second.categories.add(self.genre)
        series = Movie.objects.create(title='Short series', slug='short-series', description='Animation', published=True, kind='series')
        series.categories.add(self.genre)
        Rating.objects.create(movie=self.ready, user=self.viewer, score=5)
        Rating.objects.create(movie=second, user=self.viewer, score=3)
        response = self.client.get(reverse('catalog'), {'q': 'short', 'category': self.genre.slug, 'kind': 'movie', 'sort': 'rating'})
        self.assertTrue(response.context['is_browsing'])
        self.assertEqual([movie.pk for movie in response.context['page']], [self.ready.pk, second.pk, self.unready.pk])
        self.assertEqual(response.context['shelves'], [])
        self.assertEqual(response.context['continue_watching'], [])

    def test_continue_watching_is_personal_and_only_contains_playable_unfinished_films(self):
        History.objects.create(user=self.viewer, episode=self.episode, position=149)
        History.objects.create(user=self.viewer, episode=self.hidden_episode, position=120)
        History.objects.create(user=self.other, episode=self.episode, position=300)
        self.client.force_login(self.viewer)
        response = self.client.get(reverse('catalog'))
        cards = response.context['continue_watching']
        self.assertEqual(len(cards), 1)
        self.assertEqual(cards[0].episode_id, self.episode.pk)
        self.assertEqual(cards[0].progress_percent, 25)
        self.assertEqual(cards[0].remaining_minutes, 8)
        History.objects.filter(user=self.viewer, episode=self.episode).update(position=596)
        self.assertEqual(self.client.get(reverse('catalog')).context['continue_watching'], [])

    def test_detail_and_library_provide_real_watch_targets_and_bounded_progress(self):
        response = self.client.get(reverse('movie', args=[self.ready.slug]))
        self.assertEqual(response.context['first_ready_episode'].pk, self.episode.pk)
        self.assertEqual(response.context['movie'].ready_episode_id, self.episode.pk)
        self.client.force_login(self.viewer)
        Watchlist.objects.create(user=self.viewer, movie=self.ready)
        History.objects.create(user=self.viewer, episode=self.episode, position=597)
        response = self.client.get(reverse('library'))
        self.assertEqual(response.context['movies'][0].ready_episode_id, self.episode.pk)
        self.assertEqual(response.context['history'][0].progress_percent, 100)
        self.assertEqual(response.context['history'][0].remaining_minutes, 0)

    def test_vip_shelf_browse_link_filters_to_vip_movies(self):
        self.unready.is_vip = True
        self.unready.save(update_fields=['is_vip'])
        home = self.client.get(reverse('catalog'))
        shelf = next(shelf for shelf in home.context['shelves'] if '?access=vip' in shelf['href'])
        self.assertTrue(shelf['preparing'])
        self.assertContains(home, 'class="shelf-availability-note"')
        self.assertContains(home, 'Những bộ phim VIP đang được chuẩn bị.')
        response = self.client.get(shelf['href'])
        self.assertTrue(response.context['is_browsing'])
        self.assertEqual([movie.pk for movie in response.context['page']], [self.unready.pk])


class LandingPageTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from .models import Plan
        cls.viewer_password = 'Welcome-flow-test-849!'
        cls.viewer = get_user_model().objects.create_user('welcome-viewer', 'welcome-viewer@example.test', cls.viewer_password)
        cls.public = Movie.objects.create(title='Public landing film', slug='landing-public', published=True)
        cls.hidden = Movie.objects.create(title='Private landing film', slug='landing-private', published=False)
        cls.episode = Episode.objects.create(movie=cls.public, title='Published episode', status='ready', duration=600)
        Episode.objects.create(movie=cls.hidden, title='Private episode', status='ready', duration=600)
        cls.active_plan = Plan.objects.create(name='Available VIP', price=59000, days=30)
        Plan.objects.create(name='Retired VIP', price=1000, days=30, active=False)

    def test_public_landing_uses_only_published_movies_and_active_plans(self):
        response = self.client.get(reverse('landing'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'cinema/landing.html')
        self.assertEqual([film.pk for film in response.context['landing_movies']], [self.public.pk])
        self.assertEqual(response.context['featured'].ready_episode_id, self.episode.pk)
        self.assertEqual([plan.pk for plan in response.context['plans']], [self.active_plan.pk])
        self.assertEqual(response.context['free_movie_count'], 1)
        self.assertEqual(response.context['vip_movie_count'], 0)

    def test_discovery_has_a_distinct_route(self):
        self.assertEqual(reverse('landing'), '/')
        self.assertEqual(reverse('catalog'), '/browse/')
        response = self.client.get(reverse('catalog'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'cinema/catalog.html')

    def test_existing_filtered_home_bookmark_redirects_to_discovery(self):
        response = self.client.get('/', {'q': 'Public film', 'access': 'vip'})
        self.assertRedirects(response, '/browse/?q=Public+film&access=vip', fetch_redirect_response=False)

    def test_landing_trial_prefers_a_free_ready_film_and_never_opens_a_vip_trial(self):
        vip = Movie.objects.create(title='New VIP film', slug='new-vip', published=True, is_vip=True)
        vip_episode = Episode.objects.create(movie=vip, title='VIP episode', status='ready', duration=600)
        response = self.client.get(reverse('landing'))
        self.assertEqual(response.context['featured'].pk, self.public.pk)
        self.assertContains(response, reverse('watch', args=[self.episode.pk]))
        self.public.is_vip = True
        self.public.save(update_fields=['is_vip'])
        response = self.client.get(reverse('landing'))
        self.assertNotContains(response, 'Có phim miễn phí')
        self.assertNotContains(response, reverse('watch', args=[vip_episode.pk]))
        self.assertNotContains(response, 'Xem thử một bộ phim')

    def test_signed_in_visitors_still_get_the_public_welcome_header(self):
        self.client.force_login(self.viewer)
        response = self.client.get(reverse('landing'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'cinema/landing.html')
        header = response.content.decode().split('<header', 1)[1].split('</header>', 1)[0]
        self.assertIn('href="' + reverse('login') + '"', header)
        self.assertIn('Đăng nhập', header)
        self.assertIn('href="' + reverse('register') + '"', header)
        self.assertIn('Đăng ký', header)
        self.assertNotIn('Menu tài khoản', header)

    def test_signed_in_login_skips_the_form_and_preserves_safe_next(self):
        self.client.force_login(self.viewer)
        self.assertRedirects(self.client.get(reverse('login')), reverse('catalog'), fetch_redirect_response=False)
        watch_url = reverse('watch', args=[self.episode.pk])
        self.assertRedirects(self.client.get(reverse('login'), {'next': watch_url}), watch_url, fetch_redirect_response=False)
        self.assertRedirects(self.client.get(reverse('login'), {'next': 'https://other.example/watch/'}), reverse('catalog'), fetch_redirect_response=False)

    def test_signed_in_registration_returns_to_the_movie_browser(self):
        self.client.force_login(self.viewer)
        self.assertRedirects(self.client.get(reverse('register')), reverse('catalog'), fetch_redirect_response=False)
        count = get_user_model().objects.count()
        response = self.client.post(reverse('register'), {
            'username': 'unwanted-second-account', 'email': 'second@example.test',
            'password1': self.viewer_password, 'password2': self.viewer_password,
        })
        self.assertRedirects(response, reverse('catalog'), fetch_redirect_response=False)
        self.assertEqual(get_user_model().objects.count(), count)
        self.assertEqual(int(self.client.session['_auth_user_id']), self.viewer.pk)

    def test_guest_login_opens_the_movie_browser(self):
        response = self.client.post(reverse('login'), {
            'username': self.viewer.username, 'password': self.viewer_password,
        })
        self.assertRedirects(response, reverse('catalog'), fetch_redirect_response=False)
        self.assertEqual(int(self.client.session['_auth_user_id']), self.viewer.pk)
