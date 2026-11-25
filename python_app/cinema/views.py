import json
import math
import re
from contextlib import nullcontext, suppress
from datetime import timedelta
from urllib.parse import urlencode
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.hashers import check_password, make_password
from django.core.cache import cache
from django.core import signing
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Avg, Q, Sum, Count, OuterRef, Subquery, F, IntegerField
from django.db.models.functions import Cast, Ceil
from django.http import FileResponse, Http404, HttpResponse, HttpResponseRedirect, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.templatetags.static import static
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.utils.crypto import salted_hmac
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST, require_GET, require_http_methods
from django.views.decorators.vary import vary_on_headers
from .forms import RegisterForm, ProfileForm, AvatarForm, RoomAccessForm
from .avatars import is_managed_avatar
from .models import *
from .payments import PAYMENT_WINDOW, checkout_key_from_token, checkout_url, issue_checkout_token, process_ipn
from .search import filter_movie_search, filter_actor_search, normalize_search


def can_watch(user, episode):
    return bool(episode and user.is_authenticated and user.is_active and episode.movie.published and episode.status == 'ready' and (not episode.movie.is_vip or user.is_vip or user.is_staff))


def require_watch(user, episode):
    if not can_watch(user, episode): raise PermissionDenied('Bạn chưa có quyền xem hoặc video chưa sẵn sàng.')


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


def directory_response(request, template_name, context, data):
    if request.headers.get('X-Lumiere-Directory') == 'vue':
        return JsonResponse(data, headers={'Cache-Control': 'private, no-store'})
    return render(request, template_name, {**context, 'directory_data': data})


@vary_on_headers('X-Lumiere-Directory')
def discovery_index(request, kind):
    query = request.GET.get('q', '').strip()[:150]
    if kind == 'countries':
        items = [{'name': group['name'], 'count': group['count'],
                  'href': reverse('catalog') + '?' + urlencode({'country': group['name']})}
                 for group in public_country_groups()]
        title, eyebrow = 'Quốc gia', 'KHÁM PHÁ THEO QUỐC GIA'
        description = 'Tìm những câu chuyện từ các nền điện ảnh có trong thư viện Lumière.'
    else:
        items = [{'name': genre.name, 'count': genre.published_count,
                  'href': reverse('catalog') + '?' + urlencode({'category': genre.slug})}
                 for genre in public_categories()]
        title, eyebrow = 'Thể loại', 'KHÁM PHÁ THEO THỂ LOẠI'
        description = 'Chọn thể loại phù hợp với tâm trạng và tìm bộ phim tiếp theo của bạn.'
    total_count = len(items)
    search_term = normalize_search(query)
    if search_term:
        items = [item for item in items if search_term in normalize_search(item['name'])]
    context = {
        'title': title, 'eyebrow': eyebrow, 'description': description,
        'discovery_kind': kind, 'items': items, 'q': query, 'total_count': total_count,
    }
    return directory_response(request, 'cinema/discovery_index.html', context, {
        'kind': kind,
        'title': title,
        'eyebrow': eyebrow,
        'description': description,
        'items': items,
        'query': query,
        'count': len(items),
        'url': reverse('countries' if kind == 'countries' else 'categories'),
        'catalogUrl': reverse('catalog'),
    })


def countries(request):
    return discovery_index(request, 'countries')


def categories(request):
    return discovery_index(request, 'categories')

def history_cards(history):
    cards = list(history)
    for item in cards:
        duration = max(0, item.episode.duration)
        position = min(duration, max(0, item.position))
        item.progress_percent = round(position / duration * 100) if duration else 0
        item.remaining_minutes = math.ceil((duration - position) / 60)
    return cards


def catalog_content_links(request):
    limits = {'q': 150, 'category': 100, 'country': 100, 'actor': 64, 'year': 32,
              'kind': 20, 'sort': 20, 'access': 20, 'availability': 24, 'release': 24, 'trailer': 12}
    current = {key: request.GET.get(key, '').strip()[:limit] for key, limit in limits.items()
               if request.GET.get(key, '').strip()}
    def link(label, key=None, value=None):
        query = dict(current)
        if key is None:
            active = not any(query.get(name) for name in ('availability', 'release', 'trailer'))
            for name in ('availability', 'release', 'trailer'):
                query.pop(name, None)
        else:
            active = query.get(key) == value
            if active:
                query.pop(key, None)
            else:
                query[key] = value
        return {'label': label, 'active': active,
                'href': reverse('catalog') + ('?' + urlencode(query) if query else '?sort=newest')}
    return [link('Tất cả'), link('Đã có phim', 'availability', 'ready'),
            link('Chưa có bản xem', 'availability', 'upcoming'),
            link('Phim chiếu rạp', 'release', 'cinema'), link('Có trailer', 'trailer', '1')]



def landing(request):
    """Public introduction stays distinct from the signed-in movie browser."""
    # Existing bookmarked filter links remain useful after moving discovery.
    if any(request.GET.get(key) for key in ('q', 'category', 'country', 'actor', 'year', 'kind', 'sort', 'page', 'access', 'availability', 'release', 'trailer')):
        return redirect(reverse('catalog') + '?' + request.GET.urlencode())
    movies = catalog_movies(request.user)
    return render(request, 'cinema/landing.html', {
        'landing_movies': list(movies[:7]),
        'featured': movies.filter(is_vip=False, ready_episode_id__isnull=False).first() or movies.filter(ready_episode_id__isnull=False).first() or movies.first(),
        'plans': Plan.objects.filter(active=True).order_by('price', 'pk'),
        'free_movie_count': movies.filter(is_vip=False).count(),
        'vip_movie_count': movies.filter(is_vip=True).count(),
        'landing_categories': Category.objects.filter(movie__published=True).distinct().order_by('name'),
    })

