"""Welcome page and searchable movie catalog endpoints."""

import re
from urllib.parse import urlencode

from django.core.paginator import Paginator
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.views.decorators.vary import vary_on_headers

from ..models import Actor, Category, Movie, Plan
from ..queries import catalog_movies, continue_cards, public_categories, public_country_groups
from ..search import filter_movie_search


def catalog_content_links(request):
    limits = {'q': 150, 'category': 100, 'country': 100, 'actor': 64, 'year': 32,
              'kind': 20, 'sort': 20, 'access': 20, 'availability': 24, 'release': 24, 'trailer': 12}
    current = {key: request.GET.get(key, '').strip()[:limit] for key, limit in limits.items()
               if request.GET.get(key, '').strip()}
    def link(label, key=None, value=None):
        query = dict(current)
        if key is None:
            active = not any(query.get(name) for name in ('availability', 'release', 'trailer'))
            for name in ('availability', 'release', 'trailer'):
                query.pop(name, None)
        else:
            active = query.get(key) == value
            if active:
                query.pop(key, None)
            else:
                query[key] = value
        return {'label': label, 'active': active,
                'href': reverse('catalog') + ('?' + urlencode(query) if query else '?sort=newest')}
    return [link('Tất cả'), link('Đã có phim', 'availability', 'ready'),
            link('Chưa có bản xem', 'availability', 'upcoming'),
            link('Phim chiếu rạp', 'release', 'cinema'), link('Có trailer', 'trailer', '1')]


def landing(request):
    """Public introduction stays distinct from the signed-in movie browser."""
    # Existing bookmarked filter links remain useful after moving discovery.
    if any(request.GET.get(key) for key in ('q', 'category', 'country', 'actor', 'year', 'kind', 'sort', 'page', 'access', 'availability', 'release', 'trailer')):
        return redirect(reverse('catalog') + '?' + request.GET.urlencode())
    movies = catalog_movies(request.user)
    return render(request, 'cinema/landing.html', {
        'landing_movies': list(movies[:7]),
        'featured': movies.filter(is_vip=False, ready_episode_id__isnull=False).first() or movies.filter(ready_episode_id__isnull=False).first() or movies.first(),
        'plans': Plan.objects.filter(active=True).order_by('price', 'pk'),
        'free_movie_count': movies.filter(is_vip=False).count(),
        'vip_movie_count': movies.filter(is_vip=True).count(),
        'landing_categories': Category.objects.filter(movie__published=True).distinct().order_by('name'),
    })


def catalog_results(request, context):
    page = context['page']
    genre = context['selected_category']
    actor = context['selected_actor']
    values = {
        'q': context['q'],
        'category': context['category'],
        'country': context['selected_country'],
        'year': context['selected_year'],
        'kind': request.GET.get('kind', ''),
        'sort': request.GET.get('sort', ''),
        'access': request.GET.get('access', ''),
        'actor': context['actor_filter'],
        'availability': context['availability'],
        'release': context['release'],
        'trailer': context['trailer_filter'],
    }
    active_filters = [
        (label, value) for label, value in (
            ('Thể loại', genre.name if genre else ''),
            ('Quốc gia', values['country']),
            ('Diễn viên', actor.name if actor else ''),
            ('Năm', values['year']),
        ) if value
    ]
    titles = [
        (values['q'], f'Kết quả cho “{values["q"]}”'),
        (actor, f'Phim có {actor.name}' if actor else ''),
        (values['country'], f'Phim {values["country"]}'),
        (genre, f'Phim {genre.name}' if genre else ''),
        (values['year'], f'Phim năm {values["year"]}'),
        (values['kind'] == 'movie', 'Phim lẻ'),
        (values['kind'] == 'series', 'Phim bộ'),
        (values['access'] == 'vip', 'Phim dành cho thành viên VIP'),
        (values['sort'] == 'rating', 'Phim được đánh giá cao'),
    ]
    pagination_query = {name: value for name, value in values.items() if value}

    def page_link(number):
        return '?' + urlencode({**pagination_query, 'page': number})

    return {
        'title': next((title for matches, title in titles if matches), 'Khám phá phim'),
        'count': page.paginator.count,
        'contentLinks': context['content_links'],
        'values': values,
        'categories': [{'value': item.slug, 'label': item.name} for item in context['categories']],
        'countries': [{'value': item['name'], 'label': item['name']} for item in context['countries']],
        'years': context['years'],
        'activeFilters': [f'{label}: {value}' for label, value in active_filters],
        'pagination': {
            'page': page.number,
            'pages': page.paginator.num_pages,
            'previous': page_link(page.previous_page_number()) if page.has_previous() else None,
            'next': page_link(page.next_page_number()) if page.has_next() else None,
        },
    }


