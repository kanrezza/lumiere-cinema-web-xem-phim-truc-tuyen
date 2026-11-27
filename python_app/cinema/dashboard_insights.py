"""Date-scoped metrics with no inferred revenue or fabricated activity."""
from datetime import datetime, time, timedelta
from urllib.parse import urlencode

from django.db.models import Count, Sum
from django.db.models.functions import TruncDate
from django.urls import reverse
from django.utils import timezone

from .content_health import HEALTH_LABELS, health_queryset, permitted_health_checks
from .models import Movie, Order, User


PERIODS = (7, 30, 90)


def dashboard_insights(user, period='30', *, orders=False, users=False, now=None):
    if not user.is_authenticated or not user.is_active or not user.is_staff:
        return None
    orders = orders and (user.has_perm('cinema.view_order') or user.has_perm('cinema.change_order'))
    users = users and (user.has_perm('cinema.view_user') or user.has_perm('cinema.change_user'))
    days = int(period) if str(period) in ('7', '30', '90') else 30
    now = now or timezone.now()
    local = timezone.localtime(now)
    start_date = local.date() - timedelta(days=days - 1)
    start = timezone.make_aware(datetime.combine(start_date, time.min), timezone.get_current_timezone())
    previous_start = start - timedelta(days=days)
    checks = permitted_health_checks(user)
    result = {
        'available': bool(orders or users or checks), 'days': days,
        'start': start, 'now': now, 'start_date': start_date, 'end_date': local.date(),
        'periods': [{'days': item, 'selected': item == days, 'href': '?' + urlencode({'period': item})} for item in PERIODS],
        'revenue': None, 'paid_count': None, 'previous_revenue': None,
        'revenue_change': None, 'new_users': None, 'expiring_vips': None,
        'chart': [], 'health': [],
    }
    if orders:
        paid = Order.objects.filter(status='paid', paid_at__gte=previous_start, paid_at__lte=now)
        current = paid.filter(paid_at__gte=start)
        totals = current.aggregate(revenue=Sum('amount'), count=Count('pk'))
        previous = paid.filter(paid_at__lt=start).aggregate(revenue=Sum('amount'))['revenue'] or 0
        revenue = totals['revenue'] or 0
        result.update(revenue=revenue, paid_count=totals['count'], previous_revenue=previous,
                      revenue_change=round((revenue - previous) / previous * 100, 1) if previous else None)
        daily = {item['day']: item for item in current.annotate(
            day=TruncDate('paid_at', tzinfo=timezone.get_current_timezone()),
        ).values('day').annotate(amount=Sum('amount'), orders=Count('pk')).order_by('day')}
        # MySQL deployments without loaded timezone tables return NULL from
        # CONVERT_TZ. Preserve accurate local dates with bounded-memory reads.
        if None in daily:
            daily = {}
            for timestamp, amount in current.values_list('paid_at', 'amount').iterator(chunk_size=512):
                day = timezone.localdate(timestamp)
                item = daily.setdefault(day, {'amount': 0, 'orders': 0})
                item['amount'] += amount
                item['orders'] += 1
        peak = max((item['amount'] for item in daily.values()), default=0)
        width = 720 / days
        for index in range(days):
            day = start_date + timedelta(days=index)
            item = daily.get(day, {'amount': 0, 'orders': 0})
            height = round(item['amount'] / peak * 110, 2) if peak else 0
            result['chart'].append({
                'date': day, 'amount': item['amount'], 'orders': item['orders'],
                'x': format(index * width + 1, '.2f'), 'y': format(120 - height, '.2f'),
                'width': format(max(1, width - 2), '.2f'), 'height': format(height, '.2f'),
            })
    if users:
        result['new_users'] = User.objects.filter(date_joined__gte=start, date_joined__lte=now, erased_at__isnull=True).count()
        result['expiring_vips'] = User.objects.filter(is_active=True, erased_at__isnull=True, vip_until__gt=now,
                                                    vip_until__lte=now + timedelta(days=7)).count()
    for issue in checks:
        queryset = health_queryset(Movie.objects.all(), issue)
        result['health'].append({
            'label': HEALTH_LABELS[issue], 'count': queryset.count(),
            'url': reverse('admin:cinema_movie_changelist') + '?' + urlencode({'health': issue}),
            'issue': issue,
        })
    return result
