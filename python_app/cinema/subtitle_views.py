"""Subtitle payloads share full-film access checks and never use public media."""
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_GET

from .models import Subtitle
from .views import require_watch


@login_required
@require_GET
def subtitle(request, pk, subtitle_pk):
    track = get_object_or_404(
        Subtitle.objects.select_related('episode__movie'), pk=subtitle_pk, episode_id=pk,
    )
    require_watch(request.user, track.episode)
    response = HttpResponse(track.content, content_type='text/vtt; charset=utf-8')
    response['Cache-Control'] = 'private, no-store'
    response['X-Content-Type-Options'] = 'nosniff'
    return response
