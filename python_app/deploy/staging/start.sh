#!/bin/sh
set -eu

python manage.py migrate --noinput
python manage.py collectstatic --noinput
DJANGO_SETTINGS_MODULE=config.settings PYTHONPATH=/app python /stage/seed.py
exec gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers 2 \
  --threads 2 --timeout 120 --forwarded-allow-ips=172.30.225.2
