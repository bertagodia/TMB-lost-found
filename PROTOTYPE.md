# Functional local prototype

The prototype connects the existing WP4 interface, Qwen image extraction, PostgreSQL
and WP5 BM25 search. Open **http://127.0.0.1:8001** after starting the server below.
This is a local development application, not a public TMB service.

## What you can test

| Flow | Implemented behavior |
|---|---|
| Register a found object | Enter vehicle/line, upload two views, extract the first photo or choose manual entry, review multiple colors/type/material/description, save. |
| Image extraction | Local `qwen3-vl:2b-instruct`; JPEG including MPO, PNG and static WebP; original bytes retained. Drafts require human review. Identical image/model/prompt combinations reuse cached model output. |
| Durable storage | Original images live in the server data directory; PostgreSQL stores references, hashes, extraction attempts, original submissions and append-only reviews. |
| Server inventory | “Inventari del servidor” lists up to 200 recent objects, including records created from another browser. Correct fields, reject a review, mark returned, or reactivate. |
| Citizen search | “Soc usuari” searches current approved, registered objects using text, optional exact type and selected colors. Results include a photo, reviewed fields and reference ID. |
| Loss report | “Desar i cercar” stores the declaration and optional contact information in separate tables and returns candidates. “Cercar sense desar” runs a query without storing a declaration. |
| Reference image | An optional citizen image is stored privately as supporting material. It is **not** used to rank candidates in this version. |
| Retries | Duplicate registration/report IDs with the same request are idempotent. Different content conflicts. Operator network failures can queue the original request locally, subject to browser capacity. |

The model analyzes **only the first photo**. Both object views are stored. The
unmerged two-view experiment is not part of this prototype/database integration.
The existing form labels remain placeholders; generated descriptions are English.
Search is lexical, so use wording present in the reviewed description or select
object type/colors. There is no general multilingual/semantic translation layer.

Location and loss date are saved with a declaration. Free-text location is not
silently interpreted as a confirmed line, and registration time/vehicle are not
invented finding metadata. Unknown finding metadata does not exclude candidates.
Selected colors require all selected colors to be present on the reviewed object.
A result is a candidate, not verified ownership or an authorized return.

## Quick test on the running instance

1. Open **Operaris TMB**, enter `TEST` / `001`, and upload the two bottle photos.
2. Enter **Detalls**. Wait for extraction or click **Omplir manualment**. A cold
   model can take longer; the successful live bottle test took about 37 seconds.
3. Correct all fields, mark the review checkbox, review the summary and save.
4. Open **Inventari del servidor**. Your object should appear there.
5. In **Soc usuari**, search `bottle`, optionally choosing `Ampolla` and `Taronja`.
   Try **Cercar sense desar** or save a report using fictitious contact details.
6. In the inventory, correct the description and search again. Mark the object
   returned or reject its review: it must disappear from fresh search results.
   Reactivating a returned object restores it only if its latest review is approved.

One clearly labelled bottle test record has been left on this machine for immediate
search testing. Its images are the two previously supplied JPGs. The server
inventory is authoritative; the arrow/history button still summarizes that browser's
own submissions. No old JSON inventory is silently imported into PostgreSQL.

## Start on another computer

From this branch's repository root, install Python 3.11+, Docker Compose and Ollama:

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r backend/requirements.txt

export POSTGRES_PASSWORD='choose-a-local-password'
docker compose -f database/compose.yaml up -d --wait
export DATABASE_URL='postgresql://tmb:choose-a-local-password@127.0.0.1:55432/tmb'

