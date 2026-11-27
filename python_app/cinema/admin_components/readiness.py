"""Permission-aware content health filtering."""
from django.contrib import admin

from ..content_health import HEALTH_LABELS, health_queryset, permitted_health_checks


class ContentHealthFilter(admin.SimpleListFilter):
    title = 'Việc cần hoàn thiện'
    parameter_name = 'health'

    def lookups(self, request, model_admin):
        return [(key, HEALTH_LABELS[key]) for key in permitted_health_checks(request.user)]

    def queryset(self, request, queryset):
        if not self.value():
            return queryset
        if self.value() not in permitted_health_checks(request.user):
            return queryset.none()
        return health_queryset(queryset, self.value())
