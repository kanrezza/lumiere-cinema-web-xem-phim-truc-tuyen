"""Load Vite entries for Lumière's Vue screens."""
import json
import re

from django import template
from django.conf import settings
from django.templatetags.static import static
from django.utils.html import format_html

register = template.Library()
ENTRIES = {
    'results': 'src/catalog/main.ts', 'home': 'src/home/main.ts',
    'shell': 'src/shell/main.ts', 'public': 'src/public/main.ts',
    'viewing': 'src/viewing/main.ts', 'studio': 'src/studio/main.ts',
}


@register.simple_tag
def frontend_assets(section):
    source = ENTRIES.get(section)
    if not source:
        return ''
    bundle = 'bundles/catalog'
    directory = settings.BASE_DIR / 'static' / bundle
    try:
        manifest = json.loads((directory / 'manifest.json').read_text(encoding='utf-8'))
        entry = manifest[source]['file']
    except (OSError, ValueError, KeyError, TypeError):
        return ''
    if not isinstance(entry, str) or not re.fullmatch(r'assets/[A-Za-z0-9_-]+\.js', entry):
        return ''
    if not (directory / entry).is_file():
        return ''
    return format_html('<script type="module" src="{}"></script>', static(f'{bundle}/{entry}'))
