"""Offline retrieval evaluation with explicit labels and filter diagnostics."""
from datetime import date
import time

from .engine import SearchEngine
from .models import SearchQuery


def query_from_dict(value):
    value = dict(value)
    if value.get('lost_date') is not None:
        value['lost_date'] = date.fromisoformat(value['lost_date'])
    return SearchQuery(**value)


def evaluate(inventory, cases, *, variant='reviewed', policy='soft', min_text_score=0,
             window_days=2):
    if not cases:
        raise ValueError('Evaluation requires at least one labeled query')
    engine = SearchEngine(inventory.objects(variant))
    known = set(inventory.data['objects'])
    rows = []
    case_ids = set()
    for case in cases:
        if not case['id'] or case['id'] in case_ids:
            raise ValueError('Evaluation case IDs must be unique and nonempty')
        case_ids.add(case['id'])
        relevant = set(case['relevant_ids'])
        if relevant - known:
            raise ValueError(f'Unknown relevance labels in {case["id"]}: {sorted(relevant - known)}')
        query = query_from_dict(case['query'])
        started = time.perf_counter()
        result = engine.search(query, policy=policy, window_days=window_days,
                               limit=5, min_text_score=min_text_score)
        latency = (time.perf_counter() - started) * 1000
        returned = [c.object_id for c in result.candidates]
        metrics = {}
        for k in (1, 3, 5):
            selected = set(returned[:k])
            hits = len(selected & relevant)
            metrics[str(k)] = {'precision': hits / k,
                               'recall': hits / len(relevant) if relevant else None,
                               'false_positive_ids': sorted(selected - relevant),
                               'false_negative_ids': sorted(relevant - selected)}
        rows.append({'id': case['id'], 'category': case.get('category', 'unspecified'),
                     'description_quality': case.get('description_quality', 'unspecified'),
                     'modality': case.get('modality', 'text'),
                     'relevant_ids': sorted(relevant), 'returned_ids': returned,
                     'latency_ms': latency, 'at_k': metrics,
                     'filtered_relevant_ids': sorted(relevant & set(result.excluded_ids)),
                     'unindexed_relevant_ids': sorted(relevant - {o.id for o in engine.objects}),
                     'ranking_missed_ids_at_5': sorted(relevant & set(result.eligible_ids) - set(returned))})

    def summarize(group):
        matched = [r for r in group if r['relevant_ids']]
        no_match = [r for r in group if not r['relevant_ids']]
        return {'queries': len(group), 'matched_queries': len(matched),
                'no_match_queries': len(no_match),
                'no_match_false_positive_rate': (sum(bool(r['returned_ids']) for r in no_match) / len(no_match)
                                                if no_match else None),
                'mean_latency_ms': sum(r['latency_ms'] for r in group) / len(group),
                'at_k': {str(k): {
                    'mean_precision': sum(r['at_k'][str(k)]['precision'] for r in group) / len(group),
                    'mean_recall': (sum(r['at_k'][str(k)]['recall'] for r in matched) / len(matched)
                                    if matched else None),
                } for k in (1, 3, 5)}}

    return {'variant': variant, 'policy': policy, 'window_days': window_days,
            'min_text_score': min_text_score, 'indexed_objects': len(engine.objects),
            'summary': summarize(rows),
            'groups': {field: {value: summarize([r for r in rows if r[field] == value])
                              for value in sorted({r[field] for r in rows})}
                       for field in ('category', 'description_quality', 'modality')},
            'queries': rows}


def extraction_summary(inventory, annotations=None):
    """Attribute errors need human labels; missing annotations are not zero errors."""
    extractions = [e for r in inventory.data['objects'].values() for e in r['extractions']]
    durations = [r['elapsed_seconds'] for obj in inventory.data['objects'].values()
                 for r in obj['reviews'] if r.get('elapsed_seconds') is not None]
    annotation_report = None
    if annotations is not None:
        seen = set()
        for row in annotations:
            record = inventory.get(row['object_id'])
            if not any(e['key'] == row['extraction_key'] for e in record['extractions']):
                raise ValueError('Attribute annotation references an unknown extraction')
            identity = (row['object_id'], row['extraction_key'])
            if identity in seen:
                raise ValueError('Duplicate attribute annotation')
            seen.add(identity)
            for key in ('omitted_attributes', 'invented_attributes'):
                if not isinstance(row[key], list) or not all(isinstance(x, str) for x in row[key]):
                    raise ValueError(f'{key} must be a list of human-labeled attribute names')
        annotation_report = {'annotated_images': len(annotations),
                             'omitted_attributes': sum(len(x['omitted_attributes']) for x in annotations),
                             'invented_attributes': sum(len(x['invented_attributes']) for x in annotations)}
    return {'extractions': len(extractions),
            'total_extraction_seconds': sum(e['result']['elapsed_seconds'] for e in extractions),
            'review_timings_recorded': len(durations), 'total_review_seconds': sum(durations),
            'attribute_errors': annotation_report,
            'cost': None, 'cost_note': 'Local compute cost is not measured; latency is recorded.'}
