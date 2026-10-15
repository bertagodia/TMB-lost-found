# Prototype feedback and deferred improvements

Recorded: 9 October 2026. Status: backlog, not implemented.

These changes capture feedback from hands-on prototype testing. Keep the current
application running as-is; use this document to scope the next iteration.

## 1. Prioritize the line where the object was found

Provide a dedicated, optional citizen line filter, with an explicit unknown option.
Capture a confirmed finding line on the operator side and pass the citizen's line
through the search API. A registration line is not necessarily the finding line:
do not silently copy registration context into confirmed finding metadata.

The current citizen location is free text saved with a report; it is not used by
search. The engine supports line metadata, but the HTTP integration does not pass
it. Its existing soft metadata score only breaks equal text scores, so simply
connecting the field would not make line a meaningful priority.

Proposed default: substantially favor otherwise relevant matches on the selected
line, retaining unknown-line candidates below comparable confirmed matches. Offer
an explicit strict line filter if needed. Decide and evaluate the ranking strength
before implementation rather than assigning an untested weight.

Acceptance: a citizen can search by a known line; comparable same-line candidates
rank above others; unknown lines remain distinguishable; registration context is
never presented as a confirmed finding location.

## 2. Use dd/mm/yyyy dates

Display and accept dates in day/month/year order. The current native date input
uses browser/OS formatting, which can display month/day/year. Setting the page
language alone does not guarantee the desired presentation.

Keep ISO `YYYY-MM-DD` in API payloads and database values. Validate actual calendar
dates and preserve accessible keyboard and mobile input.

Acceptance: `03/04/2026` clearly means 3 April 2026 in the UI and reaches the API as
`2026-04-03`; invalid dates are rejected; browser locale cannot reverse the meaning.

## 3. Make color matching more forgiving

Currently every selected color must exist in the reviewed object's color list.
This SQL filter runs before text ranking, so one uncertain or missing color can
remove an otherwise strong description match completely.

Proposed default: use color overlap as supporting ranking evidence rather than
mandatory exclusion. Multiple selected colors should accommodate uncertainty,
lighting differences and multicolored objects. If a strict color mode is useful,
make it an explicit refinement rather than the default.

Acceptance: a strong description match remains visible when one selected color is
missing; color overlap helps distinguish otherwise similar objects. Include
multicolor, unknown-color and dark gray/black cases in evaluation.

## 4. Keep vehicle numbers internal

Citizens should not have to remember or provide the vehicle identifier. The
current location field is optional, but its example explicitly suggests a bus
number. Remove that suggestion and ask for a known line or station instead.

Keep vehicle identifiers available to operators for internal tracking. Separate
these from citizen-facing line and station information.

Acceptance: the citizen flow never asks for a vehicle number and can complete with
an unknown line; operators retain their internal vehicle information.

## 5. Simplify the citizen object-type field

Make the description the primary input. The existing type selector is optional,
but selecting it applies an exact filter and can hide relevant unusual objects.

Consider moving type into optional refinements or suggesting an editable type from
the description. Never turn an inferred, uncertain type into a hidden hard filter.
Retain structured type internally for operator review, reporting and refinement;
its internal usefulness does not require citizens to repeat their description.

Acceptance: description-only searches remain fully supported, including objects
outside the predefined categories. Any type suggestion can be cleared or corrected.

## 6. Keep citizen image upload as a placeholder

The current citizen reference photo can remain optional supporting material. It is
stored privately when saving a report and does not affect matching. Make that
limitation clear in the UI until photo-based citizen search is implemented and
evaluated. Do not imply that uploading a picture improves current ranking.

## Testing observation

The user reported good results with a bowl photo, an unusual object in their tests.
Keep this as positive qualitative feedback, not a measured accuracy claim. Include
bowls and other less common objects in a future repeatable evaluation, checking
description-only retrieval as well as uncertain colors, types and lines.

## How matching currently works

1. At operator ingestion, local `qwen3-vl:2b-instruct` extracts attributes from the
   first object photo. A person reviews/corrects these before registration.
2. `database/repository.py` builds searchable text from the reviewed object type,
   colors, material and description. Only approved, currently registered objects
   enter the searchable inventory.
3. `backend/postgres.py` first applies exact selected-type and all-selected-colors
   SQL filters. It combines the citizen description with selected type/color
   labels and passes that text to the search engine.
4. `search/engine.py` uses BM25 word matching: lowercase and accent normalization,
   word tokenization and a small Spanish stopword list. Shared rarer words carry
   more weight; frequency and document length also affect the score. Results need
   positive word overlap. There is no general synonym expansion, translation,
   embedding model or image-to-image comparison.
5. The endpoint returns up to 20 candidates sorted by text relevance. Available
   date metadata only breaks text-score ties. Line/direction are not passed by the
   current endpoint. Finding metadata must actually be known to contribute.

The score is a retrieval score, not a probability of ownership or a confidence
percentage. Qwen produces the initial photo description; it does not judge each
citizen query against the inventory. Citizen reference photos are not model inputs.

Implementation references: `client/index.html`, `client/app.js`,
`backend/postgres.py`, `database/repository.py`, and `search/engine.py`.
