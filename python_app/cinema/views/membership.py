"""VIP plans and retry-safe VNPay checkout endpoints."""

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core import signing
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from ..models import Movie, Order, Plan, User
from ..memberships import membership_timeline, renewal_previews
from ..payments import PAYMENT_WINDOW, checkout_key_from_token, checkout_url, issue_checkout_token, process_ipn


def plans(request):
    active_member = bool(request.user.is_authenticated and request.user.is_vip)
    renewing = active_member and request.GET.get('renew') == '1'
    member_dashboard = active_member and not renewing
    watch_together_url = reverse('rooms')
    payment_ready = bool(settings.VNPAY_TMN_CODE and settings.VNPAY_HASH_SECRET)
    checkout_token = None
    if payment_ready and request.user.is_authenticated and request.user.is_active and not member_dashboard:
        checkout_token = issue_checkout_token(request.user.pk)
    return render(request, 'cinema/plans.html', {
        'plans': renewal_previews(request.user, list(Plan.objects.filter(active=True).order_by('price'))),
        'membership': membership_timeline(request.user),
        'payment_ready': payment_ready,
        'checkout_token': checkout_token,
        'sandbox': 'sandbox' in settings.VNPAY_URL,
        'showcase': Movie.objects.filter(published=True)[:6],
        'member_dashboard': member_dashboard, 'renewing': renewing,
        'watch_together_url': watch_together_url,
    })


@login_required
@require_POST
def checkout(request, pk=None):
    if pk is None:
        try: pk = int(request.POST.get('plan', ''))
        except (ValueError, TypeError): raise Http404('Gói thành viên không hợp lệ.')
    if not settings.VNPAY_TMN_CODE or not settings.VNPAY_HASH_SECRET:
        get_object_or_404(Plan, pk=pk, active=True)
        messages.error(request, 'VNPay chưa được cấu hình. Chưa tạo giao dịch hoặc thu tiền.')
        return redirect('plans')

    plans_url = reverse('plans')
    if request.user.is_vip:
        plans_url += '?renew=1'
    try:
        checkout_key = checkout_key_from_token(request.user.pk, request.POST.get('checkout_token', ''))
    except signing.BadSignature:
        messages.error(request, 'Phiên chọn gói đã hết hạn hoặc không hợp lệ. Vui lòng kiểm tra lại gói trước khi tiếp tục.')
        return redirect(plans_url)

    with transaction.atomic():
        buyer = User.objects.select_for_update().filter(pk=request.user.pk, is_active=True).first()
        if buyer is None:
            raise PermissionDenied('Tài khoản không còn hoạt động.')
        order = Order.objects.filter(user=buyer, checkout_key=checkout_key).first()
        if order is None:
            plan = get_object_or_404(Plan, pk=pk, active=True)
            order = Order.objects.create(
                user=buyer, plan=plan, amount=plan.price, days=plan.days, checkout_key=checkout_key,
                plan_name_snapshot=plan.name,
            )
        elif order.plan_id != pk:
            messages.error(request, 'Lần thanh toán này đã gắn với một gói khác. Vui lòng chọn lại gói.')
            return redirect(plans_url)

    if order.status == 'paid':
        return redirect(reverse('profile') + '#billing')
    if order.status != 'pending' or timezone.now() >= order.created_at + PAYMENT_WINDOW:
        messages.info(request, 'Lần thanh toán này đã kết thúc. Vui lòng chọn lại gói nếu bạn muốn thanh toán tiếp.')
        return redirect(plans_url)
    return redirect(checkout_url(order, request.META.get('REMOTE_ADDR', '127.0.0.1')))


@require_GET
def ipn(request): return JsonResponse(process_ipn(request.GET))


@login_required
def payment_return(request):
    # Browser redirects never grant VIP. Only signed server IPN mutates an order.
    messages.info(request, 'Đã trở về từ VNPay. Trạng thái đơn hàng sẽ cập nhật sau khi nhận xác nhận từ cổng thanh toán.')
    return redirect('profile')
