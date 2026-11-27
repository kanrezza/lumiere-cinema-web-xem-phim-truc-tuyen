"""Account, VIP plan and payment administration."""
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.core.exceptions import PermissionDenied

from ..models import Order, User
from ..privacy_auth import LockedAdminPasswordChangeForm
from .common import LocalizedAdminMixin, format_vnd


class CustomUserAdmin(LocalizedAdminMixin, UserAdmin):
    model_label = 'Tài khoản'
    model_label_plural = 'Tài khoản'
    change_password_form = LockedAdminPasswordChangeForm
    field_labels = {'bio': 'Giới thiệu', 'vip_until': 'VIP có hiệu lực đến'}
    fieldsets = UserAdmin.fieldsets + (('Quyền lợi Lumière', {'fields': ('bio', 'vip_until')}),)
    add_fieldsets = UserAdmin.add_fieldsets + (('Liên hệ', {'fields': ('email',)}),)

    def has_change_permission(self, request, obj=None):
        return (obj is None or obj.erased_at is None) and super().has_change_permission(request, obj)

    def save_model(self, request, obj, form, change):
        if change and User.objects.select_for_update().get(pk=obj.pk).erased_at:
            raise PermissionDenied
        super().save_model(request, obj, form, change)


class OrderAdmin(LocalizedAdminMixin, admin.ModelAdmin):
    model_label = 'Giao dịch'
    model_label_plural = 'Giao dịch'
    list_display = ('order_reference', 'customer', 'plan_name', 'total_amount', 'payment_status', 'created_time')
    list_select_related = ('user', 'plan')
    list_filter = ('status',)
    search_fields = ('id', 'user__username', 'user__email', 'transaction_no')
    readonly_fields = tuple(f.name for f in Order._meta.fields) + ('full_reference', 'customer', 'plan_name', 'total_amount', 'term_days', 'payment_status', 'transaction_reference', 'created_time', 'paid_time')
    fieldsets = (
        ('Thông tin giao dịch', {'fields': ('full_reference', 'customer', 'plan_name', 'total_amount', 'term_days', 'payment_status')}),
        ('Đối soát thanh toán', {'fields': ('transaction_reference', 'created_time', 'paid_time')}),
        ('Kỳ sử dụng VIP', {'fields': ('period_start', 'period_end')}),
    )
    field_labels = {'user': 'Khách hàng', 'plan': 'Gói thành viên', 'amount': 'Số tiền', 'days': 'Số ngày sử dụng', 'status': 'Trạng thái', 'transaction_no': 'Mã giao dịch VNPay', 'created_at': 'Ngày tạo', 'paid_at': 'Ngày thanh toán'}

    @admin.display(description='Mã đơn', ordering='id')
    def order_reference(self, obj): return str(obj.pk)[:8].upper()

    @admin.display(description='Mã đơn đầy đủ')
    def full_reference(self, obj): return str(obj.pk)

    @admin.display(description='Khách hàng', ordering='user__username')
    def customer(self, obj): return obj.user.username

    @admin.display(description='Gói thành viên', ordering='plan__name')
    def plan_name(self, obj): return obj.membership_name

    @admin.display(description='Số tiền', ordering='amount')
    def total_amount(self, obj): return format_vnd(obj.amount)

    @admin.display(description='Trạng thái', ordering='status')
    def payment_status(self, obj): return obj.get_status_display()

    @admin.display(description='Ngày tạo', ordering='created_at')
    def created_time(self, obj): return obj.created_at

    @admin.display(description='Số ngày sử dụng')
    def term_days(self, obj): return obj.days

    @admin.display(description='Mã giao dịch VNPay')
    def transaction_reference(self, obj): return obj.transaction_no or 'Chưa có'

    @admin.display(description='Ngày thanh toán')
    def paid_time(self, obj): return obj.paid_at

    def has_add_permission(self, request): return False
    def has_delete_permission(self, request, obj=None): return False


class PlanAdmin(LocalizedAdminMixin, admin.ModelAdmin):
    model_label = 'Gói VIP'
    model_label_plural = 'Gói VIP'
    list_display = ('plan_name', 'price_display', 'duration_days', 'is_available')
    list_filter = ('active',)
    search_fields = ('name',)
    field_labels = {'name': 'Tên gói', 'price': 'Giá (VNĐ)', 'days': 'Số ngày sử dụng', 'active': 'Đang mở bán'}

    @admin.display(description='Gói VIP', ordering='name')
    def plan_name(self, obj): return obj.name

    @admin.display(description='Giá', ordering='price')
    def price_display(self, obj): return format_vnd(obj.price)

    @admin.display(description='Thời hạn (ngày)', ordering='days')
    def duration_days(self, obj): return obj.days

    @admin.display(description='Đang mở bán', boolean=True, ordering='active')
    def is_available(self, obj): return obj.active
