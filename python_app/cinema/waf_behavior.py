"""Correlate short-lived security signals and limit anonymous public requests."""
from collections import Counter

from django.conf import settings
from django.contrib.auth.signals import user_login_failed
from django.core.cache import cache
from django.dispatch import receiver
from django.utils import timezone
from django.utils.crypto import salted_hmac

from . import waf


BEHAVIOR_WINDOW_SECONDS = 120
BUCKET_SECONDS = 30
COOLDOWN_SECONDS = 90
TRACKED_AREAS = (waf.Area.AUTH, waf.Area.STUDIO, waf.Area.CATALOG, waf.Area.OTHER)
COOLDOWN_AREAS = (waf.Area.CATALOG, waf.Area.OTHER)
LOGIN_PATHS = ('/accounts/login/', '/admin/login/')
SIGNAL_WEIGHTS = {
    waf.Signal.ROUTE_MISSES: (8, 3, 35),
    waf.Signal.RULE_MATCHES: (2, 15, 40),
    waf.Signal.DENIED: (3, 10, 35),
    waf.Signal.LOGIN_FAILURES: (6, 6, 40),
    waf.Signal.QUERY_ANOMALIES: (2, 9, 24),
}


def mitigation_enabled():
    return settings.WAF_MODE == 'enforce' and settings.WAF_BEHAVIOR_MITIGATION


@receiver(user_login_failed, dispatch_uid='cinema.waf_behavior.failed_login')
def mark_failed_login(sender, request, **kwargs):
    if request is not None and request.path_info in LOGIN_PATHS and settings.WAF_MODE != 'off':
        request.waf_login_failed = True


def _anonymous_source(request):
    if request.user.is_authenticated:
        return None
    address = waf.client_address(request)
    if not address:
        return None
    return salted_hmac('cinema.waf.behavior', address, algorithm='sha256').hexdigest()[:24]


def _cooldown_key(source):
    return f'waf:behavior:cooldown:{source}'


def active_cooldown(request):
    """Return the remaining time and evidence for restricted public requests."""
    if not mitigation_enabled() or request.method not in ('GET', 'HEAD') or waf.request_area(request) not in COOLDOWN_AREAS:
        return None
    source = _anonymous_source(request)
    if not source:
        return None
    try:
        entry = cache.get(_cooldown_key(source))
        if entry:
            until, score, signals, metadata = entry
            remaining = until - int(timezone.now().timestamp())
            if remaining > 0:
                return remaining, waf.Assessment(score, signals, behavior_metadata=metadata)
    except waf.CACHE_ERRORS:
        return None
    return None


def _evidence(source, bucket):
    oldest = bucket - (BEHAVIOR_WINDOW_SECONDS // BUCKET_SECONDS) + 1
    keys = {
        f'waf:behavior:{source}:{slot}:{signal}:{area}': (signal, area)
        for slot in range(oldest, bucket + 1)
        for signal in SIGNAL_WEIGHTS
        for area in TRACKED_AREAS
    }
    totals = dict.fromkeys(SIGNAL_WEIGHTS, 0)
    counts_by_area = Counter()
    for key, count in cache.get_many(keys).items():
        signal, area = keys[key]
        totals[signal] += count
        counts_by_area[signal, area] += count
    return totals, counts_by_area


def _confirmed_areas(signals, counts_by_area):
    return sum(
        sum(counts_by_area[signal, area] for signal in signals) >= 2
        for area in TRACKED_AREAS
    )


def _record_signal(request, signal):
    area = waf.request_area(request)
    if area not in TRACKED_AREAS:
        return
    source = _anonymous_source(request)
    if not source:
        return

    timestamp = int(timezone.now().timestamp())
    bucket = timestamp // BUCKET_SECONDS
    try:
        key = f'waf:behavior:{source}:{bucket}:{signal}:{area}'
        waf.increment_counter(key, BEHAVIOR_WINDOW_SECONDS)
        evidence, counts_by_area = _evidence(source, bucket)
        weights = {
            kind: min(evidence[kind] * weight, cap)
            for kind, (minimum, weight, cap) in SIGNAL_WEIGHTS.items()
            if evidence[kind] >= minimum
        }
        evidence[waf.Signal.AREAS] = _confirmed_areas(weights, counts_by_area)
        widespread = evidence[waf.Signal.AREAS] >= 2
        diversity_bonus = 15 if widespread else 0
        score = min(100, sum(weights.values()) + diversity_bonus)
        if len(weights) < 2 or score < waf.HIGH_RISK_SCORE:
            return

        signals = tuple(weights) + ((waf.Signal.AREAS,) if widespread else ())
        assessment = waf.Assessment(score, signals, behavior_metadata=evidence)
        core = {kind: weight for kind, weight in weights.items() if kind != waf.Signal.QUERY_ANOMALIES}
        if (
            mitigation_enabled() and len(core) >= 2 and _confirmed_areas(core, counts_by_area) >= 2
            and sum(core.values()) + diversity_bonus >= waf.HIGH_RISK_SCORE
        ):
            cache.add(_cooldown_key(source), (timestamp + COOLDOWN_SECONDS, score, signals, evidence), COOLDOWN_SECONDS)
        waf.record_event(request, waf.Action.OBSERVED, waf.Reason.BEHAVIOR_ANOMALY, assessment=assessment)
    except waf.CACHE_ERRORS:
        return


def observe_rule_match(request):
    _record_signal(request, waf.Signal.RULE_MATCHES)


def observe_response(request, response, query_assessment):
    if getattr(request, 'waf_login_failed', False) and response.status_code in (200, 401, 403):
        _record_signal(request, waf.Signal.LOGIN_FAILURES)
    elif response.status_code in (404, 405):
        _record_signal(request, waf.Signal.ROUTE_MISSES)
    elif response.status_code in (401, 403):
        _record_signal(request, waf.Signal.DENIED)
    elif query_assessment and query_assessment.risk_score >= waf.HIGH_RISK_SCORE:
        _record_signal(request, waf.Signal.QUERY_ANOMALIES)
