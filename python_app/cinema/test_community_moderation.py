from django.contrib.admin.models import LogEntry
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse

from .models import Comment, Episode, Movie, Rating, Room, User
from .moderation import classify_comment_v1


class CommunityModerationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.viewer = User.objects.create_user('nguoixem', 'viewer@example.test')
        cls.other = User.objects.create_user('viewer-other', 'other@example.test')
        cls.admin = User.objects.create_superuser('community-admin', 'community@example.test')
        cls.reader = User.objects.create_user('community-reader', 'reader@example.test', is_staff=True)
        cls.reader.user_permissions.add(Permission.objects.get(codename='view_comment'))
        cls.movie = Movie.objects.create(title='Hành trình phía Bắc', slug='hanh-trinh-phia-bac', published=True, kind='series')
        cls.second_movie = Movie.objects.create(title='Dòng sông xanh', slug='dong-song-xanh', published=True)

    def submit(self, content):
        return self.client.post(reverse('comment', args=[self.movie.pk]), {'content': content}, follow=True)

    def test_rules_flag_context_and_preserve_normally_accented_words(self):
        cases = (
            ('DÂN miền Bắc toàn lũ ngU!', 'regional'),
            ('dat nuoc nay rac ruoi', 'country_party'),
            ('Cả lũ! ĐỘ\u200b ngu, cút đi.', 'harassment'),
            ('xin clip sex', 'sensitive'),
            ('DỊCH VỤ rất tốt! Mẹ kiếp.', 'profanity'),
        )
        for text, reason in cases:
            with self.subTest(reason=reason):
                self.assertIn(reason, classify_comment_v1(text))
        for text in ('Cốt truyện lấy bối cảnh Bắc Kỳ.', 'Người miền Trung đã ngủ rồi.',
                     'Tôi phản đối Đảng về chính sách này.', 'Đổ ngũ cốc vào bát.'):
            with self.subTest(text=text):
                self.assertEqual(classify_comment_v1(text), {})

    def test_comment_queue_preserves_context_and_publishes_only_after_review(self):
        self.client.force_login(self.viewer)
        neutral = 'Phim kể về một gia đình miền Bắc. Tôi không đồng ý với chính sách của Đảng trong phim.'
        criticism = 'Phim dở, nhịp phim chậm và cái kết rất tệ.'
        flagged = 'Đồ ngu, cút đi!'
        self.submit(neutral)
        self.submit(criticism)
        response = self.submit(flagged)
        pending = Comment.objects.get(content=flagged)
        self.assertEqual(pending.moderation_status, Comment.Status.PENDING)
        self.assertTrue(pending.moderation_matches)
        self.assertContains(response, 'Bình luận của bạn đang chờ duyệt')
        self.assertContains(response, flagged)

        movie_url = reverse('movie', args=[self.movie.slug])
        self.client.force_login(self.other)
        response = self.client.get(movie_url)
        self.assertContains(response, neutral)
        self.assertContains(response, criticism)
        self.assertNotContains(response, flagged)
        self.assertEqual(self.client.post(reverse('delete_comment', args=[pending.pk])).status_code, 404)

        self.client.force_login(self.admin)
        admin_url = reverse('admin:cinema_comment_changelist')
        self.client.post(admin_url, {'action': 'approve_comments', '_selected_action': pending.pk, 'index': 0})
        pending.refresh_from_db()
        self.assertEqual(pending.moderation_status, Comment.Status.PUBLISHED)
        self.assertTrue(LogEntry.objects.filter(user=self.admin, object_id=str(pending.pk)).exists())
        self.client.logout()
        self.assertContains(self.client.get(movie_url), flagged)

        self.client.force_login(self.admin)
        self.client.post(admin_url, {'action': 'hide_comments', '_selected_action': pending.pk, 'index': 0})
        pending.refresh_from_db()
        self.assertEqual(pending.moderation_status, Comment.Status.HIDDEN)
        self.client.logout()
        self.assertNotContains(self.client.get(movie_url), flagged)

    def test_comment_filters_combine_movie_status_and_secondary_reason(self):
        flagged = Comment.objects.create(user=self.viewer, movie=self.movie, content='Bình luận cần duyệt')
        Comment.objects.filter(pk=flagged.pk).update(
            moderation_status=Comment.Status.PENDING,
            moderation_reason=Comment.Reason.REGIONAL,
            moderation_matches={'regional': ['từ vùng miền'], 'profanity': ['từ tục']},
        )
        Comment.objects.create(user=self.viewer, movie=self.movie, content='Bình luận công khai')
        Comment.objects.create(user=self.other, movie=self.second_movie, content='Bình luận phim khác')

        self.client.force_login(self.reader)
        url = reverse('admin:cinema_comment_changelist')
        response = self.client.get(url, {'movie': self.movie.pk, 'moderation_status__exact': 'pending', 'moderation_reason': 'profanity'})
        self.assertEqual([row.pk for row in response.context['cl'].result_list], [flagged.pk])
        self.assertContains(response, self.movie.title)
        self.assertContains(response, 'Tất cả bình luận')
        self.assertNotContains(response, 'Bình luận phim khác')
        self.assertNotContains(response, 'approve_comments')

        self.client.post(url, {'action': 'approve_comments', '_selected_action': flagged.pk, 'index': 0})
        flagged.refresh_from_db()
        self.assertEqual(flagged.moderation_status, Comment.Status.PENDING)
        denied = self.client.get(reverse('admin:index'))
        self.assertContains(denied, flagged.content)
        self.assertNotContains(denied, 'Đánh giá gần đây')

    def test_rating_filter_identifies_the_movie_and_keeps_score_choices(self):
        self.client.force_login(self.viewer)
        self.client.post(reverse('rate', args=[self.movie.pk]), {'score': 4})
        rating = Rating.objects.get(user=self.viewer, movie=self.movie)
        Rating.objects.create(user=self.viewer, movie=self.second_movie, score=5)
        self.assertIsNotNone(rating.updated_at)

        self.client.force_login(self.admin)
        url = reverse('admin:cinema_rating_changelist')
        response = self.client.get(url, {'movie': self.movie.pk, 'score': 4})
        self.assertEqual([row.pk for row in response.context['cl'].result_list], [rating.pk])
        self.assertContains(response, self.movie.title)
        self.assertContains(response, '1 / 5')
        self.assertContains(response, '4 / 5')
        self.assertContains(response, self.viewer.username)
        self.assertEqual(self.client.get(url, {'movie': 'bad-id'}).status_code, 200)

    def test_room_rows_show_movie_and_episode(self):
        episode = Episode.objects.create(movie=self.movie, title='Gặp nhau', number=2)
        room = Room.objects.create(host=self.viewer, episode=episode, name='Phòng thử')
        empty = Room.objects.create(host=self.viewer, name='Phòng chờ chọn phim')
        self.client.force_login(self.admin)
        unfiltered = self.client.get(reverse('admin:cinema_room_changelist'))
        self.assertContains(unfiltered, empty.name)
        self.assertContains(unfiltered, 'Chưa chọn phim')
        response = self.client.get(reverse('admin:cinema_room_changelist'), {'movie': self.movie.pk})
        self.assertEqual([row.pk for row in response.context['cl'].result_list], [room.pk])
        self.assertContains(response, self.movie.title)
        self.assertContains(response, episode.title)
