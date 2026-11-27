"""Saved films and viewing-history endpoints."""

import re
from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Case, CharField, Count, Exists, F, IntegerField, OuterRef, Q, Subquery, Value, When
from django.db.models.functions import Coalesce
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from ..models import Episode, History, User, Watchlist
from ..queries import catalog_movies, continue_cards, history_cards, public_history
from ..search import filter_movie_search


LIBRARY_STATES = (
    ('all', 'Tất cả'), ('unwatched', 'Chưa xem'), ('inprogress', 'Đang xem'),
    ('completed', 'Đã xem'), ('preparing', 'Đang chuẩn bị'),
)
LIBRARY_SORTS = (('saved', 'Mới lưu gần đây'), ('title', 'Tên phim A–Z'), ('year', 'Năm phát hành'))


def _filters(values):
    """Only reconstruct known same-page filters, never trust a submitted next URL."""
    state = values.get('status', 'all')
    sort = values.get('sort', 'saved')
    return {
        'q': values.get('q', '').strip()[:150],
        'status': state if state in dict(LIBRARY_STATES) else 'all',
        'sort': sort if sort in dict(LIBRARY_SORTS) else 'saved',
    }


def _library_url(filters, **changes):
    query = {**filters, **changes}
    values = {key: value for key, value in query.items() if value and not (
        (key == 'status' and value == 'all') or (key == 'sort' and value == 'saved')
    )}
    return reverse('library') + ('?' + urlencode(values) if values else '') + '#saved-films'


def _saved_movies(user):
    ready = Episode.objects.filter(movie_id=OuterRef('pk'), status='ready').order_by()
    ready_count = ready.values('movie_id').annotate(total=Count('pk')).values('total')
    # Match unfinished_history's one-second completion tolerance. Zero progress
    # and unknown duration never qualify as completed.
    completed_count = ready.filter(
        duration__gt=0, history__user=user, history__position__gt=0,
        history__position__gte=F('duration') - 1,
    ).values('movie_id').annotate(total=Count('pk', distinct=True)).values('total')
    started = History.objects.filter(
        user=user, episode__movie_id=OuterRef('pk'), episode__status='ready', position__gt=0,
    )
    saved = Watchlist.objects.filter(user=user, movie_id=OuterRef('pk')).values('pk')[:1]
    return catalog_movies(user).filter(watchlist__user=user).annotate(
        library_ready_count=Coalesce(Subquery(ready_count, output_field=IntegerField()), 0),
        library_completed_count=Coalesce(Subquery(completed_count, output_field=IntegerField()), 0),
        library_started=Exists(started), library_saved_id=Subquery(saved),
    ).annotate(library_state=Case(
        When(library_ready_count=0, then=Value('preparing')),
        When(library_ready_count=F('library_completed_count'), then=Value('completed')),
        When(library_started=True, then=Value('inprogress')),
        default=Value('unwatched'), output_field=CharField(),
    ))


def _locked_viewer(user_id):
    user = User.objects.select_for_update().get(pk=user_id)
    if not user.is_active or user.erased_at:
        raise PermissionDenied('Tài khoản không còn hoạt động.')
    return user


@login_required
def library(request):
    if not request.user.is_active or request.user.erased_at:
        raise PermissionDenied
    filters = _filters(request.GET)
    saved = _saved_movies(request.user)
    saved_count = saved.count()
    matching = filter_movie_search(saved, filters['q']) if filters['q'] else saved
    totals = matching.aggregate(
        all=Count('pk', distinct=True),
        **{key: Count('pk', distinct=True, filter=Q(library_state=key)) for key, _ in LIBRARY_STATES if key != 'all'},
    )
    movies = matching if filters['status'] == 'all' else matching.filter(library_state=filters['status'])
    ordering = {
        'saved': ('-library_saved_id', '-pk'),
        'title': ('search_title', 'title', 'pk'),
        'year': ('-year', '-library_saved_id', '-pk'),
    }
    page = Paginator(movies.order_by(*ordering[filters['sort']]), 24).get_page(request.GET.get('page'))
    labels = dict(LIBRARY_STATES)
    for movie in page.object_list:
        movie.library_state_label = labels[movie.library_state]
    return render(request, 'cinema/library.html', {
        'movies': page.object_list, 'saved_count': saved_count,
        'library_page': page, 'library_filters': filters, 'library_sorts': LIBRARY_SORTS,
        'library_tabs': [{'key': key, 'label': label, 'count': totals[key],
                          'active': filters['status'] == key,
                          'url': _library_url(filters, status=key)} for key, label in LIBRARY_STATES],
        'library_filtered': bool(filters['q'] or filters['status'] != 'all'),
        'library_previous': _library_url(filters, page=page.previous_page_number()) if page.has_previous() else '',
        'library_next': _library_url(filters, page=page.next_page_number()) if page.has_next() else '',
        'continue_watching': continue_cards(request.user, 30),
        'history': history_cards(public_history(request.user).select_related('episode__movie')[:30]),
    })


@login_required
@require_POST
def remove_saved(request):
    filters = _filters(request.POST)
    page = request.POST.get('page', '')
    destination = _library_url(filters, **({'page': page} if re.fullmatch(r'[1-9][0-9]{0,8}', page) else {}))
    submitted = request.POST.getlist('movies')
    if not 1 <= len(submitted) <= 100 or any(
        not re.fullmatch(r'[1-9][0-9]{0,18}', value) or int(value) > 9223372036854775807 for value in submitted
    ):
        messages.error(request, 'Chọn từ 1 đến 100 phim hợp lệ để bỏ khỏi tủ.')
        return redirect(destination)
    with transaction.atomic():
        viewer = _locked_viewer(request.user.pk)
        removed, _ = Watchlist.objects.filter(user=viewer, movie_id__in=set(map(int, submitted))).delete()
    if removed:
        messages.success(request, f'Đã bỏ {removed} phim khỏi tủ. Lịch sử xem vẫn được giữ lại.')
    else:
        messages.info(request, 'Các phim đã chọn không còn trong tủ phim của bạn.')
    return redirect(destination)


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
