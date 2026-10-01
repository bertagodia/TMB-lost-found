"""Evaluación de recuperación; no mide acreditación ni devolución."""
import time

from .metrics import retrieval_metrics
from .reporting import build_report


def evaluate(engine, queries, policy='soft', window=2, k=3, min_score=0.0):
    rows = []
    inventory = {o['id'] for o in engine.objects}
    for query in queries:
        relevant = set(query['relevant_ids'])
        if relevant - inventory:
            raise ValueError('La verdad de referencia apunta a objetos ausentes del inventario')
        start = time.perf_counter()
        response = engine.search(query, policy=policy, window=window, k=k, min_score=min_score)
        elapsed = (time.perf_counter() - start) * 1000
        returned = {r['id'] for r in response['results']}
        eligible = set(response['eligible_ids'])
        rows.append({'query_id': query['id'], 'relevant_ids': sorted(relevant),
                     'returned_ids': [r['id'] for r in response['results']],
                     **retrieval_metrics(relevant, returned, eligible, k),
                     'latency_ms': elapsed})
    return build_report(rows, policy, window, k, min_score)