def catalog_results(request, context):
    page = context['page']
    genre = context['selected_category']
    actor = context['selected_actor']
    values = {
        'q': context['q'],
        'category': context['category'],
        'country': context['selected_country'],
        'year': context['selected_year'],
        'kind': request.GET.get('kind', ''),
        'sort': request.GET.get('sort', ''),
        'access': request.GET.get('access', ''),
        'actor': context['actor_filter'],
        'availability': context['availability'],
        'release': context['release'],
        'trailer': context['trailer_filter'],
    }
    active_filters = [
        (label, value) for label, value in (
            ('Thể loại', genre.name if genre else ''),
            ('Quốc gia', values['country']),
            ('Diễn viên', actor.name if actor else ''),
            ('Năm', values['year']),
        ) if value
    ]
    titles = [
        (values['q'], f'Kết quả cho “{values["q"]}”'),
        (actor, f'Phim có {actor.name}' if actor else ''),
        (values['country'], f'Phim {values["country"]}'),
        (genre, f'Phim {genre.name}' if genre else ''),
        (values['year'], f'Phim năm {values["year"]}'),
        (values['kind'] == 'movie', 'Phim lẻ'),
        (values['kind'] == 'series', 'Phim bộ'),
        (values['access'] == 'vip', 'Phim dành cho thành viên VIP'),
        (values['sort'] == 'rating', 'Phim được đánh giá cao'),
    ]
    pagination_query = {name: value for name, value in values.items() if value}

    def page_link(number):
        return '?' + urlencode({**pagination_query, 'page': number})

    return {
        'title': next((title for matches, title in titles if matches), 'Khám phá phim'),
        'count': page.paginator.count,
        'contentLinks': context['content_links'],
        'values': values,
        'categories': [{'value': item.slug, 'label': item.name} for item in context['categories']],
        'countries': [{'value': item['name'], 'label': item['name']} for item in context['countries']],
        'years': context['years'],
        'activeFilters': [f'{label}: {value}' for label, value in active_filters],
        'pagination': {
            'page': page.number,
            'pages': page.paginator.num_pages,
            'previous': page_link(page.previous_page_number()) if page.has_previous() else None,
            'next': page_link(page.next_page_number()) if page.has_next() else None,
        },
    }


@vary_on_headers('X-Lumiere-Catalog')
def catalog(request):
    movies = catalog_movies(request.user)
    categories = list(public_categories())
    country_groups = public_country_groups()
    country_options = [{'name': group['name'], 'count': group['count']} for group in country_groups]
    q = request.GET.get('q', '').strip()[:150]
    selected_year = request.GET.get('year', '').strip()[:32]
    years = list(Movie.objects.filter(published=True, year__range=(1, 9999)).order_by('-year').values_list('year', flat=True).distinct())
    category = request.GET.get('category', '')
    kind = request.GET.get('kind', '')
    country = request.GET.get('country', '').strip()[:100]
    selected_country_group = next((group for group in country_groups if group['name'].casefold() == country.casefold()), None)
    selected_country = selected_country_group['name'] if selected_country_group else country
    actor_filter = request.GET.get('actor', '').strip()[:64]
    selected_actor = None
    actor_id = None
    if re.fullmatch(r'[1-9][0-9]{0,18}', actor_filter):
        actor_id = int(actor_filter)
        if actor_id <= 9223372036854775807:
            selected_actor = Actor.objects.filter(pk=actor_id, movie__published=True).distinct().first()
        else:
            actor_id = None
    selected_category = next((genre for genre in categories if genre.slug == category), None)
    availability = request.GET.get('availability', '').strip()[:24]
    release = request.GET.get('release', '').strip()[:24]
    trailer_filter = request.GET.get('trailer', '').strip()[:12]
    is_browsing = any(request.GET.get(key) for key in ('q', 'category', 'country', 'actor', 'year', 'kind', 'sort', 'page', 'access', 'availability', 'release', 'trailer'))
    filtered = movies
    if q: filtered = filter_movie_search(filtered, q)
    if selected_year:
        filtered = filtered.filter(year=int(selected_year)) if re.fullmatch(r'[1-9][0-9]{0,3}', selected_year) else filtered.none()
    if category: filtered = filtered.filter(categories__slug=category)
    if country:
        filtered = filtered.filter(country__in=selected_country_group['values']) if selected_country_group else filtered.none()
    if actor_filter:
        filtered = filtered.filter(actors__pk=actor_id) if actor_id else filtered.none()
    if kind in ('movie', 'series'): filtered = filtered.filter(kind=kind)
    if request.GET.get('access') == 'vip': filtered = filtered.filter(is_vip=True)
    if availability:
        filtered = filtered.filter(ready_episode_id__isnull=availability == 'upcoming') if availability in ('ready', 'upcoming') else filtered.none()
    if release:
        filtered = filtered.filter(is_cinema_release=True) if release == 'cinema' else filtered.none()
    if trailer_filter:
        filtered = filtered.exclude(trailer_url='', trailer_file='') if trailer_filter == '1' else filtered.none()
    if request.GET.get('sort') == 'rating': filtered = filtered.order_by('-score', '-created_at', '-pk')

    shelves = []
    continue_watching = []
    featured_movies = []
    if not is_browsing:
        featured_movies = list(movies.filter(ready_episode_id__isnull=False)[:3])
        shelves.append({'title': 'Mới trên Lumière', 'subtitle': 'Những câu chuyện mới trong thư viện.', 'movies': list(movies[:12]), 'href': reverse('catalog') + '?sort=newest'})
        vip_movies = list(movies.filter(is_vip=True)[:12])
        if vip_movies:
            preparing = not any(film.ready_episode_id for film in vip_movies)
            subtitle = 'Những bộ phim VIP đang được chuẩn bị.' if preparing else 'Mở thêm những bộ phim dành riêng cho bạn.'
            shelves.append({'title': 'Dành cho thành viên VIP', 'subtitle': subtitle, 'preparing': preparing, 'movies': vip_movies, 'href': reverse('catalog') + '?access=vip'})
        for genre in categories:
            if genre.published_count < 2:
                continue
            selections = list(movies.filter(categories=genre)[:12])
            if not selections:
                continue
            shelves.append({'title': genre.name, 'subtitle': '', 'movies': selections, 'href': reverse('catalog') + '?' + urlencode({'category': genre.slug})})
            if len(shelves) >= 4:
                break
        continue_watching = continue_cards(request.user, 12)
    context = {
        'page': Paginator(filtered.distinct(), 12).get_page(request.GET.get('page')),
        'featured': featured_movies[0] if featured_movies else None,
        'categories': categories, 'q': q, 'category': category,
        'is_browsing': is_browsing, 'shelves': shelves, 'continue_watching': continue_watching,
        'featured_movies': featured_movies,
        'countries': country_options, 'selected_country': selected_country,
        'years': years, 'selected_year': selected_year,
        'content_links': catalog_content_links(request), 'availability': availability,
        'release': release, 'trailer_filter': trailer_filter,
        'selected_category': selected_category, 'selected_actor': selected_actor, 'actor_filter': actor_filter,
    }
    if is_browsing:
        results = catalog_results(request, context)
        if request.headers.get('X-Lumiere-Catalog') == 'vue':
            results['gridHtml'] = render_to_string('cinema/catalog_grid.html', context, request=request)
            return JsonResponse(results, headers={'Cache-Control': 'private, no-store'})
        context['catalog_results'] = results
    return render(request, 'cinema/catalog.html', context)


