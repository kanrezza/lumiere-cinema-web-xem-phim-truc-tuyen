"""Saved films and viewing-history endpoints."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from ..models import History
from ..queries import catalog_movies, continue_cards, history_cards, public_history


@login_required
def library(request):
    return render(request, 'cinema/library.html', {
        'movies': catalog_movies(request.user).filter(watchlist__user=request.user),
        'continue_watching': continue_cards(request.user, 30),
        'history': history_cards(public_history(request.user).select_related('episode__movie')[:30]),
    })


@login_required
@require_POST
def hide_continue(request, pk):
    hidden = History.objects.filter(
        user=request.user, episode__movie_id=pk, hidden_from_continue=False,
    ).update(hidden_from_continue=True)
    if hidden:
        messages.success(request, 'Đã bỏ phim khỏi mục Xem tiếp.')
    return redirect('library' if request.POST.get('source') == 'library' else 'catalog')


@login_required
@require_POST
def clear_history(request):
    History.objects.filter(user=request.user).delete()
    messages.success(request, 'Đã xóa lịch sử xem của bạn.')
    return redirect('library')