ollama pull qwen3-vl:2b-instruct
# Run `ollama serve` in another terminal if the Ollama service is not running.
python -m backend.server --port 8001 --data-dir artifacts/prototype/storage
```

Use the same password in the database and connection URL; URL-encode special
characters. On Windows, activate `.venv\Scripts\Activate.ps1` and set environment
variables with `$env:NAME='value'`. PostgreSQL migrations are verified/applied on
server startup. No fake seed is required: register a real test object through the UI.

Without `DATABASE_URL`, the server retains its older JSON-only mode. The full
inventory, citizen search and report APIs require PostgreSQL. The health endpoint
`/api/health` reports `storage: "postgres"`; it checks database connectivity but
is not an image-inference health test. Reload the page after a server restart
because its local request token changes.

## This machine's running configuration

- Code checkout: `/tmp/tmb-prototype`, branch `prototype-integration`.
- PostgreSQL container: `tmb-prototype-db`, localhost port `55432`, named persistent
  volume `tmb-prototype-pgdata`. This is separate from the disposable test container.
- Images/cache: `/home/tomaspr/Documents/UPC/4A/PAE_lost-n-found/artifacts/prototype/storage`.
- Private runtime environment: the sibling `runtime.env` file (ignored by Git).
- Bottle test files: the sibling `test-photos/IMG_1621.jpg` and `IMG_1622.jpg`.
- Python environment: `/tmp/tmb-db-venv`.

To restart the current instance from this checkout:

```bash
podman start tmb-prototype-db
set -a
. /home/tomaspr/Documents/UPC/4A/PAE_lost-n-found/artifacts/prototype/runtime.env
set +a
/tmp/tmb-db-venv/bin/python -m backend.server --port 8001 \
  --data-dir /home/tomaspr/Documents/UPC/4A/PAE_lost-n-found/artifacts/prototype/storage
```

Start Ollama separately if needed. Temporary checkouts/environments may need
recreation after system cleanup; the Git branch, database volume and workspace
artifact directory preserve the implementation and records. Back up **both** the
PostgreSQL database and image directory together. Do not delete the volume to stop
it; `podman stop tmb-prototype-db` retains its records.

## Tests and API contract

```bash
# TEST_DATABASE_URL must point to a local PostgreSQL role with CREATEDB.
export TEST_DATABASE_URL="$DATABASE_URL"
python -m unittest discover -s database/tests -v
python -m unittest discover -s backend/tests -v
python -m unittest discover -s search/tests -v
node --check client/app.js
```

The PostgreSQL tests create their own uniquely named databases and remove them
at the end. The 50 Python tests passed, covering actual PostgreSQL, file storage,
retry concurrency, provenance, cache reuse, contact separation and search updates.
Backend DB tests are explicitly skipped if `TEST_DATABASE_URL` is missing.

A Playwright browser test lives at `client/tests/prototype.cjs`. With Playwright
and Chromium installed, set `TEST_PHOTO_1` and `TEST_PHOTO_2` to bottle images and
run `node client/tests/prototype.cjs`. It creates a test object/report, exercises
live Ollama, searches from a fresh browser, checks image display, edits and returns
the object, then reactivates it. Use a test instance. `MOCK_EXTRACTION=1` tests the
manual path without inference. `TEST_BASE_URL` defaults to port 8001.
`client/tests/retry.cjs` additionally verifies network failure with full browser
storage, stable retry IDs and compact local history; its test record is archived.

| Endpoint | Behavior |
|---|---|
| `POST /api/extract` | `{photo}` → reviewed-pending draft and a DB extraction-attempt ID. |
| `POST /lost-found` | Current operator payload → committed object, photos and review. Success: `queued:false`, `status:"stored-postgres"`. |
| `POST /api/inventory` | `{}` → recent operator inventory (up to 200). |
| `POST /api/review` | `{id,revision,reviewed:true,status,details}` → append correction/rejection; stale revision gets 409. |
| `POST /api/status` | `{id,status}` → registered, returned or archived. |
| `POST /api/search` | `{description,filters:{objectType,colors},lostDate}` → current candidates. |
| `POST /api/lost-reports` | Current citizen payload → stored report plus candidates. |
| `GET /api/photos/<id>` | Prepared JPEG preview of a currently searchable object's photo; never a staged or citizen-reference image. |

POST requests use the page's `X-Local-Token` and same-origin checks. SQL is
parameterized. Contact details and reference images are excluded from candidate
responses and model inputs. Search snapshots are rebuilt for every query; no
separate index synchronization service is needed for this small prototype.

## Limits for the next iteration

- Localhost only; there are no accounts, operator/citizen authorization or public
  deployment controls. The tabs are not access-control boundaries.
- Human review remains necessary. A usable model result can still be wrong.
- Browser offline storage has a size limit. Large unsent photos may not fit; the
  form then remains open for retry. Online saves do not depend on that quota.
- Photos are not transactionally committed with PostgreSQL. Validation failures
  clean up unused staged files; abandoned extraction attempts retain their source
  for audit. Automated retention/cleanup and crash-recovery reconciliation remain.
- No notifications, contact-management UI, claim verification, custody workflow,
  SharePoint import, embeddings or image-to-image search.