def register(request):
    if request.user.is_authenticated:
        return redirect('catalog')
    next_url = request.POST.get('next', request.GET.get('next', '')).strip()
    if not url_has_allowed_host_and_scheme(
        next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure(),
    ):
        next_url = ''
    form = RegisterForm(request.POST if request.method == 'POST' else None)
    if request.method == 'POST' and form.is_valid():
        login(request, form.save())
        return HttpResponseRedirect(next_url or reverse('catalog'))
    return render(request, 'registration/form.html', {
        'form': form, 'next': next_url, 'title': 'Tạo tài khoản',
        'subtitle': 'Một tài khoản. Cả thế giới điện ảnh.', 'button': 'Bắt đầu khám phá',
    })


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
def library(request):
    return render(request, 'cinema/library.html', {
        'movies': catalog_movies(request.user).filter(watchlist__user=request.user),
        'continue_watching': continue_cards(request.user, 30),
        'history': history_cards(public_history(request.user).select_related('episode__movie')[:30]),
    })


@login_required
def profile(request):
    form = ProfileForm(instance=request.user)
    if request.method == 'POST':
        with transaction.atomic():
            user = User.objects.select_for_update().get(pk=request.user.pk)
            if not user.is_active or user.erased_at:
                raise PermissionDenied
            form = ProfileForm(request.POST, instance=user)
            if form.is_valid():
                form.save(commit=False).save(update_fields=ProfileForm.Meta.fields)
                messages.success(request, 'Đã cập nhật hồ sơ.')
    return render(request, 'cinema/profile.html', {'form': form, 'avatar_form': AvatarForm(), 'orders': Order.objects.filter(user=request.user).select_related('plan').order_by('-created_at')[:30]})


def _delete_unused_avatar(name, storage):
    # Only files generated by this feature are managed here. Shared or unrelated
    # stored paths are retained rather than deleting another user's content.
    if is_managed_avatar(name) and not User.objects.filter(avatar=name).exists():
        storage.delete(name)


@login_required
@require_POST
def profile_avatar(request):
    form = AvatarForm(request.POST, request.FILES, upload_error=getattr(request, '_avatar_upload_error', None))
    if not form.is_valid():
        return render(request, 'cinema/profile.html', {
            'form': ProfileForm(instance=request.user), 'avatar_form': form,
            'orders': Order.objects.filter(user=request.user).select_related('plan').order_by('-created_at')[:30],
        })
    new_name = None
    user = None
    storage = User._meta.get_field('avatar').storage
    try:
        with transaction.atomic():
            # Re-read the current path under the transaction: replacing a photo
            # must not overwrite profile fields or clean up a stale cached path.
            user = User.objects.select_for_update().get(pk=request.user.pk)
            if not user.is_active or user.erased_at:
                raise PermissionDenied
            previous_name = user.avatar.name
            user.avatar = '' if form.cleaned_data['remove_avatar'] else form.cleaned_data['avatar']
            user.save(update_fields=['avatar'])
            new_name = user.avatar.name
            if previous_name and previous_name != new_name:
                transaction.on_commit(lambda: _delete_unused_avatar(previous_name, storage), robust=True)
    except Exception:
        with suppress(Exception):
            candidate = new_name or (user.avatar.name if user is not None and user.avatar._committed else None)
            if candidate:
                _delete_unused_avatar(candidate, storage)
        raise
    messages.success(request, 'Đã xóa ảnh đại diện.' if form.cleaned_data['remove_avatar'] else 'Đã cập nhật ảnh đại diện.')
    return redirect(reverse('profile') + '#avatar')


@login_required
def watch(request, pk):
    episode = get_object_or_404(Episode.objects.select_related('movie'), pk=pk)
    require_watch(request.user, episode)
    history = History.objects.filter(user=request.user, episode=episode).first()
    restarting = request.GET.get('start') == '1'
    position = history.position if history and not restarting and 0 < history.position < episode.duration - 1 else 0
    episodes = list(episode.movie.episodes.filter(status='ready'))
    next_episode = next((item for item in episodes if item.number > episode.number), None)
    return render(request, 'cinema/watch.html', {
        'episode': episode, 'position': position,
        'start_over_url': reverse('watch', args=[episode.pk]) + '?start=1' if position > 0 else '',
        'episodes': episodes, 'next_episode': next_episode,
        'duration_minutes': math.ceil(max(0, episode.duration) / 60),
    })


@login_required
@require_POST
def progress(request, pk):
    episode = get_object_or_404(Episode.objects.select_related('movie'), pk=pk)
    require_watch(request.user, episode)
    try: position = float(request.POST.get('position', 0))
    except ValueError: return JsonResponse({'error': 'Vị trí không hợp lệ'}, status=400)
    if not math.isfinite(position) or not 0 <= position <= episode.duration + 1: return JsonResponse({'error': 'Vị trí không hợp lệ'}, status=400)
    defaults = {'position': position}
    if position > 0:
        defaults['hidden_from_continue'] = False
    History.objects.update_or_create(user=request.user, episode=episode, defaults=defaults)
    return JsonResponse({'ok': True})


@login_required
@require_POST
def report(request, pk):
    episode = get_object_or_404(Episode, pk=pk, movie__published=True)
    description = request.POST.get('description', '').strip()
    if 1 <= len(description) <= 1000:
        Report.objects.create(user=request.user, episode=episode, description=description)
        messages.success(request, 'Đã gửi báo lỗi cho quản trị viên.')
    return redirect('movie', slug=episode.movie.slug)


@login_required
@require_POST
def stream_ticket(request, pk):
    episode = get_object_or_404(Episode.objects.select_related('movie'), pk=pk)
    require_watch(request.user, episode)
    if not request.session.session_key: request.session.save()
    # One current browser session per account. DB session authentication is also required on every segment.
    from django.core.cache import cache
    cache.set(f'playback:{request.user.pk}', request.session.session_key, settings.STREAM_TOKEN_AGE + 60)
    token = signing.dumps({'u': request.user.pk, 's': salted_hmac('video-session', request.session.session_key).hexdigest(), 'e': episode.pk}, salt='video')
    return JsonResponse({'url': reverse('stream', args=[episode.pk, 'index.m3u8']) + '?' + urlencode({'token': token})})


