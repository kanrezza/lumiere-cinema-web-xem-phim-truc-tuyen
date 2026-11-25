"""Reusable public catalog and viewing-history querysets."""

import math

from django.db.models import Avg, Count, F, IntegerField, OuterRef, Q, Subquery
from django.db.models.functions import Cast, Ceil

from .models import Category, Episode, History, Movie


def public_history(user):
    if not user.is_authenticated or not user.is_active:
        return History.objects.none()
    return History.objects.filter(
        user=user, episode__movie__published=True, episode__status='ready',
    ).order_by('-updated_at', '-pk')


def unfinished_history(user):
    history = public_history(user).filter(
        episode__duration__gt=0, position__gt=0, position__lt=F('episode__duration') - 1,
    )
    if user.is_authenticated and not (user.is_vip or user.is_staff):
        history = history.filter(episode__movie__is_vip=False)
    return history


def continue_cards(user, limit):
    visible = unfinished_history(user).filter(hidden_from_continue=False)
    latest = visible.filter(episode__movie_id=OuterRef('episode__movie_id')).values('pk')[:1]
    return history_cards(visible.filter(pk=Subquery(latest)).select_related('episode__movie')[:limit])


def catalog_movies(user=None):
    """Public movie cards carry a real playback target, never a placeholder URL."""
    ready = Episode.objects.filter(movie_id=OuterRef('pk'), status='ready').order_by('number', 'pk')
    movies = Movie.objects.filter(published=True).prefetch_related('categories').annotate(
        score=Avg('ratings__score'),
        ready_episode_id=Subquery(ready.values('pk')[:1]),
        duration_minutes=Cast(Ceil(Subquery(ready.values('duration')[:1]) / 60.0), IntegerField()),
    ).order_by('-created_at', '-pk')
    if user is not None and user.is_authenticated and user.is_active:
        resume = unfinished_history(user).filter(episode__movie_id=OuterRef('pk'))
        movies = movies.annotate(resume_episode_id=Subquery(resume.values('episode_id')[:1]))
    return movies


def public_categories():
    return Category.objects.annotate(
        published_count=Count('movie', filter=Q(movie__published=True), distinct=True),
    ).filter(published_count__gt=0).order_by('name')


def public_country_groups():
    """Group existing country labels without exposing draft-film metadata."""
    groups = {}
    rows = Movie.objects.filter(published=True).order_by('country').values('country').annotate(count=Count('pk'))
    for row in rows:
        raw_name = row['country'] or ''
        name = raw_name.strip()
        if not name:
            continue
        group = groups.setdefault(name.casefold(), {'name': name, 'count': 0, 'values': []})
        group['count'] += row['count']
        group['values'].append(raw_name)
        # Prefer an existing human-readable mixed-case spelling over an all-caps variant.
        if group['name'].isupper() and not name.isupper():
            group['name'] = name
    return sorted(groups.values(), key=lambda group: group['name'].casefold())


def history_cards(history):
    cards = list(history)
    for item in cards:
        duration = max(0, item.episode.duration)
        position = min(duration, max(0, item.position))
        item.progress_percent = round(position / duration * 100) if duration else 0
        item.remaining_minutes = math.ceil((duration - position) / 60)
    return cards
