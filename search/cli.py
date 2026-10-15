"""Local operator/developer demo, not a public claimant interface."""
import argparse
import hashlib
from dataclasses import asdict
import json
from pathlib import Path
import sys

from .settings import DEFAULT_MODEL, DEFAULT_TIMEOUT
from .engine import SearchEngine
from .evaluation import evaluate, extraction_summary, query_from_dict
from .storage import Inventory, write_json


def emit(value):
    print(json.dumps(value, ensure_ascii=False, indent=2))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--store', type=Path, default=Path('artifacts/search/inventory.json'))
    commands = parser.add_subparsers(dest='command', required=True)
    command = commands.add_parser('import', help='Import JSON objects without overwriting IDs')
    command.add_argument('file', type=Path)
    command = commands.add_parser('list', help='Show review and extraction status')
    command = commands.add_parser('show', help='Inspect sources, extraction keys, and review history')
    command.add_argument('id')
    command = commands.add_parser('extract', help='Resume a batch; changed models create new versions')
    command.add_argument('--id', action='append')
    command.add_argument('--model', default=DEFAULT_MODEL, help=f'Modelo local (default: {DEFAULT_MODEL})')
    command.add_argument('--timeout', type=float, default=DEFAULT_TIMEOUT)
    command = commands.add_parser('review', help='Explicitly approve corrected text or reject a record')
    command.add_argument('id')
    command.add_argument('--text', default='')
    command.add_argument('--reject', action='store_true')
    command.add_argument('--reviewer', required=True)
    command.add_argument('--source', choices=['manual', 'extraction'], default='manual')
    command.add_argument('--extraction-key')
    command.add_argument('--seconds', type=float)
    command = commands.add_parser('photo', help='Extract a claimant photo for manual review')
    command.add_argument('image', type=Path)
    command.add_argument('--model', default=DEFAULT_MODEL, help=f'Modelo local (default: {DEFAULT_MODEL})')
    command.add_argument('--output', type=Path, required=True)
    command.add_argument('--timeout', type=float, default=DEFAULT_TIMEOUT)
    command = commands.add_parser('search', help='Search only approved inventory text')
    command.add_argument('description')
    command.add_argument('--lost-date')
    command.add_argument('--date-approximate', action='store_true')
    command.add_argument('--line')
    command.add_argument('--direction')
    command.add_argument('--limit', type=int, default=5)
    command.add_argument('--photo-result', type=Path)
    command.add_argument('--reviewed-photo-text')
    command.add_argument('--photo-action', choices=['combine', 'ignore'])
    command.add_argument('--output', type=Path)
    add_search_options(command)
    command = commands.add_parser('evaluate', help='Evaluate labeled queries and compare text variants')
    command.add_argument('queries', type=Path)
    command.add_argument('--variant', choices=['manual', 'reviewed', 'extraction', 'compare'], default='compare')
    command.add_argument('--annotations', type=Path)
    command.add_argument('--output', type=Path, required=True)
    add_search_options(command)
    args = parser.parse_args(argv)
    try:
        inventory = Inventory(args.store)
        if args.command == 'import':
            emit({'imported': inventory.import_file(args.file)})
        elif args.command == 'list':
            emit([{'id': r['id'], 'extractions': len(r['extractions']),
                   'status': r['reviews'][-1]['status'] if r['reviews'] else 'pending'}
                  for r in inventory.data['objects'].values()])
        elif args.command == 'show':
            emit(inventory.get(args.id))
        elif args.command == 'review':
            inventory.review(args.id, text=args.text, status='rejected' if args.reject else 'approved',
                             reviewer=args.reviewer, source=args.source,
                             extraction_key=args.extraction_key, elapsed_seconds=args.seconds)
            emit({'id': args.id, 'status': 'rejected' if args.reject else 'approved'})
        elif args.command == 'extract':
            from .pipeline import extract_batch
            report = extract_batch(inventory, model=args.model, object_ids=args.id, timeout=args.timeout)
            emit(report)
            return 1 if report['failed'] else 0
        elif args.command == 'photo':
            from .pipeline import extract_version, model_digest
            if args.output.exists():
                raise ValueError('Photo output already exists; choose a new path')
            result = extract_version(args.image, model=args.model, digest=model_digest(args.model),
                                     source='claimant', timeout=args.timeout)
            args.output.parent.mkdir(parents=True, exist_ok=True)
            with args.output.open('x', encoding='utf-8') as handle:
                json.dump(result, handle, ensure_ascii=False, indent=2)
            emit(result)
        elif args.command == 'search':
            photo = None
            text = args.description.strip()
            if args.photo_result:
                photo = json.loads(args.photo_result.read_text(encoding='utf-8'))
                if photo['result']['source'] != 'claimant':
                    raise ValueError('Use an extraction created by the photo command')
                if not args.photo_action:
                    raise ValueError('Inspect both sources, then choose --photo-action combine or ignore')
                if args.photo_action == 'combine':
                    if not args.reviewed_photo_text or not args.reviewed_photo_text.strip():
                        raise ValueError('Combining requires --reviewed-photo-text after resolving discrepancies')
                    text = text + '. ' + args.reviewed_photo_text.strip()
            elif args.photo_action or args.reviewed_photo_text is not None:
                raise ValueError('Photo options require --photo-result')
            query = query_from_dict({'description': text, 'lost_date': args.lost_date,
                                     'date_approximate': args.date_approximate,
                                     'line': args.line, 'direction': args.direction})
            objects = inventory.objects()
            descriptions = {o.id: o.description for o in objects}
            result = SearchEngine(objects).search(query, policy=args.policy, window_days=args.window_days,
                                                   limit=args.limit, min_text_score=args.min_text_score)
            report = {'sources': {'original_description': args.description,
                                  'photo_extraction': photo, 'photo_action': args.photo_action,
                                  'reviewed_photo_text': args.reviewed_photo_text},
                      'query': {**asdict(query), 'lost_date': args.lost_date},
                      'policy': args.policy, 'window_days': args.window_days,
                      'min_text_score': args.min_text_score,
                      **asdict(result)}
            report['candidates'] = [{**asdict(c), 'description': descriptions[c.object_id]}
                                    for c in result.candidates]
            if args.output:
                write_json(args.output, report)
            emit(report)
        elif args.command == 'evaluate':
            cases = json.loads(args.queries.read_text(encoding='utf-8'))
            variants = ['manual', 'extraction', 'reviewed'] if args.variant == 'compare' else [args.variant]
            annotations = json.loads(args.annotations.read_text(encoding='utf-8')) if args.annotations else None
            report = {'schema_version': 1, 'dataset': str(args.queries),
                      'queries_sha256': hashlib.sha256(args.queries.read_bytes()).hexdigest(),
                      'inventory_sha256': hashlib.sha256(json.dumps(inventory.data, sort_keys=True).encode()).hexdigest(),
                      'runs': [evaluate(inventory, cases, variant=v, policy=args.policy,
                                        window_days=args.window_days, min_text_score=args.min_text_score)
                               for v in variants],
                      'extraction': extraction_summary(inventory, annotations)}
            write_json(args.output, report)
            emit(report)
        return 0
    except (ValueError, OSError, KeyError, TypeError, RuntimeError, ImportError) as exc:
        print(f'Error: {exc}', file=sys.stderr)
        return 1


def add_search_options(parser):
    parser.add_argument('--policy', choices=['soft', 'strict'], default='soft')
    parser.add_argument('--window-days', type=int, default=2)
    parser.add_argument('--min-text-score', type=float, default=0)
