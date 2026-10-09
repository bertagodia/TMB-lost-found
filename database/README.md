# PostgreSQL — basic inventory implementation

WP3 implements the inventory portion of [BACKBONE.md](BACKBONE.md): four tables,
versioned migrations, a Python repository, synthetic demo data and a reviewed-only
search view. PostgreSQL 17 and Python 3.11+ are the supported development setup.

**The existing UI and search engine still use their current local storage.** This
PR supplies their database foundation; HTTP/file-storage and BM25 integration are
the next step after merge. No change of model or Catalan-label translation is needed.

## Start a local database

From the repository root, with Docker Compose installed:

```bash
# Choose a development password; keep it out of Git.
export POSTGRES_PASSWORD='choose-a-local-password'
docker compose -f database/compose.yaml up -d --wait
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r database/requirements.txt
export DATABASE_URL='postgresql://tmb:choose-a-local-password@127.0.0.1:55432/tmb'
python -m database.migrate
python -m database.seed --demo
```

Use the same password in both places. Percent-encode special characters in the
connection URI. These commands do not load `.env` automatically. An existing local
PostgreSQL server also works: create an empty development database and set
`DATABASE_URL` to its owner connection. The database owner must be able to create
the `tmb` schema; migrations do not require extra PostgreSQL extensions.

The Compose service binds only localhost:55432 and persists its data in a named
volume. `docker compose -f database/compose.yaml down` stops it without deleting
that volume. Do not use `down -v` if you want to retain your records. These are
local development owner credentials, not production role/access configuration.

View the demo inventory:

```bash
docker compose -f database/compose.yaml exec postgres \
  psql -U tmb -d tmb -c 'SELECT * FROM tmb.searchable_objects;'
```

The seed creates a bottle with two photo references and three colors, plus a
manually reviewed keys record following a failed extraction. All dates of finding
remain unknown. IDs beginning `demo-wp3-` are reserved for these fixtures. **Image
keys, hashes and dimensions are synthetic; no image files are supplied.** Do not
use these rows to test image display. Re-running the seed does not append reviews,
overwrite corrections or reactivate a rejected object.

## Schema and enforced rules

| Table/view | Purpose |
|---|---|
| `tmb.found_objects` | Object ID, status, registration/finding context, immutable original fields and submission hash. |
| `tmb.photos` | Staged or attached file references, ordered positions, original hashes and verified metadata. |
| `tmb.extraction_runs` | Pending, succeeded or failed attempts; original output and proposed fields separate from human decisions. |
| `tmb.object_reviews` | Append-only approved/rejected revisions, reviewed attributes and searchable text. |
| `tmb.searchable_objects` | Only active objects whose **latest** review is approved. No photos, internal storage keys or model output. |
| `public.tmb_schema_migrations` | Applied migration filenames, checksums and server timestamps. |

IDs are text, including legacy client IDs. Photos may be staged before an object
exists; after attachment they cannot be moved or deleted through normal DML.
Identical image hashes do not merge objects. A composite FK binds each extraction
to the exact photo hash. A review referencing an extraction must use a completed
successful attempt belonging to that same object. Failed extraction does not
prevent a separate manual review.

Review insertion locks the object and allocates the next revision, including
concurrent writers. Completed extraction results and reviews cannot be overwritten
or deleted. Append a new attempt or review instead. A rejected latest review hides
the object even when an older review was approved; returned/archived objects are
also excluded. Unknown finding dates/lines stay unknown rather than inheriting
registration timestamps or vehicle metadata.

The database validates structural constraints and distinct colors, not the UI's
placeholder vocabulary. Backend must validate field choices against the shared
form options. An approved review requires searchable text; the repository builds
it from reviewed type, colors, material and optional description. A registration
may contain no photos for imports, and SQL permits N photos; the HTTP adapter must
retain the UI's current 1–2-photo limit.

## Python contract for the next integration

