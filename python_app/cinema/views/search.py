"""Small public suggestions for the header search, without viewing-history data."""

from urllib.parse import urlencode

from django.db.models import Case, Exists, IntegerField, OuterRef, Value, When
from django.http import JsonResponse
from django.urls import reverse
from django.views.decorators.http import require_GET

from ..models import Actor, Episode, Movie
from ..search import filter_actor_search, filter_movie_search, normalize_search


@require_GET
def search_suggestions(request):
    query = request.GET.get('q', '').strip()[:150]
    normalized = normalize_search(query)
    payload = {
        'query': query, 'movies': [], 'actors': [],
        'all_url': reverse('catalog') + '?' + urlencode({'q': query}),
    }
    if len(normalized) >= 2:
        ready = Episode.objects.filter(movie_id=OuterRef('pk'), status='ready')
        films = filter_movie_search(Movie.objects.filter(published=True), normalized).annotate(
            has_ready=Exists(ready),
            title_priority=Case(When(search_title__startswith=normalized, then=Value(0)), default=Value(1), output_field=IntegerField()),
        ).order_by('title_priority', '-created_at', '-pk')[:6]
        payload['movies'] = [{
            'id': film.pk, 'title': film.title,
            'meta': f'{film.year} · {film.get_kind_display()}',
            'url': reverse('movie', args=[film.slug]),
            'poster': film.poster.url if film.poster else None,
            'ready': film.has_ready, 'vip': film.is_vip,
        } for film in films]
        actors = filter_actor_search(Actor.objects.filter(movie__published=True), normalized).distinct().order_by('name', 'pk')[:3]
        payload['actors'] = [{
            'id': actor.pk, 'name': actor.name, 'url': reverse('actor', args=[actor.pk]),
        } for actor in actors]
    return JsonResponse(payload, headers={'Cache-Control': 'private, no-store'})
