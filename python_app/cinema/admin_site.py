"""Lumière's management workspace, using Django's existing permission checks."""
import re
from datetime import timedelta

from django.conf import settings
from django.contrib.admin import AdminSite
from django.contrib.admin.apps import AdminConfig
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.http import QueryDict
from django.template.response import TemplateResponse
from django.urls import path
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.http import require_safe


WAF_SOURCE_CODE = re.compile(r'[0-9a-f]{16}')


class LumiereAdminSite(AdminSite):
    site_header = 'Lumière Studio'
    site_title = 'Lumière Studio'
    index_title = 'Tổng quan hệ thống'
    site_url = '/browse/'

    def get_urls(self):
        from .privacy_views import review_action

        return [
            path('security/', self.admin_view(self.waf), name='waf'),
            path('privacy/', self.admin_view(self.privacy_queue), name='privacy_requests'),
            path('privacy/<uuid:erasure_id>/', self.admin_view(review_action), name='privacy_review'),
        ] + super().get_urls()

    def privacy_queue(self, request):
        from .privacy_views import review_queue

        return review_queue(request, self)

    @method_decorator(require_safe)
    def waf(self, request):
        from .models import SecurityEvent
        from .studio import can_view_waf
        from .waf import BASELINE_HOURS, HIGH_RISK_SCORE, MIN_BASELINE_SAMPLES, model_status
        from .waf_behavior import BEHAVIOR_WINDOW_SECONDS, COOLDOWN_SECONDS, mitigation_enabled

        if not can_view_waf(request.user):
            raise PermissionDenied

        events = SecurityEvent.objects.order_by('-created_at', '-pk')
        recent = events.filter(created_at__gte=timezone.now() - timedelta(hours=24))
        totals = recent.aggregate(
            observed=Count('pk', filter=Q(action=SecurityEvent.Action.OBSERVED)),
            blocked=Count('pk', filter=Q(action=SecurityEvent.Action.BLOCKED)),
            high_risk=Count('pk', filter=Q(risk_score__gte=HIGH_RISK_SCORE, action=SecurityEvent.Action.OBSERVED)),
            behavior_incidents=Count('pk', filter=Q(
                reason=SecurityEvent.Reason.BEHAVIOR_ANOMALY, action=SecurityEvent.Action.OBSERVED,
            )),
            behavior_rejections=Count('pk', filter=Q(
                reason=SecurityEvent.Reason.BEHAVIOR_COOLDOWN, action=SecurityEvent.Action.BLOCKED,
            )),
        )
        action_choices = SecurityEvent.Action.choices
        reason_choices = SecurityEvent.Reason.choices
        filters = QueryDict(mutable=True)
        for parameter, choices in (('action', action_choices), ('reason', reason_choices)):
            value = request.GET.get(parameter)
            if value in dict(choices):
                filters[parameter] = value
        source = request.GET.get('source', '')
        if WAF_SOURCE_CODE.fullmatch(source):
            filters['source'] = source

        events = events.filter(**filters.dict())
        risk_filter = request.GET.get('risk')
        risk_conditions = {
            'high': Q(risk_score__gte=HIGH_RISK_SCORE),
            'scored': Q(risk_score__lt=HIGH_RISK_SCORE),
            'unscored': Q(risk_score__isnull=True),
        }
        if risk_filter in risk_conditions:
            filters['risk'] = risk_filter
            events = events.filter(risk_conditions[risk_filter])

        page = Paginator(events, 25).get_page(request.GET.get('page'))
        source_codes = {event.source for event in page if WAF_SOURCE_CODE.fullmatch(event.source)}
        request.current_app = self.name
        return TemplateResponse(request, 'studio/waf.html', {
            **self.each_context(request),
            'title': 'Bảo mật WAF',
            'waf_mode': settings.WAF_MODE,
            'waf_totals': totals,
            'waf_page': page,
            'waf_filters': filters,
            'waf_actions': action_choices,
            'waf_reasons': reason_choices,
            'waf_model_status': model_status() if settings.WAF_MODE != 'off' else None,
            'waf_baseline_hours': BASELINE_HOURS,
            'waf_min_samples': MIN_BASELINE_SAMPLES,
            'waf_high_risk_score': HIGH_RISK_SCORE,
            'waf_source_codes': source_codes,
            'waf_behavior_mitigation': mitigation_enabled(),
            'waf_behavior_window_minutes': BEHAVIOR_WINDOW_SECONDS // 60,
            'waf_cooldown_seconds': COOLDOWN_SECONDS,
        })

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
