import hashlib
import ipaddress
from urllib.parse import urlsplit

from django.conf import settings
from django.contrib.auth import logout
from django.core.cache import cache
from django.http import HttpResponse

from . import waf, waf_behavior


class SecurityMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if settings.TRUST_PROXY and request.META.get('REMOTE_ADDR') in settings.TRUSTED_PROXY_IPS:
            try:
                request.META['REMOTE_ADDR'] = str(ipaddress.ip_address(request.META.get('HTTP_X_REAL_IP', '')))
            except ValueError:
                return self.secure_response(request, HttpResponse('Invalid trusted proxy address.', status=400), rejected=True)
        if request.user.is_authenticated and not request.user.is_active:
            logout(request)

        waf_enabled = settings.WAF_MODE != 'off'
        rule = waf.strict_rule(request) if waf_enabled else None
        if rule:
            reason, status = rule
            waf_behavior.observe_rule_match(request)
            if settings.WAF_MODE == 'enforce':
                waf.record_event(request, waf.Action.BLOCKED, reason)
                response = HttpResponse('Yêu cầu bị tường lửa từ chối.', status=status, content_type='text/plain; charset=utf-8')
                return self.secure_response(request, response, rejected=True)
            waf.record_event(request, waf.Action.OBSERVED, reason)

        cooldown = waf_behavior.active_cooldown(request)
        if cooldown:
            seconds, assessment = cooldown
            waf.record_event(request, waf.Action.BLOCKED, waf.Reason.BEHAVIOR_COOLDOWN, assessment=assessment)
            response = HttpResponse('Tạm giới hạn truy cập. Vui lòng thử lại sau.', status=429)
            response['Retry-After'] = str(seconds)
            return self.secure_response(request, response, rejected=True)

        if request.method == 'POST' and self.rate_limited(request):
            if waf_enabled:
                waf.record_event(request, waf.Action.BLOCKED, waf.Reason.RATE_LIMIT)
            response = HttpResponse('Quá nhiều yêu cầu. Vui lòng thử lại sau một phút.', status=429)
            response['Retry-After'] = '60'
            return self.secure_response(request, response, rejected=True)

        response = self.get_response(request)
        if waf_enabled and not rule:
            assessment = waf.observe_response(request, response)
            waf_behavior.observe_response(request, response, assessment)
        return self.secure_response(request, response)

    @staticmethod
    def rate_limited(request):
        sensitive = request.path.startswith(('/accounts/', '/admin/login'))
        limit = 15 if sensitive else 120
        address = request.META.get('REMOTE_ADDR', '')
        identity = address if sensitive else str(request.user.pk or address)
        category = 'auth' if sensitive else 'write'
        key = 'rate:' + hashlib.sha256(f'{identity}:{category}'.encode()).hexdigest()
        if cache.add(key, 1, 60):
            return False
        try:
            return cache.incr(key) > limit
        except ValueError:
            return False

    @staticmethod
    def secure_response(request, response, *, rejected=False):
        payment_url = urlsplit(settings.VNPAY_URL)
        payment_origin = f'{payment_url.scheme}://{payment_url.netloc}'
        response['Content-Security-Policy'] = f"default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; media-src 'self' blob:; connect-src 'self'; worker-src 'self' blob:; frame-src https://www.youtube-nocookie.com; frame-ancestors 'none'; base-uri 'self'; form-action 'self' {payment_origin}"
        match = getattr(request, 'resolver_match', None)
        room_microphone = match and match.url_name == 'room' and getattr(response, 'allow_room_microphone', False)
        microphone_policy = '(self)' if room_microphone else '()'
        response['Permissions-Policy'] = f'camera=(), microphone={microphone_policy}, geolocation=()'
        if rejected or request.user.is_authenticated or request.path.startswith('/stream/'):
            response['Cache-Control'] = 'private, no-store'
        return response
