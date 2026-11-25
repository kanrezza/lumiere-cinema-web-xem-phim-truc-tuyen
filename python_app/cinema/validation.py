"""Small input parsers shared by room endpoints."""

MAX_DATABASE_ID = (1 << 63) - 1


def positive_id(value):
    """Return a positive signed-64-bit identifier, or None for invalid input."""
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if 0 < parsed <= MAX_DATABASE_ID else None
