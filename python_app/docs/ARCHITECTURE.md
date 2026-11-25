# Code organization

Lumière keeps HTTP handling, shared business rules and browser interaction in separate modules. The application still uses Django sessions and server-rendered pages with Vue components for interaction. The refactor does not introduce a second API layer or change database tables.

## Backend entry points

| Location | Responsibility |
| --- | --- |
| `config/urls.py` | Project routing, Django admin and local media serving. |
| `cinema/urls.py` | Named application routes, including authentication and room endpoints. |
| `cinema/views/` | HTTP validation, permission checks, transactions and responses, grouped by feature. |
| `cinema/access.py` | Playback eligibility shared by video, subtitles and rooms. |
| `cinema/queries.py` | Public catalog, discovery metadata and viewing-history querysets. |
| `cinema/rooms/access.py` | Room lifetime, membership, presence, capacity and admission settings. |
| `cinema/rooms/media.py` | Media version changes, source reset and player snapshots/context. |
| `cinema/rooms/playlist.py` | Playlist serialization, limits, append and ordering operations. |
| `cinema/validation.py` | Shared positive database-identifier parsing. |
| `cinema/admin.py` | Single model-admin registration entry point and compatibility exports. |
| `cinema/admin_components/` | Catalog, community, membership, subtitle and report admin classes; shared filters and mixins. |

`cinema/views/__init__.py` explicitly exports the existing endpoints, so URL names and existing Python imports remain stable. Add implementation code to the corresponding feature module, not to the package initializer. Shared policies and queries do not import views. Translation, transcription and subtitle endpoints import playback permissions directly from `cinema.access`.

Room mutations retain their existing transaction and row-lock boundaries in the view layer. `reset_room_media` prepares a new source and returns the fields to persist; the caller owns locking and saving. Selection, playlist playback and the admin editor reuse it. Presence is shared between the seat roster and voice discovery; capacity checks retain their separate admission rules.

`admin_components/common.py` contains reusable metadata localization, upload-error validation, annotated film counts and display formatters. It does not register models. Keep registrations in `admin.py` so importing a helper cannot accidentally register a model twice.

## Viewing frontend

| Location under `frontend/src/viewing/` | Responsibility |
| --- | --- |
| `main.ts` | Mount page components and connect drivers. |
| `room-types.ts`, `voice-types.ts` | Shared TypeScript contracts; no runtime startup. |
| `room-driver.ts` | Room synchronization, chat and participant actions. |
| `room-media.ts` | Replace player sources and clean up the previous player. |
| `RoomPlaylist.vue` | Render playlist and suggestion controls. |
| `use-room-playlist.ts` | Reactive playlist state, polling and mutations; common reordering logic for buttons and drag/drop. |
| `voice-driver.ts` | Voice session, microphone consent, host restrictions and recovery coordination. |
| `voice-transport.ts` | Timed authenticated HTTP requests and CSRF-protected voice commands. |
| `voice-peers.ts` | WebRTC negotiation, remote audio, peer cleanup and connection retries. |
| `voice-activity.ts` | Audio-level detection for speaking indicators. |

Vue components render state and dispatch actions. Shared types belong in the contract modules, rather than inside drivers. Browser resources belong to the module that creates them: close peer connections, stop tracks, abort requests and remove listeners when their session or component ends. Keep microphone permission prompts in the session coordinator so rendering or reconnecting a peer cannot enable a microphone.

## Extending a feature

1. Put request/response handling in its feature view and common rules in the existing shared module that owns them.
2. Import models and helpers explicitly; avoid wildcard imports and dependencies from shared modules back into views.
3. Reuse the access policy without weakening the endpoint's login, CSRF, host checks, transaction or row locks.
4. Keep URL names, response fields and browser event/data-attribute contracts stable unless intentionally changing the feature.
5. Verify the affected behavior with existing regression tests; add tests for new failure modes at the module boundary.

Run from `python_app/` with the project environment active:

```bash
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test cinema cinema.audit_experience_cases
npm --prefix frontend run build
node --test tests/*.test.cjs
```
