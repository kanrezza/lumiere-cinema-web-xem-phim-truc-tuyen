import hashlib
import hmac
import re
from datetime import timedelta
from urllib.parse import urlencode
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo
from django.conf import settings
from django.core import signing
from django.db import transaction
from django.core.exceptions import ValidationError
from django.utils import timezone
from .models import Order, User


CHECKOUT_TOKEN_SALT = 'cinema.vip.checkout'
CHECKOUT_TOKEN_MAX_AGE = timedelta(hours=1)
PAYMENT_WINDOW = timedelta(minutes=15)


def issue_checkout_token(user_id):
    return signing.dumps([user_id, uuid4().hex], salt=CHECKOUT_TOKEN_SALT)


def checkout_key_from_token(user_id, token):
    signed_user, key = signing.loads(token, salt=CHECKOUT_TOKEN_SALT, max_age=CHECKOUT_TOKEN_MAX_AGE)
    if signed_user != user_id:
        raise signing.BadSignature('Checkout token belongs to a different user.')
    return UUID(key)


def signature(params):
    data = urlencode(sorted((k, v) for k, v in params.items() if k.startswith('vnp_') and k not in ('vnp_SecureHash', 'vnp_SecureHashType') and v != ''))
    return hmac.new(settings.VNPAY_HASH_SECRET.encode(), data.encode(), hashlib.sha512).hexdigest()


def checkout_url(order, ip):
    created_at = order.created_at.astimezone(ZoneInfo('Asia/Ho_Chi_Minh'))
    params = {'vnp_Version': '2.1.0', 'vnp_Command': 'pay', 'vnp_TmnCode': settings.VNPAY_TMN_CODE, 'vnp_Amount': str(order.amount * 100), 'vnp_CurrCode': 'VND', 'vnp_TxnRef': order.pk.hex, 'vnp_OrderInfo': f'Lumiere VIP {order.pk.hex}', 'vnp_OrderType': 'other', 'vnp_Locale': 'vn', 'vnp_ReturnUrl': settings.PUBLIC_ORIGIN + '/payments/return/', 'vnp_IpAddr': ip, 'vnp_CreateDate': created_at.strftime('%Y%m%d%H%M%S'), 'vnp_ExpireDate': (created_at + PAYMENT_WINDOW).strftime('%Y%m%d%H%M%S')}
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
            if not user.erased_at:
                order.period_start = max(user.vip_until or now, now)
                order.period_end = order.period_start + timedelta(days=order.days)
                user.vip_until = order.period_end
                user.save(update_fields=['vip_until'])
            if not order.plan_name_snapshot:
                order.plan_name_snapshot = order.plan.name
            order.paid_at = now
        order.save()
    return {'RspCode': '00', 'Message': 'Confirm success'}
