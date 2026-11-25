"""Public film details and trailers."""

from django.http import Http404
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_GET

from ..models import Comment, Watchlist
from ..queries import catalog_movies


def movie_detail(request, slug):
    movies = catalog_movies(request.user)
    movie = get_object_or_404(movies.prefetch_related('actors'), slug=slug)
    episodes = list(movie.episodes.all())
    first_ready_episode = next((episode for episode in episodes if episode.status == 'ready'), None)
    resume_episode_id = getattr(movie, 'resume_episode_id', None)
    resume_episode = next((episode for episode in episodes if episode.pk == resume_episode_id), None)
    related = movies.filter(categories__in=movie.categories.all()).exclude(pk=movie.pk).distinct()[:8]
    viewer_score = None
    if request.user.is_authenticated:
        viewer_score = movie.ratings.filter(user=request.user).values_list('score', flat=True).first()
    return render(request, 'cinema/movie.html', {
        'movie': movie, 'episodes': episodes, 'first_ready_episode': first_ready_episode,
        'resume_episode': resume_episode,
        'comments': movie.comments.filter(moderation_status=Comment.Status.PUBLISHED).select_related('user')[:50],
        'pending_comments': movie.comments.filter(user=request.user, moderation_status=Comment.Status.PENDING)[:3] if request.user.is_authenticated else [],
        'score': movie.score,
        'viewer_score': viewer_score,
        'rating_choices': range(5, 0, -1),
        'saved': request.user.is_authenticated and Watchlist.objects.filter(user=request.user, movie=movie).exists(),
        'related': related,
    })


@require_GET
def movie_trailer(request, slug):
    movie = get_object_or_404(catalog_movies(), slug=slug)
    if not movie.has_trailer:
        raise Http404('Phim chưa có trailer.')
    return render(request, 'cinema/trailer.html', {'movie': movie})
