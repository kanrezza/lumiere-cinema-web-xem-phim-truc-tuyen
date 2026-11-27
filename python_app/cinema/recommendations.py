"""Small, explainable discovery based only on the current viewer's public films.

No external service or fabricated affinity score is involved. Genre overlap is
ranked before actors, then country; each card explains an actual shared feature.
"""

from django.db.models import Case, Count, Exists, F, OuterRef, Q, Value, When

from .models import Episode, History, Movie, Rating, Watchlist
from .queries import catalog_movies, public_history


SEEDS_PER_SOURCE = 6
MAX_RECOMMENDATIONS = 12


def _seed_choices(user):
    choices = {}
    saved = Watchlist.objects.filter(user=user, movie__published=True).order_by('-pk')
    liked = Rating.objects.filter(user=user, score__gte=4, movie__published=True).order_by(
        F('updated_at').desc(nulls_last=True), '-pk',
    )
    history = public_history(user).filter(hidden_from_continue=False, position__gt=0)
    # A bounded recent window keeps a long series from creating an unbounded scan.
    viewed_ids = list(dict.fromkeys(history.values_list('episode__movie_id', flat=True)[:24]))[:SEEDS_PER_SOURCE]
    for movie_id in viewed_ids:
        choices[movie_id] = 'history'
    for movie_id in saved.values_list('movie_id', flat=True)[:SEEDS_PER_SOURCE]:
        choices[movie_id] = 'saved'
    for movie_id in liked.values_list('movie_id', flat=True)[:SEEDS_PER_SOURCE]:
        choices[movie_id] = 'rating'
    return choices


def _unfinished_ready_episodes(user):
    finished = History.objects.filter(
        user=user, episode_id=OuterRef('pk'), episode__duration__gt=0,
        position__gt=0, position__gte=F('episode__duration') - 1,
    )
    return Episode.objects.filter(movie_id=OuterRef('pk'), status='ready').annotate(
        finished_by_viewer=Exists(finished),
    ).filter(finished_by_viewer=False)


def _reason(movie, seeds, choices):
    genres = {item.pk for item in movie.categories.all()}
    actors = {item.pk for item in movie.actors.all()}
    matches = []
    for seed in seeds:
        genre_overlap = len(genres & seed.recommendation_genres)
        actor_overlap = len(actors & seed.recommendation_actors)
        country_overlap = bool(seed.country.strip() and movie.country == seed.country)
        if not (genre_overlap or actor_overlap or country_overlap):
            continue
        source = choices[seed.pk]
        priority = {'history': 0, 'saved': 1, 'rating': 2}[source]
        matches.append(((genre_overlap, actor_overlap, country_overlap, priority, seed.pk), seed, source))
    if not matches:
        return ''
    _, seed, source = max(matches, key=lambda item: item[0])
    if genres & seed.recommendation_genres:
        connection = 'Cùng thể loại'
    elif actors & seed.recommendation_actors:
        connection = 'Có diễn viên chung'
    else:
        connection = 'Cùng quốc gia'
    context = {
        'saved': 'trong tủ phim của bạn',
        'history': 'bạn đã xem',
        'rating': 'bạn đã đánh giá cao',
    }[source]
    return f'{connection} với “{seed.title}” {context}.'


def recommendation_shelf(user, limit=8):
    """Return ready, relevant card objects and truthful reasons, or no shelf.

    All reads are scoped to this account. Hidden history does not become a taste
    seed; drafts never enter seed names or results. A film is considered finished
    only when every ready episode has reached the existing duration−1 boundary.
    """
    if not user.is_authenticated or not user.is_active or user.erased_at:
        return None
    limit = max(1, min(int(limit), MAX_RECOMMENDATIONS))
    choices = _seed_choices(user)
    if not choices:
        return None
    dislikes = Rating.objects.filter(user=user, score__lte=2).values('movie_id')
    seeds = list(Movie.objects.filter(published=True, pk__in=choices).exclude(
        pk__in=dislikes,
    ).prefetch_related('categories', 'actors').order_by('pk'))
    if not seeds:
        return None
    genre_ids, actor_ids, countries = set(), set(), set()
    for seed in seeds:
        seed.recommendation_genres = {item.pk for item in seed.categories.all()}
        seed.recommendation_actors = {item.pk for item in seed.actors.all()}
        genre_ids.update(seed.recommendation_genres)
        actor_ids.update(seed.recommendation_actors)
        if seed.country.strip():
            countries.add(seed.country)
    if not (genre_ids or actor_ids or countries):
        return None
    candidates = catalog_movies(user).filter(ready_episode_id__isnull=False).exclude(
        pk__in=choices,
    ).exclude(pk__in=dislikes).annotate(
        shared_genres=Count('categories', filter=Q(categories__pk__in=genre_ids), distinct=True),
        shared_actors=Count('actors', filter=Q(actors__pk__in=actor_ids), distinct=True),
        shared_country=Case(When(country__in=countries, then=Value(1)), default=Value(0)),
        has_unfinished_episode=Exists(_unfinished_ready_episodes(user)),
    ).filter(
        Q(shared_genres__gt=0) | Q(shared_actors__gt=0) | Q(shared_country=1),
        has_unfinished_episode=True,
    ).prefetch_related('actors').order_by(
        '-shared_genres', '-shared_actors', '-shared_country', '-created_at', '-pk',
    )
    movies = list(candidates[:limit])
    for movie in movies:
        movie.recommendation_reason = _reason(movie, seeds, choices)
    if not movies:
        return None
    return {
        'title': 'Dành cho bạn',
        'subtitle': 'Gợi ý từ những phim bạn đã lưu, xem hoặc đánh giá cao.',
        'movies': movies,
        'href': None,
        'personalized': True,
    }