@login_required
@require_GET
def stream(request, pk, filename):
    episode = get_object_or_404(Episode.objects.select_related('movie'), pk=pk)
    require_watch(request.user, episode)
    token = request.GET.get('token', '')
    try: ticket = signing.loads(token, salt='video', max_age=settings.STREAM_TOKEN_AGE)
    except signing.BadSignature: raise PermissionDenied('Nguồn phát đã hết hạn.')
    from django.core.cache import cache
    if ticket != {'u': request.user.pk, 's': salted_hmac('video-session', request.session.session_key).hexdigest(), 'e': episode.pk} or cache.get(f'playback:{request.user.pk}') != request.session.session_key:
        raise PermissionDenied('Phiên phát không hợp lệ.')
    if not re.fullmatch(r'(index\.m3u8|seg\d{5,}\.ts)', filename): raise Http404
    path = settings.PRIVATE_MEDIA_ROOT / 'hls' / str(episode.asset_id) / filename
    if not path.is_file(): raise Http404
    if filename == 'index.m3u8':
        lines = path.read_text().splitlines()
        content = '\n'.join(line if not line or line.startswith('#') else reverse('stream', args=[pk, line]) + '?' + urlencode({'token': token}) for line in lines)
        return HttpResponse(content, content_type='application/vnd.apple.mpegurl')
    return FileResponse(path.open('rb'), content_type='video/mp2t')


def plans(request):
    active_member = bool(request.user.is_authenticated and request.user.is_vip)
    renewing = active_member and request.GET.get('renew') == '1'
    member_dashboard = active_member and not renewing
    watch_together_url = reverse('rooms')
    payment_ready = bool(settings.VNPAY_TMN_CODE and settings.VNPAY_HASH_SECRET)
    checkout_token = None
    if payment_ready and request.user.is_authenticated and request.user.is_active and not member_dashboard:
        checkout_token = issue_checkout_token(request.user.pk)
    return render(request, 'cinema/plans.html', {
        'plans': Plan.objects.filter(active=True).order_by('price'),
        'payment_ready': payment_ready,
        'checkout_token': checkout_token,
        'sandbox': 'sandbox' in settings.VNPAY_URL,
        'showcase': Movie.objects.filter(published=True)[:6],
        'member_dashboard': member_dashboard, 'renewing': renewing,
        'watch_together_url': watch_together_url,
    })


@login_required
@require_POST
def checkout(request, pk=None):
    if pk is None:
        try: pk = int(request.POST.get('plan', ''))
        except (ValueError, TypeError): raise Http404('Gói thành viên không hợp lệ.')
    if not settings.VNPAY_TMN_CODE or not settings.VNPAY_HASH_SECRET:
        get_object_or_404(Plan, pk=pk, active=True)
        messages.error(request, 'VNPay chưa được cấu hình. Chưa tạo giao dịch hoặc thu tiền.')
        return redirect('plans')

    plans_url = reverse('plans')
    if request.user.is_vip:
        plans_url += '?renew=1'
    try:
        checkout_key = checkout_key_from_token(request.user.pk, request.POST.get('checkout_token', ''))
    except signing.BadSignature:
        messages.error(request, 'Phiên chọn gói đã hết hạn hoặc không hợp lệ. Vui lòng kiểm tra lại gói trước khi tiếp tục.')
        return redirect(plans_url)

    with transaction.atomic():
        buyer = User.objects.select_for_update().filter(pk=request.user.pk, is_active=True).first()
        if buyer is None:
            raise PermissionDenied('Tài khoản không còn hoạt động.')
        order = Order.objects.filter(user=buyer, checkout_key=checkout_key).first()
        if order is None:
            plan = get_object_or_404(Plan, pk=pk, active=True)
            order = Order.objects.create(
                user=buyer, plan=plan, amount=plan.price, days=plan.days, checkout_key=checkout_key,
            )
        elif order.plan_id != pk:
            messages.error(request, 'Lần thanh toán này đã gắn với một gói khác. Vui lòng chọn lại gói.')
            return redirect(plans_url)

    if order.status == 'paid':
        return redirect(reverse('profile') + '#billing')
    if order.status != 'pending' or timezone.now() >= order.created_at + PAYMENT_WINDOW:
        messages.info(request, 'Lần thanh toán này đã kết thúc. Vui lòng chọn lại gói nếu bạn muốn thanh toán tiếp.')
        return redirect(plans_url)
    return redirect(checkout_url(order, request.META.get('REMOTE_ADDR', '127.0.0.1')))


@require_GET
def ipn(request): return JsonResponse(process_ipn(request.GET))


@login_required
def payment_return(request):
    # Browser redirects never grant VIP. Only signed server IPN mutates an order.
    messages.info(request, 'Đã trở về từ VNPay. Trạng thái đơn hàng sẽ cập nhật sau khi nhận xác nhận từ cổng thanh toán.')
    return redirect('profile')


def can_host_room(user):
    return user.is_active and (user.is_vip or user.is_staff)


def create_watch_room(request, episode, form):
    password = form.cleaned_data['password']
    password_hash = make_password(password) if password else ''
    with transaction.atomic():
        host = User.objects.select_for_update().get(pk=request.user.pk)
        if not can_host_room(host):
            raise PermissionDenied('VIP mới có thể tạo phòng.')
        if episode:
            require_watch(host, episode)
        if Room.objects.filter(host=host, closed=False, created_at__gt=timezone.now() - timedelta(hours=6)).count() >= 3:
            return None
        name = request.POST.get('name', '').strip()[:100]
        room = Room.objects.create(
            host=host, episode=episode,
            name=name or (episode.movie.title[:100] if episode else 'Phòng xem của ' + host.username[:80]),
            password_hash=password_hash, requires_approval=form.cleaned_data['requires_approval'],
        )
        Membership.objects.create(room=room, user=host)
        if episode:
            RoomPlaylistItem.objects.create(room=room, episode=episode, position=1)
    return room


