import hashlib
import hmac
import re
from datetime import timedelta
from urllib.parse import urlencode
from zoneinfo import ZoneInfo
from django.conf import settings
from django.db import transaction
from django.core.exceptions import ValidationError
from django.utils import timezone
from .models import Order, User


def signature(params):
    data = urlencode(sorted((k, v) for k, v in params.items() if k.startswith('vnp_') and k not in ('vnp_SecureHash', 'vnp_SecureHashType') and v != ''))
    return hmac.new(settings.VNPAY_HASH_SECRET.encode(), data.encode(), hashlib.sha512).hexdigest()


def checkout_url(order, ip):
    now = timezone.now().astimezone(ZoneInfo('Asia/Ho_Chi_Minh'))
    params = {'vnp_Version': '2.1.0', 'vnp_Command': 'pay', 'vnp_TmnCode': settings.VNPAY_TMN_CODE, 'vnp_Amount': str(order.amount * 100), 'vnp_CurrCode': 'VND', 'vnp_TxnRef': order.pk.hex, 'vnp_OrderInfo': f'Lumiere VIP {order.pk.hex}', 'vnp_OrderType': 'other', 'vnp_Locale': 'vn', 'vnp_ReturnUrl': settings.PUBLIC_ORIGIN + '/payments/return/', 'vnp_IpAddr': ip, 'vnp_CreateDate': now.strftime('%Y%m%d%H%M%S'), 'vnp_ExpireDate': (now + timedelta(minutes=15)).strftime('%Y%m%d%H%M%S')}
    params['vnp_SecureHash'] = signature(params)
    return settings.VNPAY_URL + '?' + urlencode(sorted(params.items()))


def process_ipn(params):
    if not settings.VNPAY_HASH_SECRET or any(len(values) != 1 for _, values in params.lists()):
        return {'RspCode': '97', 'Message': 'Invalid signature'}
    values = params.dict()
    if not re.fullmatch(r'[a-fA-F0-9]{128}', values.get('vnp_SecureHash', '')) or not hmac.compare_digest(signature(values), values.get('vnp_SecureHash', '').lower()) or values.get('vnp_TmnCode') != settings.VNPAY_TMN_CODE:
        return {'RspCode': '97', 'Message': 'Invalid signature'}
    with transaction.atomic():
        try:
            order = Order.objects.select_for_update().get(pk=values.get('vnp_TxnRef'))
        except (Order.DoesNotExist, ValueError, TypeError, ValidationError):
            return {'RspCode': '01', 'Message': 'Order not found'}
        if values.get('vnp_Amount') != str(order.amount * 100):
            return {'RspCode': '04', 'Message': 'Invalid amount'}
        if order.status != 'pending':
            return {'RspCode': '02', 'Message': 'Order already confirmed'}
        successful = values.get('vnp_ResponseCode') == '00' and values.get('vnp_TransactionStatus') == '00'
        if successful and not values.get('vnp_TransactionNo'):
            return {'RspCode': '99', 'Message': 'Missing transaction number'}
        order.status = 'paid' if successful else 'failed'
        order.transaction_no = values.get('vnp_TransactionNo', '')[:100]
        if successful:
            user = User.objects.select_for_update().get(pk=order.user_id)
            now = timezone.now()
            user.vip_until = max(user.vip_until or now, now) + timedelta(days=order.days)
            user.save(update_fields=['vip_until'])
            order.paid_at = now
        order.save()
    return {'RspCode': '00', 'Message': 'Confirm success'}
