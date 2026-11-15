"""Resolve the optional catalog entry built by Vite."""
import json
import re

from django import template
from django.conf import settings
from django.templatetags.static import static
from django.utils.html import format_html

register = template.Library()


@register.simple_tag
def catalog_frontend(section='results'):
    sources = {'results': 'src/catalog/main.ts', 'home': 'src/home/main.ts'}
    if section not in sources:
        return ''

    bundle = 'bundles/catalog'
    directory = settings.BASE_DIR / 'static' / bundle
    try:
        manifest = json.loads((directory / 'manifest.json').read_text(encoding='utf-8'))
        entry = manifest[sources[section]]['file']
    except (OSError, ValueError, KeyError, TypeError):
        return ''
    if not isinstance(entry, str) or not re.fullmatch(r'assets/[A-Za-z0-9_-]+\.js', entry):
        return ''
    if not (directory / entry).is_file():
        return ''
    return format_html('<script type="module" src="{}"></script>', static(f'{bundle}/{entry}'))