```python
import os
from database.repository import Repository

store = Repository(os.environ['DATABASE_URL'])
# After the backend has validated and stored the original file:
photo = store.create_photo(
    storage_key='objects/generated-file-id.jpg', image_sha256=verified_sha256,
    media_type='image/jpeg', size_bytes=verified_size, width=width, height=height,
    position=1,
)
attempt = store.start_extraction(
    photo['id'], model_name=model_name, model_digest=model_digest,
    prompt_version=prompt_version, preprocessing_version=preprocessing_version,
)
# Run Ollama OUTSIDE a transaction, then complete_extraction(...) or fail_extraction(...).
# After explicit human review:
record = store.register_object(
    client_id, photo_ids=[photo['id']], details=reviewed_fields, reviewed=True,
    extraction_id=completed_attempt_id, registered_line='H12',
    registered_vehicle='3421', vehicle_source='manual',
)
rows = store.searchable_objects()
```

The names `verified_sha256`, `reviewed_fields`, etc. represent values supplied by
the future backend adapter. `details` uses the current form shape: `colors` list,
`objectType`, `material`, `description`. Type/material may be `None` for imports.
The repository does not import the UI/search packages and does not accept data URLs.

- `create_photo`: creates a staged reference. Backend owns validation, file writes,
  access control and cleanup; SQL cannot verify that a file actually exists.
- `start_extraction`, `complete_extraction`, `fail_extraction`: preserve attempts;
  the model/config identity must be available when completing a successful run.
- `register_object`: one transaction adopts the staged photos and writes the object
  and its first review. IDs/ordered photo hashes, fields, extraction reference and
  normalized metadata determine idempotency. Identical retries return
  `duplicate=True`, even after subsequent corrections. Different content raises
  `ConflictError`; no existing record is overwritten. Re-staging identical bytes
  on a retry can leave unused staged references for backend cleanup.
- `add_review`: append a correction or rejection; `extraction_id` is optional for
  manual reviews. `reviewer_ref` is optional until real authentication exists.
- `set_status`: change registered/returned/archived status.
- `get_object`: internal object, photos and review history; do not expose wholesale
  as a citizen endpoint.
- `searchable_objects`: one database snapshot. Map its `id`, `description`,
  `found_date`, `date_quality`, `found_line`, `found_direction` to WP5 `FoundObject`.
  Keep `review_id`/`revision` as provenance. Rebuild BM25 from this snapshot for the
  first prototype so rejected/returned objects disappear without an index queue.

## Migrations and tests

`python -m database.migrate` is safe to repeat: it checks migration hashes and
applies missing files transactionally under an advisory lock. Changed/missing
applied migrations, out-of-order additions and SQL errors fail rather than silently
changing history. All pending files in one invocation commit together. Add a new
numbered SQL migration for future changes. There is no destructive automatic downgrade.

Tests require a local PostgreSQL role with `CREATEDB`. They create and drop only a
unique `tmb_test_<uuid>` database; they never reset the database in `DATABASE_URL`.

```bash
export TEST_DATABASE_URL="$DATABASE_URL"
python -m unittest discover -s database/tests -v
```

The Compose development owner has the required privilege. CI runs the same tests
against a PostgreSQL 17 service. Tests cover migration replay/tamper/rollback,
concurrent registration/reviews, provenance, immutable history, retries, rejection,
archival, manual fallback and repeatable demo data.

## Deliberate first-version choices

This implementation follows the inventory backbone over the older conceptual
[borrador](modelo-y-operaciones.md): text IDs, finding columns on the object,
optional description with derived reviewed search text, staged photos and versioned
extractions/reviews. This is the concrete proposal for review in this PR.

Deferred: citizen reports/contact tables, authentication/roles, actual file storage
and cleanup, JSON import, custody/returns workflows, SharePoint, and multiview
extraction provenance (a future migration can add multiple input-photo references
per extraction). Both object photos are already stored; each current extraction
references one photo. No embeddings or database search ranking are introduced.