@login_required
@require_http_methods(['GET', 'POST'])
def rooms(request):
    form = RoomAccessForm(request.POST if request.method == 'POST' else None)
    error = ''
    if request.method == 'POST':
        if not can_host_room(request.user):
            raise PermissionDenied('VIP mới có thể tạo phòng.')
        if form.is_valid():
            created = create_watch_room(request, None, form)
            if created:
                return redirect('room', pk=created.pk)
            error = 'Bạn đã có 3 phòng đang hoạt động.'
    available = Room.objects.filter(
        Q(host=request.user) | Q(members__user=request.user, members__banned=False, members__active=True),
        closed=False, created_at__gt=timezone.now() - timedelta(hours=6),
    ).select_related('host', 'episode__movie').distinct().order_by('-created_at')
    return render(request, 'cinema/rooms.html', {
        'rooms': available, 'form': form, 'can_create_room': can_host_room(request.user), 'error': error,
    }, status=400 if request.method == 'POST' else 200)


@login_required
@require_POST
def create_room(request, pk):
    episode = get_object_or_404(Episode.objects.select_related('movie'), pk=pk)
    require_watch(request.user, episode)
    if not can_host_room(request.user):
        raise PermissionDenied('VIP mới có thể tạo phòng.')
    form = RoomAccessForm(request.POST)
    if not form.is_valid():
        messages.error(request, 'Mật khẩu phòng cần từ 4 đến 128 ký tự.')
        return redirect(reverse('watch', args=[pk]) + '#watch-together')
    created = create_watch_room(request, episode, form)
    if not created:
        messages.error(request, 'Bạn đã có 3 phòng đang hoạt động.')
        return redirect('watch', pk=pk)
    return redirect('room', pk=created.pk)


def accessible_room(request, pk, lock=False):
    qs = Room.objects.all()
    if lock:
        qs = qs.select_for_update()
    else:
        qs = qs.select_related('episode__movie', 'host')
    room = get_object_or_404(qs, pk=pk, closed=False, created_at__gt=timezone.now() - timedelta(hours=6))
    if not can_host_room(room.host):
        raise PermissionDenied('Quyền tạo phòng của chủ phòng đã hết hạn.')
    return room


def active_room_member(request, room):
    return get_object_or_404(Membership, room=room, user=request.user, banned=False, active=True)


def room_member_roster(room):
    members = room.members.filter(
        banned=False, active=True, user__is_active=True,
        last_seen__gt=timezone.now() - timedelta(seconds=30),
    ).select_related('user').order_by('user_id')
    return [{
        'user_id': member.user_id,
        'user__username': member.user.username,
        'display_name': member.user.get_full_name().strip() or member.user.username,
        'avatar_url': member.user.avatar.url if member.user.avatar else '',
    } for member in members]


def room_media_state(room, user):
    episode = room.episode
    published = bool(episode and episode.movie.published and episode.status == 'ready')
    return {
        'episode_id': episode.pk if episode else None,
        'media_version': room.media_version,
        'can_watch': can_watch(user, episode),
        'title': episode.movie.title if published else '',
        'episode_title': episode.title if published else '',
        'player_url': reverse('room_player', args=[room.pk]) + '?' + urlencode({'v': room.media_version}),
    }


def room_player_context(room, user):
    episode = room.episode
    return {
        'room': room, 'episode': episode if episode and episode.movie.published else None,
        'is_host': room.host_id == user.pk, 'position': room.position,
        'media_version': room.media_version, 'can_watch_room': can_watch(user, room.episode),
        'room_media': room_media_state(room, user),
        'playlist_url': reverse('room_playlist', args=[room.pk]),
    }


@login_required
@require_GET
def room_player(request, pk):
    room = accessible_room(request, pk)
    active_room_member(request, room)
    response = render(request, 'cinema/room_player.html', room_player_context(room, request.user))
    response['Cache-Control'] = 'private, no-store'
    return response


@login_required
@require_http_methods(['GET', 'POST'])
@vary_on_headers('X-Lumiere-Room-Selection')
def room_selection(request, pk):
    with transaction.atomic() if request.method == 'POST' else nullcontext():
        room = accessible_room(request, pk, lock=request.method == 'POST')
        active_room_member(request, room)
        if request.method == 'POST':
            if room.host_id != request.user.pk:
                raise PermissionDenied
            if request.POST.get('media_version') != str(room.media_version):
                return JsonResponse({
                    **room_media_state(room, request.user), 'code': 'media_changed',
                    'error': 'Phim trong phòng đã thay đổi. Kiểm tra lại rồi chọn phim.',
                }, status=409)
            action = request.POST.get('action', 'select')
            episode = None
            if action == 'select':
                try:
                    episode_id = int(request.POST.get('episode', ''))
                except (TypeError, ValueError):
                    return JsonResponse({'error': 'Tập phim không hợp lệ.'}, status=400)
                if not 0 < episode_id < 2**63:
                    return JsonResponse({'error': 'Tập phim không hợp lệ.'}, status=400)
                episode = get_object_or_404(Episode.objects.select_related('movie'), pk=episode_id, status='ready', movie__published=True)
                require_watch(request.user, episode)
            elif action != 'clear':
                return JsonResponse({'error': 'Thao tác không hợp lệ.'}, status=400)
            room.episode = episode
            room.media_version += 1
            room.position = 0
            room.playing = False
            room.updated_at = timezone.now()
            room.save(update_fields=['episode', 'media_version', 'position', 'playing', 'updated_at'])
            if request.headers.get('X-Lumiere-Room-Selection') == '1':
                return JsonResponse(room_media_state(room, request.user))
            return redirect('room', pk=room.pk)

        query = request.GET.get('q', '').strip()[:150]
        movies = filter_movie_search(Movie.objects.filter(published=True), query)
        episodes = Episode.objects.select_related('movie').filter(movie__in=movies, status='ready')
        if not (request.user.is_vip or request.user.is_staff):
            episodes = episodes.filter(movie__is_vip=False)
        context = {
            'room': room, 'q': query, 'is_host': room.host_id == request.user.pk,
            'episodes': Paginator(episodes.order_by('movie__title', 'movie_id', 'number', 'pk'), 12).get_page(request.GET.get('page')),
        }
        template = 'cinema/room_selection_results.html' if request.headers.get('X-Lumiere-Room-Selection') == '1' else 'cinema/room_selection.html'
        return render(request, template, context)


