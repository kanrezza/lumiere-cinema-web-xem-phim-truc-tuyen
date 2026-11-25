"""Staff-only dashboard entry point."""

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import render


@login_required
def studio(request):
    if not request.user.is_staff: raise PermissionDenied
    from django.contrib import admin
    from ..studio import build_dashboard_context
    context = {**admin.site.each_context(request), **build_dashboard_context(request.user), 'title': 'Tổng quan hệ thống'}
    return render(request, 'cinema/studio.html', context)
