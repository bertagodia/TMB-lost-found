# FastAPI on the current prototype

This implementation adapts the FastAPI routing, local middleware, request models
and error-response approach from [PR #7](https://github.com/bertagodia/TMB-lost-found/pull/7)
(WP3 commit `d438386`). It does not merge that PR's older UI, `public` database
schema, migration 002, or replacement application service.

The existing `PostgresApplication` remains responsible for extraction provenance,
registration, review revisions, ranked colors, strict search, reports and Match.
The browser URLs, request shapes and successful response bodies are retained.
There are no database changes for this transition. Applied migrations 001–005,
photo paths, extraction caches and existing submission hashes remain valid.

## Launch

Activate the project's virtual environment, then:

```bash
python -m pip install -r backend/requirements.txt
# Keep DATABASE_URL and the storage directory used by your current installation.
python -m backend.server --port 8001 --data-dir artifacts/prototype/storage
```

As before, `DATABASE_URL` enables PostgreSQL and verified migrations run at startup.
Without it, the legacy JSON registration/extraction mode still works; inventory,
search, reports and Match return an explicit 503 explaining that PostgreSQL is
required. The default model is still `qwen3-vl:2b-instruct`; use `--model` to change it.

- UI: http://127.0.0.1:8001/
- Interactive API documentation: http://127.0.0.1:8001/docs
- OpenAPI schema: http://127.0.0.1:8001/openapi.json
- Health: http://127.0.0.1:8001/api/health

The health response retains `status`, `model` and `storage`. It checks the database,
not model inference. Swagger UI loads its assets from a CDN; the OpenAPI JSON and
normal application UI remain available without those assets.

## Existing routes and additions

| Method / route | Behavior |
|---|---|
| POST `/api/extract` | Existing extraction, provenance and cache; ranked-color fields |
| POST `/lost-found` | Existing registration and idempotent retries |
| POST `/api/objects` | Alias for registration, with the same 200 receipt contract |
| POST `/api/inventory` | Existing inventory response; send `{}` |
| GET `/api/objects` | Alias for inventory; returns `objects`, up to the current 200-record limit |
| POST `/api/review` | Review with required `id`, `revision`, `reviewed`, `details`; optional finding corrections |
| POST `/api/status` | Registered / returned / archived status |
| POST `/api/search` | Same-line/transport, inclusive ±7 days, every selected color in the first three; BM25 ranks eligible objects |
| POST `/api/lost-reports` | Save a report and return search candidates, as the UI expects |
| POST `/api/matches` | Read or update persistent manual links and operational tracking |
| GET `/api/photos/{id}` | Image of a currently approved, registered object |
| GET `/api/photos/{id}/content` | Alias for that same restricted image |

The PR's additional resource CRUD/pagination endpoints and citizen offline queue
are not introduced here. This change establishes FastAPI without replacing the
working workflows. No photo endpoint exposes staged or citizen-reference images.

## Calling the API

The server still binds to `127.0.0.1`. POST requests and GET `/api/objects` require
the per-process `X-Local-Token` header. Load the UI, open the browser developer
console, and read the local token:

```javascript
document.querySelector('meta[name="local-token"]').content
```

Paste it into **Authorize** in `/docs`. Use the same hostname and port for UI and
docs. Reload after a server restart: the token changes. This local request token
is not a user account, a production API key, or an authorization boundary between
operators and citizens. Contacts remain limited to the operator Match response;
search responses do not include them.

Example search body:

```json
{
  "description": "orange bottle",
  "transport": "bus",
  "line": "H12",
  "lostDate": "2026-04-03",
  "filters": {"colors": ["Taronja"]}
}
```

Dates in the API are ISO `YYYY-MM-DD`; the UI continues to display/input
`dd/mm/yyyy`. Input models accept the current nested `finding`, `origin`, and
`vehicle.transport` structures. They also preserve older single-color submissions
and two-field origins. Omitted defaults are not inserted into service payloads,
so merely switching to FastAPI does not alter retry hashes.

Errors retain an `error` message for the current UI and add a machine-readable
`code`. Invalid request shapes return 422, domain validation 400, stale revisions
and busy extraction 409, and database unavailability 503. Validation errors omit
submitted values, photo bytes and contact contents. Request bodies are bounded
at 58 MiB, including chunked requests. Synchronous service calls run in FastAPI's
worker threads so inference does not directly block the event loop.

## Tests

```bash
python -m pip install -r backend/requirements-dev.txt
python -m unittest discover -s backend/tests -v
```

Set `TEST_DATABASE_URL` to an isolated PostgreSQL role with CREATEDB to include
API/database tests; each suite creates and removes its own database. The API tests
exercise real PostgreSQL, old submission retries, model-output caching, current
origin/finding payloads, strict search, stale reviews, Match and photo visibility.
Inference is mocked. Existing Playwright scripts in `client/tests/` also run
unchanged in their workflow against this server.

## University model server

This change replaces the application's HTTP transport with FastAPI. It does not
yet move the model: inference and model-digest lookup still use local Ollama.
Remote inference will need a configured model API URL and the university's access
requirements. The browser should continue to call this backend; model credentials
should stay on the backend. Deployment/authentication and remote inference can be
added independently of these current UI and database contracts.