def playlist_episode_data(episode):
    if not episode.movie.published or episode.status != 'ready':
        return {
            'episode_id': episode.pk, 'title': 'Phim không còn khả dụng',
            'episode_title': '', 'poster_url': '', 'available': False,
        }
    movie = episode.movie
    if movie.poster:
        poster_url = movie.poster.url
    elif movie.backdrop:
        poster_url = movie.backdrop.url
    elif movie.slug in {'big-buck-bunny', 'orbit', 'dusk', 'forest', 'city', 'ocean', 'summer'}:
        poster_url = static(f'imagery/posters/{movie.slug}.svg')
    else:
        artwork = movie.artwork if movie.artwork in {'orbit', 'dusk', 'forest', 'city', 'ocean', 'summer'} else 'orbit'
        poster_url = static(f'art/{artwork}.svg')
    return {
        'episode_id': episode.pk, 'title': episode.movie.title,
        'episode_title': episode.title, 'poster_url': poster_url, 'available': True,
    }


def room_playlist_state(room, user):
    items = room.playlist_items.select_related('episode__movie').all()
    is_host = room.host_id == user.pk
    suggestions_query = room.suggestions.select_related('episode__movie', 'proposed_by')
    suggestions = list(suggestions_query.filter(status=RoomSuggestion.Status.PENDING))
    if not is_host:
        suggestions.extend(suggestions_query.filter(proposed_by=user).exclude(
            status=RoomSuggestion.Status.PENDING,
        ).order_by('-created_at', '-pk')[:20])
    return {
        'playlist_version': room.playlist_version, 'is_host': is_host, 'can_manage': is_host,
        'items': [dict(id=item.pk, position=item.position, **playlist_episode_data(item.episode)) for item in items],
        'suggestions': [dict(
            id=entry.pk, proposed_by=entry.proposed_by.username, proposer_id=entry.proposed_by_id,
            status=entry.status, **playlist_episode_data(entry.episode),
        ) for entry in suggestions],
    }


def room_playlist_error(room, user, message, status=400):
    data = {**room_playlist_state(room, user), 'error': message}
    if status == 409:
        data['code'] = 'playlist_changed'
    return JsonResponse(data, status=status)


def playlist_request_id(request, key):
    try:
        value = int(request.POST.get(key, ''))
    except (TypeError, ValueError):
        return None
    return value if 0 < value < 2**63 else None


def append_playlist_item(room, episode):
    existing = room.playlist_items.filter(episode=episode).first()
    if existing:
        return False
    count = room.playlist_items.count()
    if count >= 50:
        raise ValueError('Danh sách đã đủ 50 tập phim.')
    last_position = room.playlist_items.order_by('-position').values_list('position', flat=True).first() or 0
    room.playlist_items.create(episode=episode, position=last_position + 1)
    return True


def renumber_playlist(room, ordered_ids):
    positions = {pk: index for index, pk in enumerate(ordered_ids, 1)}
    items = list(room.playlist_items.all())
    for item in items:
        item.position = positions[item.pk]
    RoomPlaylistItem.objects.bulk_update(items, ['position'])


@login_required
@require_http_methods(['GET', 'POST'])
def room_playlist(request, pk):
    with transaction.atomic():
        room = accessible_room(request, pk, lock=True)
        active_room_member(request, room)
        if request.method == 'GET':
            return JsonResponse(room_playlist_state(room, request.user))
        action = request.POST.get('action')
        if action != 'suggest':
            if room.host_id != request.user.pk:
                raise PermissionDenied
            if request.POST.get('playlist_version') != str(room.playlist_version):
                return room_playlist_error(room, request.user, 'Danh sách đã thay đổi. Kiểm tra lại rồi thử tiếp.', 409)
        changed = True
        playing = False
        try:
            if action in ('add', 'suggest'):
                episode_id = playlist_request_id(request, 'episode')
                episode = get_object_or_404(Episode.objects.select_related('movie'), pk=episode_id, status='ready', movie__published=True)
                require_watch(request.user, episode)
                if action == 'add':
                    changed = append_playlist_item(room, episode)
                else:
                    existing = room.suggestions.filter(episode=episode).first()
                    if room.playlist_items.filter(episode=episode).exists() or (existing and existing.status == RoomSuggestion.Status.PENDING):
                        changed = False
                    else:
                        pending = room.suggestions.filter(status=RoomSuggestion.Status.PENDING)
                        if pending.count() >= 20 or pending.filter(proposed_by=request.user).count() >= 5:
                            raise ValueError('Đã đủ đề xuất đang chờ. Hãy chờ chủ phòng phản hồi.')
                        if existing:
                            existing.status = RoomSuggestion.Status.PENDING
                            existing.proposed_by = request.user
                            existing.created_at = timezone.now()
                            existing.save(update_fields=['status', 'proposed_by', 'created_at'])
                        else:
                            room.suggestions.create(episode=episode, proposed_by=request.user)
            elif action == 'remove':
                item = get_object_or_404(room.playlist_items, pk=playlist_request_id(request, 'item'))
                item.delete()
                renumber_playlist(room, list(room.playlist_items.values_list('pk', flat=True)))
            elif action == 'reorder':
                try:
                    ordered_ids = json.loads(request.POST.get('item_ids', ''))
                except (ValueError, TypeError, RecursionError):
                    raise ValueError('Thứ tự danh sách không hợp lệ.')
                current_ids = list(room.playlist_items.values_list('pk', flat=True))
                if (
                    not isinstance(ordered_ids, list) or len(ordered_ids) != len(current_ids)
                    or any(type(value) is not int for value in ordered_ids)
                    or set(ordered_ids) != set(current_ids)
                ):
                    raise ValueError('Thứ tự danh sách không hợp lệ.')
                changed = ordered_ids != current_ids
                if changed:
                    renumber_playlist(room, ordered_ids)
            elif action == 'play':
                item = get_object_or_404(room.playlist_items.select_related('episode__movie'), pk=playlist_request_id(request, 'item'))
                require_watch(request.user, item.episode)
                room.episode = item.episode
                room.position = 0
                room.playing = False
                room.updated_at = timezone.now()
                room.media_version += 1
                room.save(update_fields=['episode', 'position', 'playing', 'updated_at', 'media_version'])
                playing = True
            elif action in ('approve', 'reject'):
                suggestion = get_object_or_404(
                    room.suggestions.select_related('episode__movie'),
                    pk=playlist_request_id(request, 'suggestion'), status=RoomSuggestion.Status.PENDING,
                )
                if action == 'approve':
                    require_watch(request.user, suggestion.episode)
                    append_playlist_item(room, suggestion.episode)
                    suggestion.status = RoomSuggestion.Status.APPROVED
                else:
                    suggestion.status = RoomSuggestion.Status.REJECTED
                suggestion.save(update_fields=['status'])
            else:
                raise ValueError('Thao tác không hợp lệ.')
        except ValueError as error:
            return room_playlist_error(room, request.user, str(error))
        if changed:
            room.playlist_version += 1
            room.save(update_fields=['playlist_version'])
        data = room_playlist_state(room, request.user)
        if playing:
            data.update(room_media_state(room, request.user))
        return JsonResponse(data)


