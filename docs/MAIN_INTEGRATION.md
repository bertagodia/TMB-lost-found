# Main integration: WP3 database and WP4 operations

This branch merges `origin/main` through `b970e77` with ranked colors, strict
search and extraction progress. Main included the location and Match modules but
its final merged HTML no longer loaded them. The integrated page restores both.

## Operator workflow

1. In step 1, enter the transport, line, internal vehicle and finding date as
   before. Optionally choose an origin station or depot. Its assigned central
   appears immediately and is included in the review and saved registration.
2. Register the object with the existing photo/extraction/review workflow.
3. Save a citizen loss report through **Soc usuari → Desar i cercar**.
4. Open **Match**. Choose a real object and loss report and confirm the link.
   Multiple reports can be linked to one object and vice versa. Links require
   manual confirmation; search results never establish ownership automatically.
5. Review the linked reports and their supplied contacts. Enter the actual
   destination under **On s’envia / ubicació actual** and save. This records the
   sending time. The automatically assigned central is a routing suggestion,
   not evidence that shipment has happened.
6. Mark the object returned. It disappears from fresh searches. Reopen tracking
   to make it searchable again if its latest review is approved. Removing a
   link leaves the report and object intact.

Match now uses PostgreSQL instead of localStorage demo data. It reloads when
opened and persists across reloads and application restarts. Old browser demo
records are not imported as real inventory. Concurrent routing edits use revision
checks and require reopening Match after a conflict. Failed requests show an
error and do not claim success or silently queue operational changes.

The station/depot mappings supplied by WP4 live in `client/origin-options.json`.
Both the browser and server use this file; the server validates the origin and
computes its assigned destination. Origin is separate from vehicle identity and
from the confirmed transport/line used by strict search. Older submissions without
an origin remain supported, including retries.

## Database upgrade

The WP3 merge rewrote migration 001 and moved tables to the public schema. That
cannot be applied over an existing checksummed prototype database, and the later
migrations still expect `tmb`. The integration preserves migrations 001–003
byte-for-byte and implements the additions in **004_match_and_routing.sql**.

- Retains existing records, photos, extraction provenance, immutable reviews,
  review numbering and duplicate-submission protection.
- Adds report/contact update timestamps, nonempty-contact validation and indexes.
- Keeps `lost_line` as the report line column (already added in 003), rather than
  adding a competing `line`; adds the new optional `direction` field.
- Adds `object_routing` for origin, assigned central, actual location/destination,
  shipment/return times and revision; `object_matches` stores many-to-many links.
- No table is dropped, no data is silently reseeded and no demo data is imported.

Startup applies 004 automatically. Back up the database and photo directory first
as described in SETUP.md. Do not replace migration 001 or reset a volume to fix a
checksum error. If a separate installation already applied the rewritten public
schema directly, it needs a separate reviewed migration; this upgrade targets the
existing prototype's `tmb` schema and clean installations.

## Validation

Database, backend and search tests cover clean installation, upgrade from three
migrations with records/reports, legacy retries, routing validation, persistent
many-to-many links, stale revisions, shipment/return/reopen, and strict search.
`client/tests/ranked-search.cjs` exercises origin selection, registration,
extraction progress and failures, ranked color corrections, search, reports,
Match persistence and return/reopen on a disposable database.

The prototype remains local, with no staff authentication or role enforcement.
Contacts appear in the operator Match view, never in search results. This is not
a public or production deployment. The existing model and first-photo-only
extraction behavior have not changed.
