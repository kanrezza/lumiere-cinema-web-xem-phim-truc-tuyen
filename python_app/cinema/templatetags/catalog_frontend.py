"""Resolve the optional catalog entry built by Vite."""
import json
import re

from django import template
from django.conf import settings
from django.templatetags.static import static
from django.utils.html import format_html

register = template.Library()


@register.simple_tag
def catalog_frontend():
    bundle = 'bundles/catalog'
    manifest = settings.BASE_DIR / 'static' / bundle / 'manifest.json'
    try:
        entry = json.loads(manifest.read_text(encoding='utf-8'))['src/catalog/main.ts']['file']
    except (OSError, ValueError, KeyError, TypeError):
        return ''
    if not isinstance(entry, str) or not re.fullmatch(r'assets/main-[A-Za-z0-9_-]+\.js', entry):
        return ''
    return format_html('<script type="module" src="{}"></script>', static(f'{bundle}/{entry}'))
