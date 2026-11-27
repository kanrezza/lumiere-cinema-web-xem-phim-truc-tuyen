"""Paid VIP periods: one continuous entitlement, with an auditable queue."""

from datetime import timedelta

from django.utils import timezone

from .models import Order


def membership_timeline(user, now=None):
    now = timezone.now() if now is None else now
    empty = {'current': None, 'queued': [], 'current_until': None, 'active_until': None}
    if not user.is_authenticated or not user.is_active or user.erased_at or not user.vip_until or user.vip_until <= now:
        return empty
    periods = Order.objects.filter(
        user=user, status='paid', period_start__isnull=False, period_end__gt=now,
        period_end__lte=user.vip_until,
    ).select_related('plan').order_by('period_start', 'pk')
    current = None
    queued = []
    for period in periods:
        if period.period_start <= now:
            current = period
        else:
            queued.append(period)
    return {
        'current': current, 'queued': queued,
        'current_until': current.period_end if current else (queued[0].period_start if queued else user.vip_until),
        'active_until': user.vip_until,
    }


def renewal_previews(user, plans, now=None):
    """Display estimates only; IPN always computes the actual period under lock."""
    now = timezone.now() if now is None else now
    expiry = user.vip_until if user.is_authenticated and user.is_active and not user.erased_at else None
    start = max(expiry or now, now)
    for plan in plans:
        plan.renewal_start = start
        plan.renewal_end = start + timedelta(days=plan.days)
    return plans