@login_required
def room(request, pk):
    room = accessible_room(request, pk)
    member = Membership.objects.filter(room=room, user=request.user).first()
    if member and member.banned:
        raise PermissionDenied('Bạn đã bị loại khỏi phòng.')
    if not member or not member.active:
        return room_lobby(request, room)
    response = render(request, 'cinema/room.html', {
        **room_player_context(room, request.user),
        'room_access_version': room_access_settings(room)['settings_version'] if room.host_id == request.user.pk else '',
    })
    response.allow_room_microphone = True
    return response


def room_lobby(request, room, error='', status=200):
    join_status = RoomJoinRequest.objects.filter(room=room, user=request.user).values_list('status', flat=True).first()
    return render(request, 'cinema/join.html', {'room': room, 'join_status': join_status, 'join_error': error}, status=status)


def room_password_attempt_allowed(room_id, user_id):
    key = f'room-password:{room_id}:{user_id}'
    if cache.add(key, 1, timeout=60):
        return True
    try:
        return cache.incr(key) <= 8
    except ValueError:
        return cache.add(key, 1, timeout=60)


@login_required
@require_POST
def join_room(request, pk):
    with transaction.atomic():
        room = accessible_room(request, pk, lock=True)
        member = Membership.objects.filter(room=room, user=request.user).first()
        if member and member.banned: raise PermissionDenied
        if member and member.active:
            return redirect('room', pk=pk)
        admission = RoomJoinRequest.objects.filter(room=room, user=request.user).first()
        if admission and admission.status == RoomJoinRequest.Status.REJECTED:
            return room_lobby(request, room, status=403)
        if room.requires_approval and admission and admission.status == RoomJoinRequest.Status.PENDING:
            return redirect('room', pk=pk)
        approved = admission and admission.status == RoomJoinRequest.Status.APPROVED
        if room.password_hash and not approved:
            if not room_password_attempt_allowed(room.pk, request.user.pk):
                return room_lobby(request, room, 'Bạn đã thử quá nhiều lần. Hãy đợi một phút.', 429)
            password = request.POST.get('password', '')
            if not 4 <= len(password) <= 128 or not check_password(password, room.password_hash):
                return room_lobby(request, room, 'Mật khẩu phòng không đúng.', 400)
        if room.requires_approval and not approved:
            RoomJoinRequest.objects.get_or_create(room=room, user=request.user)
            return redirect('room', pk=pk)
        if room.members.filter(banned=False, active=True, last_seen__gt=timezone.now() - timedelta(seconds=30)).exclude(user=request.user).count() >= 10:
            return room_lobby(request, room, 'Phòng đã đủ 10 thành viên.', 409)
        Membership.objects.update_or_create(room=room, user=request.user, defaults={
            'active': True, 'last_seen': timezone.now(), 'voice_session': None, 'voice_seen_at': None, 'voice_mic_on': False,
        })
        if admission:
            admission.delete()
    return redirect('room', pk=pk)


def room_access_settings(room):
    version = salted_hmac(
        'cinema.room-access-settings', f'{room.pk}:{room.requires_approval}:{room.password_hash}', algorithm='sha256',
    ).hexdigest()
    return {
        'has_password': bool(room.password_hash),
        'requires_approval': room.requires_approval,
        'settings_version': version,
    }


@login_required
@require_http_methods(['GET', 'POST'])
def room_admission(request, pk):
    with transaction.atomic() if request.method == 'POST' else nullcontext():
        room = accessible_room(request, pk, lock=request.method == 'POST')
        if room.host_id != request.user.pk:
            if request.method != 'GET':
                raise PermissionDenied
            status = room.join_requests.filter(user=request.user).values_list('status', flat=True).first()
            return JsonResponse({'status': status, 'requires_approval': room.requires_approval})
        if request.method == 'POST':
            action = request.POST.get('action')
            if action in ('approve', 'reject'):
                try:
                    entry_id = int(request.POST.get('request', ''))
                except ValueError:
                    entry_id = 0
                if not 0 < entry_id < 2**63:
                    return JsonResponse({'error': 'Yêu cầu vào phòng không hợp lệ.'}, status=400)
                entry = get_object_or_404(room.join_requests, pk=entry_id, status=RoomJoinRequest.Status.PENDING)
                entry.status = RoomJoinRequest.Status.APPROVED if action == 'approve' else RoomJoinRequest.Status.REJECTED
                entry.save(update_fields=['status'])
            elif action == 'settings':
                current_settings = room_access_settings(room)
                if request.POST.get('settings_version') != current_settings['settings_version']:
                    return JsonResponse({
                        **current_settings,
                        'error': 'Cài đặt phòng đã thay đổi. Kiểm tra lại rồi bấm lưu.',
                    }, status=409)
                form = RoomAccessForm(request.POST)
                remove_password = request.POST.get('remove_password') == 'on'
                if not form.is_valid() or (remove_password and form.cleaned_data['password']):
                    return JsonResponse({'error': 'Nhập mật khẩu mới từ 4 đến 128 ký tự hoặc chọn bỏ mật khẩu.'}, status=400)
                password = form.cleaned_data['password']
                if password or remove_password:
                    room.password_hash = make_password(password) if password else ''
                    room.join_requests.exclude(status=RoomJoinRequest.Status.REJECTED).delete()
                room.requires_approval = form.cleaned_data['requires_approval']
                room.save(update_fields=['password_hash', 'requires_approval'])
            else:
                return JsonResponse({'error': 'Thao tác không hợp lệ.'}, status=400)
        pending = room.join_requests.filter(status=RoomJoinRequest.Status.PENDING).order_by('created_at', 'pk')
        return JsonResponse({
            **room_access_settings(room),
            'pending': list(pending.values('pk', 'user__username')[:30]), 'pending_count': pending.count(),
        })


