#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
if [[ -f .env ]]; then
  set -a
  source .env
  set +a
fi
exec .venv/bin/python manage.py runserver 127.0.0.1:8000
