"""Published catalog data for the shared navigation dropdown."""
from urllib.parse import urlencode

from django import template
from django.db.models import Count, Q
from django.urls import reverse

from cinema.models import Category

register = template.Library()


def _catalog_filters(context, changing):
    catalog_url = reverse('catalog')
    request = context.get('request')
    query = {}
    if request is not None and request.path == catalog_url:
        limits = {'q': 150, 'category': 100, 'country': 100, 'actor': 64,
                  'kind': 20, 'sort': 20, 'access': 20, 'year': 32}
        for key, limit in limits.items():
            if key == changing:
                continue
            value = request.GET.get(key, '').strip()[:limit]
            if value:
                query[key] = value
    return catalog_url, query


@register.simple_tag(takes_context=True)
def genre_menu_data(context):
    """Select a genre without losing the user's current catalog filters."""
    catalog_url, query = _catalog_filters(context, 'category')
    genres = Category.objects.annotate(
        published_count=Count('movie', filter=Q(movie__published=True), distinct=True),
    ).filter(published_count__gt=0).order_by('name', 'pk')
    return [
        {
            'name': genre.name,
            'slug': genre.slug,
            'count': genre.published_count,
            'href': catalog_url + '?' + urlencode({**query, 'category': genre.slug}),
        }
        for genre in genres
    ]


@register.simple_tag(takes_context=True)
def country_menu_data(context):
    """Use the same public country grouping as discovery and preserve filters."""
    from cinema.views import public_country_groups

    catalog_url, query = _catalog_filters(context, 'country')
    request = context.get('request')
    selected = request.GET.get('country', '').strip().casefold() if request is not None else ''
    return [
        {
            'name': country['name'],
            'count': country['count'],
            'href': catalog_url + '?' + urlencode({**query, 'country': country['name']}),
            'selected': country['name'].casefold() == selected,
        }
        for country in public_country_groups()
    ]
