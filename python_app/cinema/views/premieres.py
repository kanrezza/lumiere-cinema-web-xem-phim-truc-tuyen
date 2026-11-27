"""Public screening discovery, a moderated chat and permission-gated controls."""

from django.contrib.admin.models import CHANGE, LogEntry
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST, require_http_methods

from ..models import Premiere, PremiereMessage
from ..moderation import classify_comment_v1
from ..premieres import can_manage_premieres, can_view_premiere, premiere_phase, premiere_state


def _visible_screening(request, pk):
    rows = Premiere.objects.select_related('episode__movie')
    if not can_manage_premieres(request.user):
        rows = rows.filter(episode__movie__published=True)
    return get_object_or_404(rows, pk=pk)


@require_GET
def premieres(request):
    rows = Premiere.objects.filter(
        episode__movie__published=True, episode__status='ready',
    ).exclude(status=Premiere.Status.CANCELLED).select_related('episode__movie')
    page = Paginator(rows, 18).get_page(request.GET.get('page'))
    now = timezone.now()
    screenings = [{'premiere': screening, 'state': premiere_state(screening, request.user, now, include_messages=False)} for screening in page]
    return render(request, 'cinema/premieres.html', {
        'premieres': page, 'screenings': screenings,
        'can_manage_premiere': can_manage_premieres(request.user),
    })


@login_required
@require_GET
@never_cache
def premiere(request, pk):
    screening = _visible_screening(request, pk)
    state = premiere_state(screening, request.user)
    return render(request, 'cinema/premiere.html', {
        'premiere': screening, 'episode': screening.episode, 'premiere_state': state,
        'can_manage_premiere': state['can_manage'], 'can_watch_premiere': state['can_watch'],
        'premiere_ticket_url': state['ticket_url'],
    })


@login_required
@require_http_methods(['GET', 'POST'])
@never_cache
def premiere_state_view(request, pk):
    screening = _visible_screening(request, pk)
    if request.method == 'POST':
        if not can_view_premiere(request.user, screening):
            raise PermissionDenied('Suất chiếu này cần quyền xem phù hợp.')
        if request.POST.get('action') != 'chat':
            return JsonResponse({'error': 'Thao tác không hợp lệ.'}, status=400)
        if premiere_phase(screening) not in (Premiere.Status.SCHEDULED, Premiere.Status.LIVE):
            return JsonResponse({'error': 'Trò chuyện của buổi công chiếu đã đóng.'}, status=409)
        content = request.POST.get('content', '').strip()
        if not 1 <= len(content) <= 500:
            return JsonResponse({'error': 'Tin nhắn cần 1–500 ký tự.'}, status=400)
        if not cache.add(f'premiere-chat:{pk}:{request.user.pk}', 1, timeout=2):
            response = JsonResponse({'error': 'Bạn đang gửi quá nhanh. Vui lòng đợi 2 giây.'}, status=429)
            response['Retry-After'] = '2'
            return response
        matches = classify_comment_v1(content)
        PremiereMessage.objects.create(premiere=screening, user=request.user, content=content, hidden=bool(matches), moderation_matches=matches)
        state = premiere_state(screening, request.user)
        if matches:
            state['notice'] = 'Tin nhắn đang chờ quản trị viên kiểm duyệt.'
        return JsonResponse(state)
    return JsonResponse(premiere_state(screening, request.user))


@login_required
@require_POST
@never_cache
def premiere_control(request, pk):
    if not can_manage_premieres(request.user):
        raise PermissionDenied('Bạn chưa được cấp quyền tổ chức công chiếu.')
    with transaction.atomic():
        screening = get_object_or_404(Premiere.objects.select_for_update().select_related('episode__movie'), pk=pk)
        if request.POST.get('state_version') != str(screening.state_version):
            return JsonResponse({**premiere_state(screening, request.user), 'error': 'Suất chiếu vừa thay đổi. Vui lòng kiểm tra lại.'}, status=409)
        action = request.POST.get('action')
        phase = premiere_phase(screening)
        now = timezone.now()
        if action == 'start' and phase == Premiere.Status.SCHEDULED:
            if not can_view_premiere(request.user, screening):
                raise PermissionDenied('Nguồn phim chưa sẵn sàng để công chiếu.')
            screening.status = Premiere.Status.LIVE
            screening.started_at = now
        elif action == 'end' and phase == Premiere.Status.LIVE:
            screening.status = Premiere.Status.ENDED
            screening.ended_at = now
        elif action == 'cancel' and phase == Premiere.Status.SCHEDULED:
            screening.status = Premiere.Status.CANCELLED
            screening.ended_at = now
        else:
            return JsonResponse({'error': 'Không thể thực hiện thao tác ở trạng thái hiện tại.'}, status=400)
        screening.state_version += 1
        screening.save(update_fields=['status', 'started_at', 'ended_at', 'state_version', 'updated_at'])
        LogEntry.objects.log_actions(
            user_id=request.user.pk, queryset=Premiere.objects.filter(pk=screening.pk),
            action_flag=CHANGE, change_message=f'Công chiếu: {action}', single_object=True,
        )
        return JsonResponse(premiere_state(screening, request.user, now))
