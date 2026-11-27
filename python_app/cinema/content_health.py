"""Shared publication checks for Studio and the movie list."""
from django.db.models import Exists, OuterRef

from .models import Episode, Subtitle


HEALTH_LABELS = {
    'waiting': 'Phim công khai chưa có video sẵn sàng',
    'poster': 'Phim công khai chưa có poster riêng',
    'subtitles': 'Phim có tập sẵn sàng chưa có phụ đề',
    'draft_ready': 'Phim nháp đã có video sẵn sàng',
}


def health_queryset(movies, issue):
    ready = Episode.objects.filter(movie_id=OuterRef('pk'), status='ready')
    if issue == 'poster':
        return movies.filter(published=True, poster='')
    if issue == 'waiting':
        return movies.filter(published=True).alias(health_ready=Exists(ready)).filter(health_ready=False)
    if issue == 'draft_ready':
        return movies.filter(published=False).alias(health_ready=Exists(ready)).filter(health_ready=True)
    if issue == 'subtitles':
        without_captions = ready.alias(
            health_captions=Exists(Subtitle.objects.filter(episode_id=OuterRef('pk'))),
        ).filter(health_captions=False)
        return movies.filter(published=True).alias(health_missing_captions=Exists(without_captions)).filter(health_missing_captions=True)
    return movies.none()


def permitted_health_checks(user):
    def view(model):
        return user.has_perm(f'cinema.view_{model}') or user.has_perm(f'cinema.change_{model}')
    if not user.is_authenticated or not user.is_active or not user.is_staff or not view('movie'):
        return []
    checks = ['poster']
    if view('episode'):
        checks = ['waiting', *checks, 'draft_ready']
        if view('subtitle'):
            checks.insert(2, 'subtitles')
    return checks
