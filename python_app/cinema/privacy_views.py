from django import forms
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.shortcuts import redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.debug import sensitive_post_parameters
from django.views.decorators.http import require_http_methods, require_safe

from . import privacy
from .models import ErasureRequest


class ErasureForm(forms.Form):
    password = forms.CharField(
        label='Mật khẩu hiện tại', strip=False, max_length=4096,
        widget=forms.PasswordInput(attrs={'autocomplete': 'current-password'}),
    )
    confirmed = forms.BooleanField(
        label='Tôi yêu cầu đóng tài khoản và xử lý dữ liệu theo chính sách quyền riêng tư.',
    )


@require_safe
def policy(request):
    return render(request, 'cinema/privacy_policy.html', {
        'policy_version': privacy.NOTICE_VERSION,
        'contact_email': settings.PRIVACY_CONTACT_EMAIL,
    })


@login_required
@never_cache
@sensitive_post_parameters('password')
@require_http_methods(['GET', 'HEAD', 'POST'])
def account_privacy(request):
    if request.user.is_staff or request.user.is_superuser or request.user.erased_at:
        raise PermissionDenied
    form = ErasureForm()
    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'cancel':
            privacy.cancel_erasure(request.user.pk)
            messages.success(request, 'Đã hủy yêu cầu đang chờ.')
            return redirect('account_privacy')
        if action != 'request':
            raise PermissionDenied
        form = ErasureForm(request.POST)
        if form.is_valid():
            try:
                privacy.request_erasure(request.user.pk, form.cleaned_data['password'])
            except ValidationError as error:
                form.add_error('password', error)
            else:
                messages.success(request, 'Đã ghi nhận yêu cầu xử lý dữ liệu.')
                return redirect('account_privacy')
    history = request.user.erasure_requests.all()
    return render(request, 'cinema/account_privacy.html', {
        'form': form,
        'pending': history.filter(status=ErasureRequest.Status.PENDING).first(),
        'history': history[:10],
    })


def _can_review(user):
    return user.is_active and user.is_staff and user.is_superuser


@require_safe
def review_queue(request, admin_site):
    from django.core.paginator import Paginator

    if not _can_review(request.user):
        raise PermissionDenied
    status = request.GET.get('status', ErasureRequest.Status.PENDING)
    requests = ErasureRequest.objects.select_related('user', 'reviewed_by')
    if status in ErasureRequest.Status.values:
        requests = requests.filter(status=status)
    else:
        status = ''
    request.current_app = admin_site.name
    return render(request, 'studio/privacy_requests.html', {
        **admin_site.each_context(request),
        'title': 'Yêu cầu quyền riêng tư',
        'entries': Paginator(requests, 25).get_page(request.GET.get('page')),
        'status': status,
        'status_choices': ErasureRequest.Status.choices,
    })


def review_action(request, erasure_id):
    from django.shortcuts import get_object_or_404

    if not _can_review(request.user) or request.method != 'POST':
        raise PermissionDenied
    entry = get_object_or_404(ErasureRequest, pk=erasure_id)
    action = request.POST.get('action')
    if action == 'complete' and request.POST.get('confirmed') == 'yes':
        try:
            privacy.complete_erasure(entry.pk, request.user)
        except ValidationError as error:
            messages.error(request, error.messages[0])
        else:
            messages.success(request, 'Đã xử lý hồ sơ tài khoản.')
    elif action == 'retry_avatar' and entry.status == ErasureRequest.Status.COMPLETED:
        try:
            privacy.cleanup_avatar(entry.pk)
        except OSError:
            messages.error(request, 'Kho ảnh chưa phản hồi. Thử lại sau khi kiểm tra kho tệp.')
        else:
            messages.success(request, 'Đã kiểm tra lại ảnh đại diện.')
    else:
        raise PermissionDenied
    return redirect('admin:privacy_requests')
