"""Reproducible local vision benchmark; labels are never sent to the model."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import statistics
import time

from .extraction import _prepare_image, request_json, PREPROCESS_VERSION
from .form_extraction import extract_form, FORM_PROMPT_VERSION, FormFields
from .pipeline import model_digest
from .settings import DEFAULT_MODEL, DEFAULT_TIMEOUT
from .storage import write_json

BASELINE = Path(__file__).parent / 'benchmarks/wp4-fields-v2.json'
BENCHMARK_VERSION = 'vision-accuracy-v1'


def score(case, result):
    expected = case['expected']
    fields = result.get('fields', {})
    actual = set(fields.get('colors', []))
    required = set(expected['required_colors'])
    allowed = set(expected.get('allowed_colors', expected['required_colors']))
    name = result.get('recognized_object') or fields.get('description', '')
    return dict(category_correct=fields.get('objectType') == expected['objectType'],
                name_correct=bool(re.search(expected['name_pattern'], name, re.I)),
                color_hits=len(actual & required), color_required=len(required),
                color_allowed_hits=len(actual & allowed), color_predictions=len(actual),
                color_extra=sorted(actual - allowed), color_missing=sorted(required - actual),
                material_correct=(fields.get('material') == expected['material'])
                if expected.get('material') is not None else None,
                abstained=fields.get('objectType') is None)


def summarize(rows):
    groups = {}
    for row in rows:
        groups.setdefault((row['model'], row['variant'], row['view']), []).append(row)
    output = []
    for (model, variant, view), entries in groups.items():
        scores = [entry['scores'] for entry in entries]
        total = len(entries)
        colors_predicted = sum(s['color_predictions'] for s in scores)
        colors_required = sum(s['color_required'] for s in scores)
        material = [s['material_correct'] for s in scores if s['material_correct'] is not None]
        output.append(dict(model=model, variant=variant, view=view, images=total,
            distinct_objects=len({e['object_id'] for e in entries}),
            errors=sum('error' in e for e in entries),
            category_accuracy=sum(s['category_correct'] for s in scores)/total,
            name_accuracy=sum(s['name_correct'] for s in scores)/total,
            color_precision=sum(s['color_allowed_hits'] for s in scores)/colors_predicted if colors_predicted else None,
            color_recall=sum(s['color_hits'] for s in scores)/colors_required if colors_required else None,
            material_accuracy=sum(material)/len(material) if material else None,
            material_label_count=len(material),
            abstentions=sum(s['abstained'] for s in scores),
            median_seconds=statistics.median(e['seconds'] for e in entries),
            unsupported_details_reviewed=sum(e.get('unsupported_claims') is not None for e in entries),
            outputs_with_unsupported_details=sum(bool(e.get('unsupported_claims')) for e in entries)))
    return output


def legacy_extract(path, *, model, crop, timeout):
    baseline = json.loads(BASELINE.read_text())
    encoded, digest = _prepare_image(path, crop=crop)
    raw = json.loads(request_json([encoded], schema=baseline['schema'],
                                 prompt=baseline['prompt'], model=model, timeout=timeout))
    fields = {key: raw[key] for key in FormFields.model_fields}
    fields = FormFields.model_validate_json(json.dumps(fields)).model_dump(mode='json')
    if raw['quality'] not in {'usable', 'insufficient', 'ambiguous'} or type(raw['sensitive_content']) is not bool:
        raise ValueError('Invalid baseline quality fields')
    if raw['quality'] != 'usable' or raw['sensitive_content']:
        fields = dict(colors=[], objectType=None, material=None, description='')
    return dict(fields=fields, raw_draft=raw, image_sha256=digest, prompt_version='wp4-fields-v2')


def run(args):
    manifest = json.loads(args.manifest.read_text())
    cases = manifest['cases']
    if args.ids:
        wanted = set(args.ids.split(','))
        cases = [case for case in cases if case['id'] in wanted]
        if wanted - {case['id'] for case in cases}:
            raise ValueError('Unknown case ID')
    # Validate all files and labels before paying for any inference.
    prepared = []
    for case in cases:
        root = args.personal if case.get('source') == 'personal' else args.images
        if root is None:
            raise ValueError('This manifest requires --personal for the user-provided photos')
        path = root / case['image']
        image_hash = hashlib.sha256(path.read_bytes()).hexdigest()
        if image_hash != case['image_sha256']:
            raise ValueError(f"Source image changed: {case['id']}")
        prepared.append((case, path, image_hash))
    args.output.mkdir(parents=True, exist_ok=True)
    reviews = json.loads(args.reviews.read_text()) if args.reviews else {}
    if not isinstance(reviews, dict) or any(
            value is not None and (not isinstance(value, list) or any(not isinstance(claim, str) for claim in value))
            for value in reviews.values()):
        raise ValueError('Reviews must map run keys to null or lists of unsupported claims')
    rows = []
    for model in args.models:
        digest = model_digest(model)
        for variant in args.variants:
            version = FORM_PROMPT_VERSION if variant == 'current' else hashlib.sha256(BASELINE.read_bytes()).hexdigest()
            for view in args.views:
                for case, path, image_hash in prepared:
                    if view == 'crop' and not case.get('crop'):
                        continue
                    crop = case['crop'] if view == 'crop' else None
                    identity = [BENCHMARK_VERSION, image_hash, digest, variant, version, PREPROCESS_VERSION, crop]
                    key = hashlib.sha256(json.dumps(identity).encode()).hexdigest()
                    cache = args.output / 'runs' / (key + '.json')
                    if cache.exists():
                        run_result = json.loads(cache.read_text())
                    else:
                        started = time.monotonic()
                        try:
                            result = (extract_form(path, model=model, crop=crop, timeout=args.timeout)
                                      if variant == 'current' else legacy_extract(path, model=model, crop=crop, timeout=args.timeout))
                            run_result = dict(result=result)
                        except (ValueError, RuntimeError, OSError, KeyError, TypeError) as exc:
                            run_result = dict(error=str(exc), result={})
                        run_result.update(seconds=round(time.monotonic()-started, 3), identity=identity)
                        if model_digest(model) != digest:
                            raise RuntimeError('Model changed during benchmark; rerun with a stable model')
                        # Errors remain in the report but are retried on the next run.
                        if 'error' not in run_result:
                            write_json(cache, run_result)
                    row = dict(id=case['id'], object_id=case.get('object_id', case['id']), model=model,
                               model_digest=digest, variant=variant, view=view, run_key=key,
                               expected=case['expected'], **run_result)
                    row['scores'] = score(case, run_result['result'])
                    row['unsupported_claims'] = reviews.get(key)
                    rows.append(row)
                    report = dict(benchmark_version=BENCHMARK_VERSION, label_status=manifest['label_status'],
                                  caveats=['Development set; not an independent test set.',
                                           'Crops use labelled boxes, not automatic object detection.',
                                           'Unsupported details require manual review; null means unreviewed.',
                                           'Metrics are per image; multiple views of one object are not independent.'],
                                  review_file=str(args.reviews) if args.reviews else None,
                                  summary=summarize(rows), rows=rows)
                    write_json(args.output / 'report.json', report)
                    write_json(args.output / 'review-template.json', {r['run_key']:r['unsupported_claims'] for r in rows})
                    print(f"{model} {variant}/{view} {case['id']}: category={row['scores']['category_correct']} "
                          f"name={row['scores']['name_correct']} {row['seconds']}s "
                          f"{'ERROR: '+row['error'] if 'error' in row else ''}", flush=True)
    print(json.dumps(summarize(rows), indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, default=Path(__file__).parent/'benchmarks/objects-v1.json')
    parser.add_argument('--images', type=Path, required=True, help='Root of selected50 dataset')
    parser.add_argument('--personal', type=Path, help='Folder containing the two bottle JPGs')
    parser.add_argument('--models', nargs='+', default=[DEFAULT_MODEL])
    parser.add_argument('--variants', nargs='+', choices=['legacy', 'current'], default=['legacy', 'current'])
    parser.add_argument('--views', nargs='+', choices=['full', 'crop'], default=['full'])
    parser.add_argument('--ids', help='Optional comma-separated case IDs')
    parser.add_argument('--output', type=Path, default=Path('reports/vision-accuracy'))
    parser.add_argument('--reviews', type=Path, help='Reviewed copy of review-template.json: run key -> list of unsupported claims')
    parser.add_argument('--timeout', type=float, default=DEFAULT_TIMEOUT)
    args = parser.parse_args()
    try:
        run(args)
    except (ValueError, RuntimeError, OSError) as exc:
        parser.exit(1, f'Error: {exc}\n')


if __name__ == '__main__':
    main()
