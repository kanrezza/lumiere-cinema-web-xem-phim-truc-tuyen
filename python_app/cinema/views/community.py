"""Viewer watchlists, film comments and ratings."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views.decorators.http import require_POST

from ..models import Comment, Movie, Rating, Watchlist


@login_required
@require_POST
def watchlist_toggle(request, pk):
    movie = get_object_or_404(Movie, pk=pk, published=True)
    item, created = Watchlist.objects.get_or_create(user=request.user, movie=movie)
    if not created: item.delete()
    return redirect('movie', slug=movie.slug)


@login_required
@require_POST
def comment(request, pk):
    movie = get_object_or_404(Movie, pk=pk, published=True)
    content = request.POST.get('content', '').strip()
    if 1 <= len(content) <= 1000:
        submitted = Comment.objects.create(user=request.user, movie=movie, content=content)
        if submitted.moderation_status == Comment.Status.PENDING:
            messages.info(request, 'Bình luận đã được gửi và đang chờ duyệt.')
    return redirect(reverse('movie', args=[movie.slug]) + '#discussion')


@login_required
@require_POST
def rate(request, pk):
    movie = get_object_or_404(Movie, pk=pk, published=True)
    try: score = int(request.POST.get('score', 0))
    except ValueError: score = 0
    if 1 <= score <= 5: Rating.objects.update_or_create(user=request.user, movie=movie, defaults={'score': score})
    return redirect('movie', slug=movie.slug)


@login_required
@require_POST
def delete_comment(request, pk):
    comment = get_object_or_404(Comment.objects.select_related('movie'), pk=pk)
    if comment.user_id != request.user.pk and not request.user.has_perm('cinema.delete_comment'):
        if comment.moderation_status != Comment.Status.PUBLISHED:
            raise Http404
        raise PermissionDenied
    slug = comment.movie.slug
    comment.delete()
    return redirect('movie', slug=slug)
