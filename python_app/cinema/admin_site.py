"""Lumière's management workspace, using Django's existing permission checks."""
from django.contrib.admin import AdminSite
from django.contrib.admin.apps import AdminConfig


class LumiereAdminSite(AdminSite):
    site_header = 'Lumière Studio'
    site_title = 'Lumière Studio'
    index_title = 'Tổng quan hệ thống'
    site_url = '/browse/'

    def get_app_list(self, request, app_label=None):
        from .studio import MODEL_LABELS
        apps = super().get_app_list(request, app_label)
        for app in apps:
            if app['app_label'] == 'cinema':
                app['name'] = 'Nội dung Lumière'
            for model in app['models']:
                labels = MODEL_LABELS.get(model['object_name'].lower())
                if labels:
                    model['name'] = labels[1]
        return apps

    def index(self, request, extra_context=None):
        from .studio import build_dashboard_context
        context = build_dashboard_context(request.user)
        context.update(extra_context or {})
        return super().index(request, extra_context=context)


class LumiereAdminConfig(AdminConfig):
    default_site = 'cinema.admin_site.LumiereAdminSite'
