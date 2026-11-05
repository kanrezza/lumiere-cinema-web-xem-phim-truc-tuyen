"""Stored, database-side Vietnamese search without SQLite collation assumptions.

Names and titles have ordinary indexes for exact/prefix queries. Substring search,
especially descriptions, still needs a database scan; this is not a full-text
index. Normalized values are maintained by model.save(), including update_fields.
Raw SQL, QuerySet.update(), bulk_create() and bulk_update() bypass save(): callers
changing search sources through those APIs must also supply normalized values.
"""

import unicodedata

from django.db.models import Q


def normalize_search(value):
    """Casefold, remove Vietnamese diacritics and normalize whitespace."""
    value = unicodedata.normalize('NFKD', str(value or '')).casefold().replace('đ', 'd')
    return ' '.join(''.join(character for character in value if not unicodedata.combining(character)).split())


def filter_movie_search(queryset, query):
    """Keep the caller's publication/access scope and search related performers."""
    query = normalize_search(query)
    if not query:
        return queryset
    return queryset.filter(
        Q(search_title__contains=query)
        | Q(search_description__contains=query)
        | Q(actors__search_name__contains=query)
    ).distinct()


def filter_actor_search(queryset, query):
    query = normalize_search(query)
    return queryset.filter(search_name__contains=query) if query else queryset
