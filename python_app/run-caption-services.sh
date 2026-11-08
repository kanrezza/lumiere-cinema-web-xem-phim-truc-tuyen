#!/usr/bin/env bash
# Local-only caption services and database workers. Does not start the web server.
set -euo pipefail
umask 077
cd "$(dirname "$0")"

caption_download_models=0
caption_check_only=0
for caption_argument in "$@"; do
  case "$caption_argument" in
    --download-models) caption_download_models=1 ;;
    --check) caption_check_only=1 ;;
    --help|-h)
      printf '%s\n' 'Usage: ./run-caption-services.sh [--download-models] [--check]' \
        'Starts/reuses loopback translation and speech services, then runs both caption workers.' \
        '--download-models permits the initial official model downloads when starting missing services.' \
        '--check only verifies virtual environments, configuration and running service health.' \
        'Ctrl+C stops only child processes started by this helper; existing services are retained.'
      exit 0 ;;
    *) printf 'Unknown option: %s\n' "$caption_argument" >&2; exit 2 ;;
  esac
done

if [[ -f .env ]]; then
  set -a
  source .env
  set +a
fi
export PYTHONUNBUFFERED=1

for caption_python in .venv/bin/python .translation-venv/bin/python .speech-venv/bin/python; do
  if [[ ! -x "$caption_python" ]]; then
    printf 'Missing %s. Follow the optional caption setup in README.md first.\n' "$caption_python" >&2
    exit 1
  fi
done

# This helper manages the two bundled local services only. Never redirect a
# configured remote endpoint or start an extra service on an occupied port.
case "${TRANSLATION_API_URL:-}" in
  http://127.0.0.1:5001|http://127.0.0.1:5001/|http://localhost:5001|http://localhost:5001/) ;;
  *) printf '%s\n' 'Set TRANSLATION_API_URL=http://127.0.0.1:5001 in .env to use this local helper.' >&2; exit 1 ;;
esac
case "${SPEECH_API_URL:-}" in
  http://127.0.0.1:5002|http://127.0.0.1:5002/|http://localhost:5002|http://localhost:5002/) ;;
  *) printf '%s\n' 'Set SPEECH_API_URL=http://127.0.0.1:5002 in .env to use this local helper.' >&2; exit 1 ;;
esac

caption_health() {
  .venv/bin/python - "$1" <<'PY'
import json
import sys
from urllib.request import ProxyHandler, build_opener

kind = sys.argv[1]
port = 5001 if kind == 'translation' else 5002
try:
    with build_opener(ProxyHandler({})).open(f'http://127.0.0.1:{port}/health', timeout=2) as response:
        payload = json.loads(response.read(4097))
    valid = (payload.get('status') == 'ok' and payload.get('engine') == 'argos-local'
             and payload.get('modelVersion') == '1.9' and payload.get('pairs') == 2) if kind == 'translation' else (
        payload.get('status') == 'ready' and payload.get('offline') is True and payload.get('model') == 'tiny')
except Exception:
    valid = False
raise SystemExit(0 if valid else 1)
PY
}

caption_port_busy() {
  .venv/bin/python - "$1" <<'PY'
import socket
import sys

try:
    with socket.create_connection(('127.0.0.1', int(sys.argv[1])), timeout=1):
        pass
except OSError:
    raise SystemExit(1)
PY
}

if ((caption_check_only)); then
  caption_check_failed=0
  for caption_kind in translation speech; do
    if caption_health "$caption_kind"; then
      printf '%s service is ready.\n' "$caption_kind"
    else
      printf '%s service is not ready.\n' "$caption_kind" >&2
      caption_check_failed=1
    fi
  done
  exit "$caption_check_failed"
fi

caption_log_dir='reports/caption-services'
caption_lock_dir="$caption_log_dir/.runner-lock"
mkdir -p "$caption_log_dir"
if ! mkdir "$caption_lock_dir" 2>/dev/null; then
  caption_previous_pid=''
  if [[ -f "$caption_lock_dir/pid" ]]; then
    read -r caption_previous_pid < "$caption_lock_dir/pid" || true
  fi
  if [[ "$caption_previous_pid" =~ ^[0-9]+$ ]] && ! kill -0 "$caption_previous_pid" 2>/dev/null; then
    rm -f "$caption_lock_dir/pid"
    rmdir "$caption_lock_dir"
    mkdir "$caption_lock_dir"
  else
    printf '%s\n' 'A caption helper is already running, or its startup lock cannot be verified.' >&2
    exit 1
  fi
fi
printf '%s\n' "$$" > "$caption_lock_dir/pid"
caption_children=''
caption_cleanup() {
  trap - EXIT INT TERM
  # The list contains only direct child PIDs created below, never discovered
  # service PIDs. Existing processes on 5001/5002 are deliberately untouched.
  for caption_child in $caption_children; do
    kill -TERM "$caption_child" 2>/dev/null || true
  done
  for caption_child in $caption_children; do
    wait "$caption_child" 2>/dev/null || true
  done
  rm -f "$caption_lock_dir/pid"
  rmdir "$caption_lock_dir" 2>/dev/null || true
}
trap caption_cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

caption_start_service() {
  caption_kind="$1"
  caption_port="$2"
  caption_python="$3"
  caption_script="$4"
  caption_download_option="$5"
  if caption_health "$caption_kind"; then
    printf 'Reusing existing %s service on 127.0.0.1:%s.\n' "$caption_kind" "$caption_port"
    return
  fi
  if caption_port_busy "$caption_port"; then
    printf 'Port %s is occupied by an unhealthy or different service; nothing was stopped.\n' "$caption_port" >&2
    exit 1
  fi
  if ((caption_download_models)); then
    "$caption_python" "$caption_script" "$caption_download_option" >> "$caption_log_dir/$caption_kind-service.log" 2>&1 &
  else
    "$caption_python" "$caption_script" >> "$caption_log_dir/$caption_kind-service.log" 2>&1 &
  fi
  caption_service_pid=$!
  caption_children="$caption_children $caption_service_pid"
  # Initial model downloads can take several minutes. The helper stays attached
  # so the user can stop it; it does not silently become a background daemon.
  for ((caption_attempt=0; caption_attempt<300; caption_attempt++)); do
    if ! kill -0 "$caption_service_pid" 2>/dev/null; then
      printf '%s service exited. Check %s/%s-service.log.\n' "$caption_kind" "$caption_log_dir" "$caption_kind" >&2
      exit 1
    fi
    if caption_health "$caption_kind"; then
      printf '%s service is ready.\n' "$caption_kind"
      return
    fi
    sleep 1
  done
  printf '%s service startup timed out. Check %s/%s-service.log.\n' "$caption_kind" "$caption_log_dir" "$caption_kind" >&2
  exit 1
}

caption_start_service translation 5001 .translation-venv/bin/python services/local_translation.py --install-models
caption_start_service speech 5002 .speech-venv/bin/python services/local_speech.py --download-model

.venv/bin/python manage.py process_translations --watch >> "$caption_log_dir/translation-worker.log" 2>&1 &
caption_children="$caption_children $!"
.venv/bin/python manage.py process_transcriptions --watch >> "$caption_log_dir/speech-worker.log" 2>&1 &
caption_children="$caption_children $!"
printf 'Caption services and workers are ready. Logs: %s/. Press Ctrl+C to stop this helper.\n' "$caption_log_dir"

while true; do
  for caption_child in $caption_children; do
    if ! kill -0 "$caption_child" 2>/dev/null; then
      printf 'A caption child process stopped. Check the logs in %s/.\n' "$caption_log_dir" >&2
      exit 1
    fi
  done
  sleep 2
done
