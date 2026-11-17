"""Request rules and local, aggregate traffic anomaly detection."""
import ipaddress
import re
from dataclasses import dataclass, field
from itertools import product
from math import log10

from django.core.cache import cache
from django.db import DatabaseError
from django.utils import timezone
from django.utils.crypto import salted_hmac
from django_redis.exceptions import ConnectionInterrupted
from redis.exceptions import RedisError

from .models import SecurityEvent


Action = SecurityEvent.Action
Reason = SecurityEvent.Reason
Area = SecurityEvent.Area
Signal = SecurityEvent.Signal
MAX_PATH_LENGTH = 4096
MAX_QUERY_LENGTH = 8192
MAX_QUERY_FIELDS = 128
EVENTS_PER_ACTION_PER_HOUR = 20
ROUTE_MISS_THRESHOLD = 12
ACCOUNTABLE_METHODS = frozenset(('GET', 'HEAD', 'POST', 'OPTIONS', 'PUT', 'PATCH', 'DELETE', 'TRACE', 'CONNECT'))
INVALID_PATH = re.compile(r'[\x00-\x1f\x7f\\]|(?:^|/)\.{1,2}(?:/|$)')
ANOMALY_ROUTES = {'/browse/': 'browse', '/actors/': 'actors'}
BASELINE_HOURS = 6
MIN_BASELINE_SAMPLES = 50
TRAINING_SAMPLE_SECONDS = 600
RARE_TAIL_PROBABILITY = 0.02
HIGH_RISK_SCORE = 70
QUERY_SHAPES = tuple(product(range(3), repeat=2))
CACHE_ERRORS = (ConnectionInterrupted, RedisError)
AREAS = {
    'accounts': Area.AUTH,
    'profile': Area.AUTH,
    'library': Area.AUTH,
    'admin': Area.STUDIO,
    'studio': Area.STUDIO,
    'browse': Area.CATALOG,
    'actors': Area.CATALOG,
    'genres': Area.CATALOG,
    'countries': Area.CATALOG,
    'movies': Area.CATALOG,
    'watch': Area.VIEWING,
    'stream': Area.VIEWING,
    'rooms': Area.ROOM,
    'vip': Area.PAYMENT,
    'checkout': Area.PAYMENT,
    'payments': Area.PAYMENT,
    'static': Area.ASSET,
    'media': Area.ASSET,
}


def strict_rule(request):
    """Inspect only the request target and method, before reading any request body."""
    path = request.path_info
    query = request.META.get('QUERY_STRING', '')
    if len(path) > MAX_PATH_LENGTH or len(query) > MAX_QUERY_LENGTH:
        return Reason.REQUEST_TARGET, 414
    if query.count('&') >= MAX_QUERY_FIELDS:
        return Reason.REQUEST_TARGET, 400
    if INVALID_PATH.search(path):
        return Reason.UNSAFE_PATH, 400
    if request.method in ('TRACE', 'CONNECT'):
        return Reason.INVALID_METHOD, 403
    return None


def request_area(request):
    first_segment = request.path_info[:48].lstrip('/').partition('/')[0]
    return AREAS.get(first_segment, Area.OTHER)


def client_address(request):
    try:
        return ipaddress.ip_address(request.META.get('REMOTE_ADDR', '')).compressed
    except ValueError:
        return None


def _source(request, now):
    ip = client_address(request)
    if not ip:
        return 'unknown'
    return salted_hmac('cinema.waf.source', f'{now.date()}|{ip}', algorithm='sha256').hexdigest()[:16]


def increment_counter(key, ttl):
    if cache.add(key, 1, ttl):
        return 1
    try:
        return cache.incr(key)
    except ValueError:
        # The key may expire between ADD and INCR.
        return int(cache.add(key, 1, ttl))


@dataclass(frozen=True)
class Assessment:
    risk_score: int
    signals: tuple[str, ...]
    baseline_samples: int | None = None
    behavior_metadata: dict[str, int] = field(default_factory=dict)


