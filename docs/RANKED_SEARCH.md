# Ranked colors and finding metadata

Feature branch: `feature/ranked-colors-transit-search` (based on main).

## Operator workflow

1. In step 1 choose Bus or Metro, type the finding line, and enter the internal
   vehicle number and finding date (if known). NFC remains available. Line inputs
   are plain text placeholders; another teammate owns the future dropdown UI.
2. Upload the photos. Extraction orders up to four colors by estimated visible
   coverage on the first photo: largest area first, then smaller areas/accents.
3. Review the numbered color list. Use its up/down buttons to correct the order;
   the first color is labelled Principal. Added manual colors appear at the end.
   These are relative visual estimates, not segmentation measurements or percentages.
4. Finding details are entered only in step 1, not repeated in Details. The date
   can be unknown or approximate. The explicitly labelled finding line is used for
   matching; existing records are never backfilled from old registration metadata.
5. Review and save. Inventory corrections support both color order and finding
   metadata, with stale-revision checks and an append-only metadata audit.

Existing records have unknown color order until reviewed. They remain searchable;
no existing color list is retroactively treated as coverage-ranked. Under strict
filters, unknown finding metadata or unreviewed color order cannot satisfy the
corresponding requirement. Use the server
inventory's correction form to add finding metadata and confirm color order.

## Citizen search

Choose an optional transport, line and loss date. Dates are entered/displayed as
`dd/mm/yyyy` and sent/stored as ISO `YYYY-MM-DD`. Impossible and future dates are
rejected. Exact and approximate dates are distinguished. Vehicle identifiers are
only requested from operators. Station text remains supplementary report data.

Every selected color must appear among the first three reviewed, coverage-ranked
colors. A selected line must match exactly (including transport), and a supplied
loss date requires a finding date within an inclusive ±7-day window. Unknown
required metadata excludes a record. Blank filters do not restrict candidates;
approximate dates still use the same ±7-day window. The UI displays candidates' ordered colors, finding details and
matching signals. Reference photos remain supporting material and are not searched.

## Ranking contract

The HTTP search uses the engine's `ranked_strict` policy. Apply the hard constraints
above first, then rank the surviving candidates:

- Start with BM25 over reviewed text. A candidate needs positive lexical overlap.
  Selected type remains an optional exact filter and contributes to query text;
  selected color filters are no longer appended to that text.
- Bounded text score: `BM25 / (1 + BM25)`.
- Finding line: +0.9 for a match; -0.2 for a known mismatch; 0 for unknown.
- Transport: +0.15 for a match; -0.15 for a known mismatch; 0 for unknown.
- Finding date on/after loss: `0.5 / (1 + days_after_loss / 7)`; before loss: -0.5.
  Halve date influence when either date is approximate. Unknown dates contribute 0.
- Colors: +0.45 times matched color weight / total object color weight. Known color
  order uses `1, 1/2, 1/3, ...`; older unordered lists use equal weights. Selecting
  any color absent from the first three ranked colors excludes the candidate.
- Sort by combined score, then metadata score, then ID for deterministic ties.

Weights are provisional, explainable prototype choices, not learned probabilities
or a measured accuracy improvement. Dates outside the inclusive ±7-day window exclude candidates. The existing `soft` and `strict` CLI policies remain available
with their previous behavior; `ranked` remains available for soft-ranking experiments. This is still lexical retrieval, not semantic search.

## API and database

- Registration accepts `finding: {transport, line, date, dateQuality}`. The transport
  is `bus`, `metro` or null; `dateQuality` is confirmed, approximate or unknown.
- Reviewed `details.colors` preserves order. `details.colorOrderKnown` confirms
  that it represents estimated coverage. Missing means legacy/unranked.
- `/api/search` accepts `transport`, `line`, `lostDate`, `dateApproximate` alongside
  description/filters. Saved reports accept these under `incident`, with `lossDate`.
- Results include `colorOrderKnown`, `foundTransport`, `foundLine`, `foundDate`,
  `dateQuality`, combined `score`, raw `textScore` and explanatory `signals`.
- Migration 003 adds color-order provenance, transport/report fields and the
  `finding_reviews` audit table. It preserves original records and images.
- Historical registration/report payloads remain supported, including retry hashes.

## Line catalogue

`client/transit-options.json` contains an offline snapshot taken on 13 October 2026
from [TMB's official transport page](https://www.tmb.cat/ca/transport-barcelona):
108 bus services and 11 Metro entries (10 branches plus the Montjuïc funicular).
Special bus services present in that source are included. This is TMB's network,
not all metropolitan operators: FGC, Rodalies and other operators are not invented
as TMB lines. Unknown-line choices remain available.

The backend uses this file to validate typed line codes. The browser no longer
loads the catalogue or renders line dropdowns; that UI belongs to a teammate.
No TMB API credentials are needed. To refresh the validation catalogue:

```bash
curl --fail --location https://www.tmb.cat/ca/transport-barcelona -o /tmp/tmb-lines.html
python scripts/update_transit_options.py /tmp/tmb-lines.html
```

The script validates minimum counts and stores only public line names/descriptions,
never page scripts or credentials. Review the diff before committing a refresh;
counts and routes can change. A future live integration can replace the snapshot.

## Verification

Python tests cover color dominance, unknown legacy order, real line reranking,
chronological plausibility, approximate dates, catalogue validation, SQL round trips,
metadata revision rollback, history, and idempotency. Run existing backend/database
suites with TEST_DATABASE_URL pointing to a disposable PostgreSQL service.

`client/tests/ranked-search.cjs` exercises mobile layout, first-step metadata, extraction progress, mocked
extraction order, manual reordering, invalid and day-first dates, persistence,
search, report storage and inventory corrections against a test server. Set
TEST_BASE_URL (default port 8002), TEST_PHOTO_1 and install Playwright/Chromium.
The existing prototype browser test additionally supports real Ollama extraction.

## Extraction progress

The extraction panel uses a native, accessible indeterminate progress bar while
waiting for Ollama, alongside elapsed seconds. Ollama does not supply a completion
percentage. The bar fills only when a valid response arrives; errors stop it, and
manual entry/reset hide it. Late responses from skipped attempts cannot restore it.
