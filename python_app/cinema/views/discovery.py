"""Genre, country and actor directory endpoints."""

from urllib.parse import urlencode

from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.views.decorators.vary import vary_on_headers

from ..models import Actor
from ..queries import catalog_movies, public_categories, public_country_groups
from ..search import filter_actor_search, normalize_search


def directory_response(request, template_name, context, data):
    if request.headers.get('X-Lumiere-Directory') == 'vue':
        return JsonResponse(data, headers={'Cache-Control': 'private, no-store'})
    return render(request, template_name, {**context, 'directory_data': data})


@vary_on_headers('X-Lumiere-Directory')
def discovery_index(request, kind):
    query = request.GET.get('q', '').strip()[:150]
    if kind == 'countries':
        items = [{'name': group['name'], 'count': group['count'],
                  'href': reverse('catalog') + '?' + urlencode({'country': group['name']})}
                 for group in public_country_groups()]
        title, eyebrow = 'Quốc gia', 'KHÁM PHÁ THEO QUỐC GIA'
        description = 'Tìm những câu chuyện từ các nền điện ảnh có trong thư viện Lumière.'
    else:
        items = [{'name': genre.name, 'count': genre.published_count,
                  'href': reverse('catalog') + '?' + urlencode({'category': genre.slug})}
                 for genre in public_categories()]
        title, eyebrow = 'Thể loại', 'KHÁM PHÁ THEO THỂ LOẠI'
        description = 'Chọn thể loại phù hợp với tâm trạng và tìm bộ phim tiếp theo của bạn.'
    total_count = len(items)
    search_term = normalize_search(query)
    if search_term:
        items = [item for item in items if search_term in normalize_search(item['name'])]
    context = {
        'title': title, 'eyebrow': eyebrow, 'description': description,
        'discovery_kind': kind, 'items': items, 'q': query, 'total_count': total_count,
    }
    return directory_response(request, 'cinema/discovery_index.html', context, {
        'kind': kind,
        'title': title,
        'eyebrow': eyebrow,
        'description': description,
        'items': items,
        'query': query,
        'count': len(items),
        'url': reverse('countries' if kind == 'countries' else 'categories'),
        'catalogUrl': reverse('catalog'),
    })


def countries(request):
    return discovery_index(request, 'countries')


def categories(request):
    return discovery_index(request, 'categories')


@vary_on_headers('X-Lumiere-Directory')
def actors(request):
    query = request.GET.get('q', '').strip()[:150]
    people = Actor.objects.annotate(
        film_count=Count('movie', filter=Q(movie__published=True), distinct=True),
    ).filter(film_count__gt=0).order_by('name', 'pk')
    if query: people = filter_actor_search(people, query)
    page = Paginator(people, 24).get_page(request.GET.get('page'))
    context = {'actors': page, 'q': query, 'total_count': page.paginator.count}
    return directory_response(request, 'cinema/actors.html', context, {
        'kind': 'actors',
        'title': 'Diễn viên',
        'eyebrow': 'KHÁM PHÁ LUMIÈRE',
        'description': 'Tìm diễn viên và khám phá những bộ phim họ tham gia.',
        'items': [
            {'name': actor.name, 'count': actor.film_count, 'href': reverse('actor', args=[actor.pk])}
            for actor in page
        ],
        'query': query,
        'count': page.paginator.count,
        'url': reverse('actors'),
        'catalogUrl': reverse('catalog'),
        'addActorUrl': reverse('admin:cinema_actor_add') if request.user.has_perm('cinema.add_actor') else None,
        'pagination': {
            'page': page.number,
            'pages': page.paginator.num_pages,
            'previous': '?' + urlencode({'q': query, 'page': page.previous_page_number()}) if page.has_previous() else None,
            'next': '?' + urlencode({'q': query, 'page': page.next_page_number()}) if page.has_next() else None,
        },
    })


def actor_detail(request, pk):
    actor = get_object_or_404(Actor.objects.annotate(
        film_count=Count('movie', filter=Q(movie__published=True), distinct=True),
    ).filter(film_count__gt=0), pk=pk)
    return render(request, 'cinema/actor.html', {'actor': actor, 'movies': catalog_movies(request.user).filter(actors=actor)})
