from django import template
from django.templatetags.static import static

register = template.Library()


@register.filter
def cinema_poster(movie):
    """Use the designed demo posters, while honoring real uploaded movie art."""
    demo_slugs = {'big-buck-bunny', 'orbit', 'dusk', 'forest', 'city', 'ocean', 'summer'}
    if movie.slug in demo_slugs:
        return static(f'imagery/posters/{movie.slug}.svg')
    if movie.poster:
        return movie.poster.url
    if movie.backdrop:
        return movie.backdrop.url
    return static(f'imagery/{movie.artwork}.jpg')


@register.filter
def vnd(value):
    """Group whole-VND amounts consistently, including locales with no grouping."""
    try:
        return format(int(value), ',').replace(',', '.')
    except (TypeError, ValueError, OverflowError):
        return value


@register.filter
def first_paragraph(value):
    """Keep quick movie summaries compact; full credits stay on detail pages."""
    return str(value or '').replace('\r\n', '\n').strip().split('\n\n', 1)[0]