@vary_on_headers('X-Lumiere-Catalog')
def catalog(request):
    movies = catalog_movies(request.user)
    categories = list(public_categories())
    country_groups = public_country_groups()
    country_options = [{'name': group['name'], 'count': group['count']} for group in country_groups]
    q = request.GET.get('q', '').strip()[:150]
    selected_year = request.GET.get('year', '').strip()[:32]
    years = list(Movie.objects.filter(published=True, year__range=(1, 9999)).order_by('-year').values_list('year', flat=True).distinct())
    category = request.GET.get('category', '')
    kind = request.GET.get('kind', '')
    country = request.GET.get('country', '').strip()[:100]
    selected_country_group = next((group for group in country_groups if group['name'].casefold() == country.casefold()), None)
    selected_country = selected_country_group['name'] if selected_country_group else country
    actor_filter = request.GET.get('actor', '').strip()[:64]
    selected_actor = None
    actor_id = None
    if re.fullmatch(r'[1-9][0-9]{0,18}', actor_filter):
        actor_id = int(actor_filter)
        if actor_id <= 9223372036854775807:
            selected_actor = Actor.objects.filter(pk=actor_id, movie__published=True).distinct().first()
        else:
            actor_id = None
    selected_category = next((genre for genre in categories if genre.slug == category), None)
    availability = request.GET.get('availability', '').strip()[:24]
    release = request.GET.get('release', '').strip()[:24]
    trailer_filter = request.GET.get('trailer', '').strip()[:12]
    is_browsing = any(request.GET.get(key) for key in ('q', 'category', 'country', 'actor', 'year', 'kind', 'sort', 'page', 'access', 'availability', 'release', 'trailer'))
    filtered = movies
    if q: filtered = filter_movie_search(filtered, q)
    if selected_year:
        filtered = filtered.filter(year=int(selected_year)) if re.fullmatch(r'[1-9][0-9]{0,3}', selected_year) else filtered.none()
    if category: filtered = filtered.filter(categories__slug=category)
    if country:
        filtered = filtered.filter(country__in=selected_country_group['values']) if selected_country_group else filtered.none()
    if actor_filter:
        filtered = filtered.filter(actors__pk=actor_id) if actor_id else filtered.none()
    if kind in ('movie', 'series'): filtered = filtered.filter(kind=kind)
    if request.GET.get('access') == 'vip': filtered = filtered.filter(is_vip=True)
    if availability:
        filtered = filtered.filter(ready_episode_id__isnull=availability == 'upcoming') if availability in ('ready', 'upcoming') else filtered.none()
    if release:
        filtered = filtered.filter(is_cinema_release=True) if release == 'cinema' else filtered.none()
    if trailer_filter:
        filtered = filtered.exclude(trailer_url='', trailer_file='') if trailer_filter == '1' else filtered.none()
    if request.GET.get('sort') == 'rating': filtered = filtered.order_by('-score', '-created_at', '-pk')

    shelves = []
    continue_watching = []
    featured_movies = []
    if not is_browsing:
        featured_movies = list(movies.filter(ready_episode_id__isnull=False)[:3])
        shelves.append({'title': 'Mới trên Lumière', 'subtitle': 'Những câu chuyện mới trong thư viện.', 'movies': list(movies[:12]), 'href': reverse('catalog') + '?sort=newest'})
        vip_movies = list(movies.filter(is_vip=True)[:12])
        if vip_movies:
            preparing = not any(film.ready_episode_id for film in vip_movies)
            subtitle = 'Những bộ phim VIP đang được chuẩn bị.' if preparing else 'Mở thêm những bộ phim dành riêng cho bạn.'
            shelves.append({'title': 'Dành cho thành viên VIP', 'subtitle': subtitle, 'preparing': preparing, 'movies': vip_movies, 'href': reverse('catalog') + '?access=vip'})
        for genre in categories:
            if genre.published_count < 2:
                continue
            selections = list(movies.filter(categories=genre)[:12])
            if not selections:
                continue
            shelves.append({'title': genre.name, 'subtitle': '', 'movies': selections, 'href': reverse('catalog') + '?' + urlencode({'category': genre.slug})})
            if len(shelves) >= 4:
                break
        continue_watching = continue_cards(request.user, 12)
    context = {
        'page': Paginator(filtered.distinct(), 12).get_page(request.GET.get('page')),
        'featured': featured_movies[0] if featured_movies else None,
        'categories': categories, 'q': q, 'category': category,
        'is_browsing': is_browsing, 'shelves': shelves, 'continue_watching': continue_watching,
        'featured_movies': featured_movies,
        'countries': country_options, 'selected_country': selected_country,
        'years': years, 'selected_year': selected_year,
        'content_links': catalog_content_links(request), 'availability': availability,
        'release': release, 'trailer_filter': trailer_filter,
        'selected_category': selected_category, 'selected_actor': selected_actor, 'actor_filter': actor_filter,
    }
    if is_browsing:
        results = catalog_results(request, context)
        if request.headers.get('X-Lumiere-Catalog') == 'vue':
            results['gridHtml'] = render_to_string('cinema/catalog_grid.html', context, request=request)
            return JsonResponse(results, headers={'Cache-Control': 'private, no-store'})
        context['catalog_results'] = results
    return render(request, 'cinema/catalog.html', context)
