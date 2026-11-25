# Lumière

Lumière is a Vietnamese-language streaming application for managing a film catalog and watching films together. Viewers can browse titles and trailers, resume playback, and join rooms with synced playback, chat, and WebRTC voice. Staff use Lumière Studio to manage films, episodes, subtitles, and comments.

## Run locally

Use Python 3.14 and Node.js 24 to match CI. Run the setup from a Bash or Zsh shell.

```bash
git clone https://github.com/kanrezza/lumiere-cinema-web-xem-phim-truc-tuyen.git
cd lumiere-cinema-web-xem-phim-truc-tuyen/python_app

python3.14 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
npm --prefix frontend ci
npm --prefix frontend run build

test -f .env || cp .env.example .env
set -a
source .env
set +a

python manage.py migrate
python manage.py seed_demo
./run-local.sh
```

Open [the catalog](http://127.0.0.1:8000/browse/) and create a [viewer account](http://127.0.0.1:8000/accounts/register/). The sample environment uses SQLite, and `seed_demo` adds catalog entries and VIP plans.

Run the remaining commands from `python_app/` in a second shell. Activate `.venv` and export `.env` as above. `run-local.sh` loads `.env` when it starts Django.

## Try playback

Install FFmpeg with `libx264` and put `ffprobe` on your `PATH`. With `DEBUG=1`, generate a two-episode series with Vietnamese and English subtitles.

```bash
python manage.py make_demo_series
```

Sign in and open [Trạm ánh sáng (Demo)](http://127.0.0.1:8000/movies/tram-anh-sang-demo/) to try playback, subtitles, and resume position. For your own media, run `python manage.py createsuperuser`, add a film and upload an episode in [Django admin](http://127.0.0.1:8000/admin/), then run `python manage.py process_videos` and publish the film.

## How it works

The application lives in `python_app/`. Django renders the pages and handles sessions and access checks. Vite builds the Vue 3 and TypeScript entry points into `static/bundles/catalog/`, where Django reads the manifest. Rebuild the bundle after editing `frontend/src/`.

FFmpeg converts uploads to HLS in private storage. Django checks access before issuing a signed playback URL tied to the viewer's session. Viewers create a watch room before choosing a film. In the cinema view, the host builds and reorders a playlist, reviews film suggestions from members, and switches films or episodes while retaining participants, chat, and voice. Playback and chat sync through HTTP polling. Voice uses WebRTC.

The backend lives in [`cinema/`](python_app/cinema/). VNPay checkout reuses the same order when a signed checkout form is submitted again. VIP activates after a successful, verified server callback. Viewers can request account erasure from their profile, and superusers review those requests in Studio.

## Checks

```bash
npm --prefix frontend run build
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test cinema cinema.audit_experience_cases
node --test tests/*.test.cjs
```

The [GitHub Actions workflow](.github/workflows/ci.yml) runs the build and tests, then starts an HTTPS staging stack on the runner and runs a recovery drill.

## Operations

Use the [environment example](python_app/.env.example) for configuration keys. To use MySQL, set `DB_NAME` and the matching `DB_*` settings. Deployments with `DEBUG=0` require Redis. The staging stack uses Docker Compose with Caddy, MySQL, Redis, and simulated VNPay callbacks.

- [HTTPS staging and VNPay Sandbox setup](python_app/docs/STAGING.md)
- [Database and media backup and restore](python_app/docs/BACKUP_RESTORE.md)
- [Privacy requests and incident response](python_app/docs/PRIVACY_INCIDENTS.md)
- [Application configuration, captions, and WAF](python_app/README.md)
