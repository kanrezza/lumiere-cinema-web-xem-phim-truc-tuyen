#!/bin/sh
set -eu

cd "$(dirname "$0")/../.."
if [ "${1:-}" = build ]; then
  shift
  exec docker build --file deploy/staging/Dockerfile --tag lumiere-staging-app:local "$@" .
fi
exec docker compose --project-directory "$PWD" \
  --env-file deploy/staging/.env -f deploy/staging/compose.yml "$@"