def record_event(request, action, reason, *, assessment=None):
    """Sample alerts before writing to the database. No raw request data is stored."""
    now = timezone.now()
    area = request_area(request)
    source = _source(request, now)
    method = request.method if request.method in ACCOUNTABLE_METHODS else 'OTHER'
    hour = int(now.timestamp()) // 3600
    budget_key = f'waf:budget:{action}:{hour}'
    dedup_key = f'waf:event:{action}:{reason}:{area}:{source}'
    try:
        if cache.get(budget_key, 0) >= EVENTS_PER_ACTION_PER_HOUR:
            return
        if not cache.add(dedup_key, True, 300):
            return
        count = increment_counter(budget_key, 3600)
        if 0 < count <= EVENTS_PER_ACTION_PER_HOUR:
            SecurityEvent.objects.create(
                action=action, reason=reason, area=area, method=method, source=source,
                risk_score=assessment.risk_score if assessment else None,
                baseline_samples=assessment.baseline_samples if assessment else None,
                signals=list(assessment.signals) if assessment else [],
                behavior_metadata=assessment.behavior_metadata if assessment else {},
            )
    except (*CACHE_ERRORS, DatabaseError):
        # Telemetry is best effort, including during migrations or an outage.
        return


def _shape_key(route, hour, shape):
    return f'waf:model:v2:{route}:{hour}:{shape[0]}:{shape[1]}'


def _baseline(route, hour):
    buckets = {
        _shape_key(route, previous, shape): shape
        for previous in range(hour - BASELINE_HOURS, hour)
        for shape in QUERY_SHAPES
    }
    counts = dict.fromkeys(QUERY_SHAPES, 0)
    for key, count in cache.get_many(buckets).items():
        counts[buckets[key]] += count
    return counts


def model_status():
    """Report the baseline currently used to score each catalog route."""
    hour = int(timezone.now().timestamp()) // 3600
    try:
        routes = []
        for label, route in ANOMALY_ROUTES.items():
            samples = sum(_baseline(route, hour).values())
            routes.append({'label': label, 'samples': samples, 'ready': samples >= MIN_BASELINE_SAMPLES})
        return routes
    except CACHE_ERRORS:
        return None


def _score_shape(shape, counts):
    length, fields = shape
    samples = sum(counts.values())
    if samples < MIN_BASELINE_SAMPLES:
        return None

    # Use smoothed upper-tail frequencies so rare, short requests are not flagged.
    patterns = (
        (Signal.LENGTH, length == 2, sum(count for (size, _), count in counts.items() if size >= length)),
        (Signal.FIELD_COUNT, fields == 2, sum(count for (_, count_band), count in counts.items() if count_band >= fields)),
        (Signal.COMBINATION, length > 0 and fields > 0,
         sum(count for (size, count_band), count in counts.items() if size >= length and count_band >= fields)),
    )
    rare = {
        signal: (matches + 1) / (samples + 2)
        for signal, eligible, matches in patterns
        if eligible and (matches + 1) / (samples + 2) <= RARE_TAIL_PROBABILITY
    }
    if not rare:
        return None
    risk_score = min(100, round(-30 * log10(min(rare.values()))))
    return Assessment(risk_score, tuple(rare), baseline_samples=samples)


def _observe_catalog_query(request, route):
    now = timezone.now()
    timestamp = int(now.timestamp())
    hour = timestamp // 3600
    query = request.META.get('QUERY_STRING', '')
    length = len(query)
    fields = query.count('&') + bool(query)
    shape = (int(length >= 128) + int(length >= 768), int(fields >= 5) + int(fields >= 12))

    if 2 in shape:
        alert = _score_shape(shape, _baseline(route, hour))
        if alert:
            record_event(request, Action.OBSERVED, Reason.QUERY_ANOMALY, assessment=alert)
            return alert

    source = _source(request, now)
    window = timestamp // TRAINING_SAMPLE_SECONDS
    sample_key = f'waf:sample:v2:{route}:{window}:{source}'
    if source != 'unknown' and cache.add(sample_key, True, TRAINING_SAMPLE_SECONDS):
        # Retain completed hours through the final hour in which they may be scored.
        increment_counter(_shape_key(route, hour, shape), (BASELINE_HOURS + 1) * 3600)


def observe_response(request, response):
    """Behavioral signals only create alerts, even in enforce mode."""
    try:
        if response.status_code in (404, 405):
            if request_area(request) in (Area.VIEWING, Area.ROOM, Area.PAYMENT, Area.ASSET):
                return
            now = timezone.now()
            minute = int(now.timestamp()) // 60
            source = _source(request, now)
            if increment_counter(f'waf:miss:{minute}:{source}', 90) == ROUTE_MISS_THRESHOLD:
                record_event(request, Action.OBSERVED, Reason.ROUTE_MISS_BURST)
            return
        route = ANOMALY_ROUTES.get(request.path_info)
        if request.method == 'GET' and response.status_code == 200 and route:
            return _observe_catalog_query(request, route)
    except CACHE_ERRORS:
        return
