import hashlib
import ipaddress
from urllib.parse import urlsplit
from django.conf import settings
from django.core.cache import cache
from django.http import HttpResponse
from django.contrib.auth import logout

class SecurityMiddleware:
    def __init__(self, get_response): self.get_response = get_response
    def __call__(self, request):
        if settings.TRUST_PROXY and request.META.get('REMOTE_ADDR') in settings.TRUSTED_PROXY_IPS:
            try:
                request.META['REMOTE_ADDR'] = str(ipaddress.ip_address(request.META.get('HTTP_X_REAL_IP', '')))
            except ValueError:
                return HttpResponse('Invalid trusted proxy address.', status=400)
        if request.user.is_authenticated and not request.user.is_active:
            logout(request)
        if request.method == 'POST':
            sensitive = request.path.startswith(('/accounts/', '/admin/login'))
            limit = 15 if sensitive else 120
            identity = request.META.get('REMOTE_ADDR', '') if sensitive else str(request.user.pk or request.META.get('REMOTE_ADDR', ''))
            key = 'rate:' + hashlib.sha256((identity + (':auth' if sensitive else ':write')).encode()).hexdigest()
            if not cache.add(key, 1, 60):
                try: count = cache.incr(key)
                except ValueError: count = 1
                if count > limit: return HttpResponse('Quá nhiều yêu cầu. Vui lòng thử lại sau một phút.', status=429)
        response = self.get_response(request)
        payment_url = urlsplit(settings.VNPAY_URL)
        payment_origin = f'{payment_url.scheme}://{payment_url.netloc}'
        response['Content-Security-Policy'] = f"default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; media-src 'self' blob:; connect-src 'self'; worker-src 'self' blob:; frame-ancestors 'none'; base-uri 'self'; form-action 'self' {payment_origin}"
        response['Permissions-Policy'] = 'camera=(), microphone=(), geolocation=()'
        if request.user.is_authenticated or request.path.startswith('/stream/'):
            response['Cache-Control'] = 'private, no-store'
        return response
