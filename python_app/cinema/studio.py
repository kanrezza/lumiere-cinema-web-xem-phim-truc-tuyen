"""Read-only dashboard summaries and permission-aware Studio navigation."""
from django.db.models import Count, Q, Sum
from django.urls import reverse
from django.utils import timezone

from .models import Episode, Movie, Order, Report, User


MODEL_LABELS = {
    'movie': ('phim', 'Phim'),
    'episode': ('tập phim', 'Tập phim'),
    'subtitle': ('phụ đề', 'Phụ đề'),
    'category': ('thể loại', 'Thể loại'),
    'actor': ('diễn viên', 'Diễn viên'),
    'user': ('người dùng', 'Người dùng'),
    'plan': ('gói VIP', 'Gói VIP'),
    'order': ('giao dịch', 'Giao dịch'),
    'comment': ('bình luận', 'Bình luận'),
    'rating': ('đánh giá', 'Đánh giá'),
    'room': ('phòng xem', 'Phòng xem'),
    'report': ('báo lỗi', 'Báo lỗi'),
    'group': ('nhóm quyền', 'Nhóm quyền'),
}

NAVIGATION = (
    ('Thư viện', (
        ('cinema', 'movie', 'film'),
        ('cinema', 'episode', 'video'),
        ('cinema', 'subtitle', 'captions'),
        ('cinema', 'category', 'genres'),
        ('cinema', 'actor', 'actors'),
    )),
    ('Thành viên & doanh thu', (
        ('cinema', 'user', 'users'),
        ('cinema', 'plan', 'crown'),
        ('cinema', 'order', 'receipt'),
    )),
    ('Cộng đồng', (
        ('cinema', 'comment', 'chat'),
        ('cinema', 'rating', 'star'),
        ('cinema', 'room', 'room'),
        ('cinema', 'report', 'flag'),
    )),
    ('Hệ thống', (('auth', 'group', 'shield'),)),
)


def is_studio_user(user):
    return bool(user and user.is_authenticated and user.is_active and user.is_staff)


def can_view(user, model, app='cinema'):
    return is_studio_user(user) and (
        user.has_perm(f'{app}.view_{model}') or user.has_perm(f'{app}.change_{model}')
    )


def can_add(user, model, app='cinema'):
    return is_studio_user(user) and user.has_perm(f'{app}.add_{model}')


def build_navigation(user, path=''):
    """Only show destinations the current account can actually open."""
    if not is_studio_user(user):
        return []
    sections = [{
        'label': 'Không gian quản trị',
        'items': [{
            'label': 'Tổng quan', 'url': reverse('studio'), 'icon': 'grid',
            'active': path.rstrip('/') in ('/admin', '/studio'),
        }],
    }]
    for label, entries in NAVIGATION:
        items = []
        for app, model, icon in entries:
            viewable = can_view(user, model, app)
            if not viewable and not can_add(user, model, app):
                continue
            list_url = reverse(f'admin:{app}_{model}_changelist')
            items.append({
                'label': MODEL_LABELS[model][1], 'icon': icon,
                'url': list_url if viewable else reverse(f'admin:{app}_{model}_add'),
                'active': path.startswith(list_url),
            })
        if items:
            sections.append({'label': label, 'items': items})
    return sections


def build_dashboard_context(user):
    """Summarize only domains the staff account may view in Django admin."""
    context = {
        'has_permission': is_studio_user(user),
        'studio_dashboard': True,
        'dashboard_available': False,
        'movies_count': None, 'published_movies_count': None, 'draft_count': None,
        'users_count': None, 'vip_count': None,
        'revenue': None, 'paid_count': None,
        'ready_episodes_count': None, 'processing_episodes_count': None,
        'failed_episodes_count': None, 'unresolved_reports_count': None,
        'ready_count': None, 'processing_count': None, 'failed_count': None,
        'episodes': [], 'orders': [], 'reports': [],
    }
    for name, model in (
        ('movies', 'movie'), ('episodes', 'episode'), ('users', 'user'),
        ('plans', 'plan'), ('reports', 'report'),
    ):
        context[f'can_manage_{name}'] = can_view(user, model)
    context['can_view_orders'] = can_view(user, 'order')
    for model in ('movie', 'episode', 'actor'):
        context[f'can_add_{model}'] = can_add(user, model)
    context['can_add_movies'] = context['can_add_movie']
    context['can_add_episodes'] = context['can_add_episode']
    if not context['has_permission']:
        return context
    context['dashboard_available'] = any(
        can_view(user, model, app) or can_add(user, model, app)
        for _, entries in NAVIGATION for app, model, _ in entries
    )
    if context['can_manage_movies']:
        totals = Movie.objects.aggregate(
            total=Count('pk'), published_total=Count('pk', filter=Q(published=True)),
            draft=Count('pk', filter=Q(published=False)),
        )
        context.update(movies_count=totals['total'], published_movies_count=totals['published_total'], draft_count=totals['draft'])
    if context['can_manage_users']:
        totals = User.objects.aggregate(
            total=Count('pk'), vip=Count('pk', filter=Q(is_active=True, vip_until__gt=timezone.now())),
        )
        context.update(users_count=totals['total'], vip_count=totals['vip'])
    if context['can_manage_episodes']:
        totals = Episode.objects.aggregate(
            ready=Count('pk', filter=Q(status='ready')),
            processing=Count('pk', filter=Q(status__in=('pending', 'processing'))),
            failed=Count('pk', filter=Q(status='failed')),
        )
        context.update(
            ready_episodes_count=totals['ready'], processing_episodes_count=totals['processing'],
            failed_episodes_count=totals['failed'], ready_count=totals['ready'],
            processing_count=totals['processing'], failed_count=totals['failed'],
            episodes=Episode.objects.select_related('movie').order_by('-id')[:8],
        )
    if context['can_view_orders']:
        totals = Order.objects.filter(status='paid').aggregate(revenue=Sum('amount'), count=Count('pk'))
        context.update(
            revenue=totals['revenue'] or 0, paid_count=totals['count'],
            orders=Order.objects.select_related('user', 'plan').order_by('-created_at')[:5],
        )
    if context['can_manage_reports']:
        unresolved = Report.objects.filter(resolved=False)
        context.update(
            unresolved_reports_count=unresolved.count(),
            reports=unresolved.select_related('episode__movie').order_by('-created_at')[:5],
        )
    return context
