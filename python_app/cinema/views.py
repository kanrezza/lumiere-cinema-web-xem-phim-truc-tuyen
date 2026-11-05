import math
import re
from contextlib import suppress
from datetime import timedelta
from urllib.parse import urlencode
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.core import signing
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Avg, Q, Sum, Count, OuterRef, Subquery, F, IntegerField
from django.db.models.functions import Cast, Ceil
from django.http import FileResponse, Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.crypto import salted_hmac
from django.views.decorators.http import require_POST, require_GET, require_http_methods
from .forms import RegisterForm, ProfileForm, AvatarForm
from .avatars import is_managed_avatar
from .models import *
from .payments import checkout_url, process_ipn
from .search import filter_movie_search, filter_actor_search


def can_watch(user, episode):
    return user.is_authenticated and user.is_active and episode.movie.published and episode.status == 'ready' and (not episode.movie.is_vip or user.is_vip or user.is_staff)


def require_watch(user, episode):
    if not can_watch(user, episode): raise PermissionDenied('Bạn chưa có quyền xem hoặc video chưa sẵn sàng.')


def catalog_movies():
    """Public movie cards carry a real playback target, never a placeholder URL."""
    ready = Episode.objects.filter(movie_id=OuterRef('pk'), status='ready').order_by('number', 'pk')
    return Movie.objects.filter(published=True).prefetch_related('categories').annotate(
        score=Avg('ratings__score'),
        ready_episode_id=Subquery(ready.values('pk')[:1]),
        duration_minutes=Cast(Ceil(Subquery(ready.values('duration')[:1]) / 60.0), IntegerField()),
    ).order_by('-created_at', '-pk')



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
    if query:
        items = [item for item in items if query.casefold() in item['name'].casefold()]
    return render(request, 'cinema/discovery_index.html', {
        'title': title, 'eyebrow': eyebrow, 'description': description,
        'discovery_kind': kind, 'items': items, 'q': query, 'total_count': total_count,
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
        item.position_minutes = int(position // 60)
    return cards



def landing(request):
    """Public introduction stays distinct from the signed-in movie browser."""
    # Existing bookmarked filter links remain useful after moving discovery.
    if any(request.GET.get(key) for key in ('q', 'category', 'country', 'actor', 'year', 'kind', 'sort', 'page', 'access')):
        return redirect(reverse('catalog') + '?' + request.GET.urlencode())
    movies = catalog_movies()
    return render(request, 'cinema/landing.html', {
        'landing_movies': list(movies[:7]),
        'featured': movies.filter(is_vip=False, ready_episode_id__isnull=False).first() or movies.filter(ready_episode_id__isnull=False).first() or movies.first(),
        'plans': Plan.objects.filter(active=True).order_by('price', 'pk'),
        'free_movie_count': movies.filter(is_vip=False).count(),
        'vip_movie_count': movies.filter(is_vip=True).count(),
        'landing_categories': Category.objects.filter(movie__published=True).distinct().order_by('name'),
    })

def catalog(request):
    movies = catalog_movies()
    featured = movies.filter(ready_episode_id__isnull=False).first()
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
    is_browsing = any(request.GET.get(key) for key in ('q', 'category', 'country', 'actor', 'year', 'kind', 'sort', 'page', 'access'))
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
        if request.user.is_authenticated:
            continue_watching = history_cards(History.objects.filter(
                user=request.user, episode__movie__published=True, episode__status='ready',
                episode__duration__gt=0, position__gt=0, position__lt=F('episode__duration') - 1,
            ).select_related('episode__movie')[:12])
    return render(request, 'cinema/catalog.html', {
        'page': Paginator(filtered.distinct(), 12).get_page(request.GET.get('page')),
        'featured': featured, 'categories': categories, 'q': q, 'category': category,
        'is_browsing': is_browsing, 'shelves': shelves, 'continue_watching': continue_watching,
        'featured_movies': featured_movies,
        'countries': country_options, 'selected_country': selected_country,
        'years': years, 'selected_year': selected_year,
        'selected_category': selected_category, 'selected_actor': selected_actor, 'actor_filter': actor_filter,
    })


def register(request):
    if request.user.is_authenticated:
        return redirect('catalog')
    form = RegisterForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        login(request, form.save())
        return redirect('catalog')
    return render(request, 'registration/form.html', {'form': form, 'title': 'Tạo tài khoản', 'subtitle': 'Một tài khoản. Cả thế giới điện ảnh.', 'button': 'Bắt đầu khám phá'})


def movie_detail(request, slug):
    movie = get_object_or_404(catalog_movies().prefetch_related('actors'), slug=slug)
    episodes = list(movie.episodes.all())
    first_ready_episode = next((episode for episode in episodes if episode.status == 'ready'), None)
    related = catalog_movies().filter(categories__in=movie.categories.all()).exclude(pk=movie.pk).distinct()[:8]
    return render(request, 'cinema/movie.html', {
        'movie': movie, 'episodes': episodes, 'first_ready_episode': first_ready_episode,
        'comments': movie.comments.select_related('user')[:50], 'score': movie.score,
        'saved': request.user.is_authenticated and Watchlist.objects.filter(user=request.user, movie=movie).exists(),
        'related': related,
    })


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
    if 1 <= len(content) <= 1000: Comment.objects.create(user=request.user, movie=movie, content=content)
    return redirect('movie', slug=movie.slug)


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
        'movies': catalog_movies().filter(watchlist__user=request.user),
        'history': history_cards(History.objects.filter(user=request.user, episode__movie__published=True, episode__status='ready').select_related('episode__movie')[:30]),
    })


@login_required
def profile(request):
    form = ProfileForm(request.POST or None, instance=request.user)
    if request.method == 'POST' and form.is_valid():
        form.save()
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
    episodes = list(episode.movie.episodes.filter(status='ready'))
    next_episode = next((item for item in episodes if item.number > episode.number), None)
    return render(request, 'cinema/watch.html', {
        'episode': episode, 'position': history.position if history else 0,
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
    History.objects.update_or_create(user=request.user, episode=episode, defaults={'position': position})
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
    first_ready = catalog_movies().filter(ready_episode_id__isnull=False).first() if member_dashboard else None
    watch_together_url = reverse('watch', args=[first_ready.ready_episode_id]) + '#watch-together' if first_ready else reverse('catalog')
    return render(request, 'cinema/plans.html', {
        'plans': Plan.objects.filter(active=True).order_by('price'),
        'payment_ready': bool(settings.VNPAY_TMN_CODE and settings.VNPAY_HASH_SECRET),
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
    plan = get_object_or_404(Plan, pk=pk, active=True)
    if not settings.VNPAY_TMN_CODE or not settings.VNPAY_HASH_SECRET:
        messages.error(request, 'VNPay chưa được cấu hình. Chưa tạo giao dịch hoặc thu tiền.')
        return redirect('plans')
    order = Order.objects.create(user=request.user, plan=plan, amount=plan.price, days=plan.days)
    return redirect(checkout_url(order, request.META.get('REMOTE_ADDR', '127.0.0.1')))


@require_GET
def ipn(request): return JsonResponse(process_ipn(request.GET))


@login_required
def payment_return(request):
    # Browser redirects never grant VIP. Only signed server IPN mutates an order.
    messages.info(request, 'Đã trở về từ VNPay. Trạng thái đơn hàng sẽ cập nhật sau khi nhận xác nhận từ cổng thanh toán.')
    return redirect('profile')


@login_required
@require_POST
def create_room(request, pk):
    episode = get_object_or_404(Episode.objects.select_related('movie'), pk=pk)
    require_watch(request.user, episode)
    if not request.user.is_vip and not request.user.is_staff: raise PermissionDenied('VIP mới có thể tạo phòng.')
    with transaction.atomic():
        User.objects.select_for_update().get(pk=request.user.pk)
        if Room.objects.filter(host=request.user, closed=False, created_at__gt=timezone.now() - timedelta(hours=6)).count() >= 3:
            messages.error(request, 'Bạn đã có 3 phòng đang hoạt động.')
            return redirect('watch', pk=pk)
        room = Room.objects.create(host=request.user, episode=episode, name=request.POST.get('name', '').strip()[:100] or episode.movie.title[:100])
        Membership.objects.create(room=room, user=request.user)
    return redirect('room', pk=room.pk)


def accessible_room(request, pk, lock=False):
    qs = Room.objects.select_related('episode__movie', 'host')
    if lock: qs = qs.select_for_update()
    room = get_object_or_404(qs, pk=pk, closed=False, created_at__gt=timezone.now() - timedelta(hours=6))
    require_watch(request.user, room.episode)
    if not (room.host.is_active and (room.host.is_vip or room.host.is_staff)): raise PermissionDenied('Quyền tạo phòng của chủ phòng đã hết hạn.')
    return room


@login_required
def room(request, pk):
    room = accessible_room(request, pk)
    member = Membership.objects.filter(room=room, user=request.user).first()
    if member and member.banned: raise PermissionDenied('Bạn đã bị loại khỏi phòng.')
    if not member or not member.active: return render(request, 'cinema/join.html', {'room': room})
    return render(request, 'cinema/room.html', {'room': room, 'episode': room.episode, 'is_host': room.host_id == request.user.pk, 'position': room.position})


@login_required
@require_POST
def join_room(request, pk):
    with transaction.atomic():
        room = accessible_room(request, pk, lock=True)
        member = Membership.objects.filter(room=room, user=request.user).first()
        if member and member.banned: raise PermissionDenied
        if room.members.filter(banned=False, active=True, last_seen__gt=timezone.now() - timedelta(seconds=30)).exclude(user=request.user).count() >= 10:
            return HttpResponse('Phòng đã đủ 10 thành viên.', status=409)
        Membership.objects.update_or_create(room=room, user=request.user, defaults={'active': True, 'last_seen': timezone.now()})
    return redirect('room', pk=pk)


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
                elif action == 'kick':
                    try: target = int(request.POST.get('user', ''))
                    except (ValueError, TypeError): return JsonResponse({'error': 'Thành viên không hợp lệ'}, status=400)
                    Membership.objects.filter(room=room, user_id=target, banned=False).exclude(user=room.host).update(banned=True, active=False)
                elif action == 'sync':
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
        position = min(room.episode.duration, room.position + ((timezone.now() - room.updated_at).total_seconds() if room.playing else 0))
        chats = list(Chat.objects.filter(room=room).select_related('user').order_by('-id')[:60])
        return JsonResponse({'position': position, 'playing': room.playing, 'closed': room.closed, 'members': list(room.members.filter(banned=False, active=True, last_seen__gt=timezone.now() - timedelta(seconds=30)).values('user_id', 'user__username')), 'messages': [{'id': c.pk, 'user': c.user.username, 'content': c.content} for c in reversed(chats)]})


@login_required
@require_POST
def leave_room(request, pk):
    room = get_object_or_404(Room, pk=pk)
    Membership.objects.filter(room=room, user=request.user).update(active=False)
    if room.host_id == request.user.pk:
        room.closed = True
        room.save(update_fields=['closed'])
    return redirect('library')


def actors(request):
    query = request.GET.get('q', '').strip()[:150]
    people = Actor.objects.annotate(
        film_count=Count('movie', filter=Q(movie__published=True), distinct=True),
    ).filter(film_count__gt=0).order_by('name', 'pk')
    if query: people = filter_actor_search(people, query)
    page = Paginator(people, 24).get_page(request.GET.get('page'))
    return render(request, 'cinema/actors.html', {'actors': page, 'q': query, 'total_count': page.paginator.count})


def actor_detail(request, pk):
    actor = get_object_or_404(Actor.objects.annotate(
        film_count=Count('movie', filter=Q(movie__published=True), distinct=True),
    ).filter(film_count__gt=0), pk=pk)
    return render(request, 'cinema/actor.html', {'actor': actor, 'movies': catalog_movies().filter(actors=actor)})


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
    if comment.user_id != request.user.pk and not request.user.is_staff: raise PermissionDenied
    slug = comment.movie.slug
    comment.delete()
    return redirect('movie', slug=slug)


@login_required
def studio(request):
    if not request.user.is_staff: raise PermissionDenied
    totals = Order.objects.filter(status='paid').aggregate(revenue=Sum('amount'), count=Count('id'))
    return render(request, 'cinema/studio.html', {
        'movies_count': Movie.objects.count(), 'users_count': User.objects.count(),
        'vip_count':User.objects.filter(is_active=True, vip_until__gt=timezone.now()).count(),
        'revenue':totals['revenue'] or 0, 'paid_count':totals['count'],
        'episodes':Episode.objects.select_related('movie').order_by('-id')[:12],
        'orders':Order.objects.select_related('user', 'plan').order_by('-created_at')[:10],
        'reports':Report.objects.filter(resolved=False).select_related('episode__movie')[:10],
    })