@login_required
@require_http_methods(['GET', 'POST'])
def room_state(request, pk):
    with transaction.atomic():
        room = accessible_room(request, pk, lock=True)
        member = get_object_or_404(Membership, room=room, user=request.user, banned=False, active=True)
        if room.members.filter(banned=False, active=True, last_seen__gt=timezone.now() - timedelta(seconds=30)).exclude(user=request.user).count() >= 10:
            return JsonResponse({'error': 'Phòng đã đủ 10 thành viên.'}, status=409)
        if request.method == 'POST':
            action = request.POST.get('action')
            if action == 'chat':
                content = request.POST.get('content', '').strip()
                if not 1 <= len(content) <= 500: return JsonResponse({'error': 'Tin nhắn cần 1–500 ký tự.'}, status=400)
                Chat.objects.create(room=room, user=request.user, content=content)
            else:
                if room.host_id != request.user.pk: raise PermissionDenied
                if action == 'close':
                    room.closed = True
                    room.members.update(voice_session=None, voice_seen_at=None, voice_mic_on=False)
                    RoomVoiceSignal.objects.filter(room=room).delete()
                elif action == 'kick':
                    try: target = int(request.POST.get('user', ''))
                    except (ValueError, TypeError): return JsonResponse({'error': 'Thành viên không hợp lệ'}, status=400)
                    if not 0 < target < 2**63:
                        return JsonResponse({'error': 'Thành viên không hợp lệ'}, status=400)
                    removed = Membership.objects.filter(room=room, user_id=target, banned=False).exclude(user=room.host).update(
                        banned=True, active=False, voice_session=None, voice_seen_at=None, voice_mic_on=False,
                    )
                    if removed:
                        RoomVoiceSignal.objects.filter(room=room).filter(Q(sender_id=target) | Q(recipient_id=target)).delete()
                elif action == 'sync':
                    version = request.POST.get('media_version')
                    if version != str(room.media_version) and not (version is None and room.media_version == 1):
                        return JsonResponse({
                            **room_media_state(room, request.user), 'code': 'media_changed',
                            'error': 'Phim trong phòng đã thay đổi. Đang cập nhật nguồn phát.',
                        }, status=409)
                    if not room.episode:
                        return JsonResponse({'error': 'Chọn phim trước khi bắt đầu phát.'}, status=400)
                    require_watch(request.user, room.episode)
                    try: position = float(request.POST.get('position', 0))
                    except ValueError: return JsonResponse({'error': 'Vị trí không hợp lệ'}, status=400)
                    if not math.isfinite(position) or not 0 <= position <= room.episode.duration + 1: return JsonResponse({'error': 'Vị trí không hợp lệ'}, status=400)
                    room.position = position
                    room.playing = request.POST.get('playing') == 'true'
                    room.updated_at = timezone.now()
                else: return JsonResponse({'error': 'Thao tác không hợp lệ'}, status=400)
                room.save()
        member.last_seen = timezone.now()
        member.save(update_fields=['last_seen'])
        position = min(room.episode.duration, room.position + ((timezone.now() - room.updated_at).total_seconds() if room.playing else 0)) if room.episode else 0
        chats = list(Chat.objects.filter(room=room).select_related('user').order_by('-id')[:60])
        return JsonResponse({**room_media_state(room, request.user), 'position': position, 'playing': bool(room.episode and room.playing), 'closed': room.closed, 'members': room_member_roster(room), 'messages': [{'id': c.pk, 'user_id': c.user_id, 'user': c.user.username, 'content': c.content} for c in reversed(chats)]})


@login_required
@require_POST
def leave_room(request, pk):
    with transaction.atomic():
        room = get_object_or_404(Room.objects.select_for_update(), pk=pk)
        members = room.members.all()
        signals = RoomVoiceSignal.objects.filter(room=room)
        if room.host_id == request.user.pk:
            room.closed = True
            room.save(update_fields=['closed'])
        else:
            members = members.filter(user=request.user)
            signals = signals.filter(Q(sender=request.user) | Q(recipient=request.user))
        members.update(active=False, voice_session=None, voice_seen_at=None, voice_mic_on=False)
        signals.delete()
    return redirect('library')


@vary_on_headers('X-Lumiere-Directory')
def actors(request):
    query = request.GET.get('q', '').strip()[:150]
    people = Actor.objects.annotate(
        film_count=Count('movie', filter=Q(movie__published=True), distinct=True),
    ).filter(film_count__gt=0).order_by('name', 'pk')
    if query: people = filter_actor_search(people, query)
    page = Paginator(people, 24).get_page(request.GET.get('page'))
    context = {'actors': page, 'q': query, 'total_count': page.paginator.count}
    return directory_response(request, 'cinema/actors.html', context, {
        'kind': 'actors',
        'title': 'Diễn viên',
        'eyebrow': 'KHÁM PHÁ LUMIÈRE',
        'description': 'Tìm diễn viên và khám phá những bộ phim họ tham gia.',
        'items': [
            {'name': actor.name, 'count': actor.film_count, 'href': reverse('actor', args=[actor.pk])}
            for actor in page
        ],
        'query': query,
        'count': page.paginator.count,
        'url': reverse('actors'),
        'catalogUrl': reverse('catalog'),
        'addActorUrl': reverse('admin:cinema_actor_add') if request.user.has_perm('cinema.add_actor') else None,
        'pagination': {
            'page': page.number,
            'pages': page.paginator.num_pages,
            'previous': '?' + urlencode({'q': query, 'page': page.previous_page_number()}) if page.has_previous() else None,
            'next': '?' + urlencode({'q': query, 'page': page.next_page_number()}) if page.has_next() else None,
        },
    })


def actor_detail(request, pk):
    actor = get_object_or_404(Actor.objects.annotate(
        film_count=Count('movie', filter=Q(movie__published=True), distinct=True),
    ).filter(film_count__gt=0), pk=pk)
    return render(request, 'cinema/actor.html', {'actor': actor, 'movies': catalog_movies(request.user).filter(actors=actor)})


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


@login_required
def studio(request):
    if not request.user.is_staff: raise PermissionDenied
    from django.contrib import admin
    from .studio import build_dashboard_context
    context = {**admin.site.each_context(request), **build_dashboard_context(request.user), 'title': 'Tổng quan hệ thống'}
    return render(request, 'cinema/studio.html', context)
