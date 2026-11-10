"""Studio labels are presentation-only; model metadata stays unchanged."""
from django import template

from cinema.studio import MODEL_LABELS, build_navigation

register = template.Library()


@register.simple_tag(takes_context=True)
def studio_menu(context):
    request = context.get('request')
    user = getattr(request, 'user', context.get('user'))
    return build_navigation(user, getattr(request, 'path', ''))


@register.filter
def studio_model_label(value, form='plural'):
    model = getattr(value, 'model_name', str(value)).lower()
    labels = MODEL_LABELS.get(model)
    if labels:
        return labels[0] if form == 'singular' else labels[1]
    return getattr(value, 'verbose_name_plural', value)


@register.simple_tag(takes_context=True)
def studio_page_title(context):
    request = context.get('request')
    path = getattr(request, 'path', '')
    if path.rstrip('/') == '/admin/login':
        return 'Đăng nhập quản trị'
    if context.get('studio_dashboard') or path.rstrip('/') in ('/admin', '/studio'):
        return 'Tổng quan hệ thống'
    opts = context.get('opts')
    if opts is not None:
        singular = studio_model_label(opts, 'singular')
        if context.get('add'):
            return f'Thêm {singular}'
        if context.get('change'):
            return f'Chỉnh sửa {singular}'
        if context.get('cl') is not None:
            return studio_model_label(opts)
    return context.get('title') or 'Lumière Studio'
