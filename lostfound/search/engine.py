"""Orquestación de recuperación, filtros y ranking."""
import math

from ..schemas import SearchQuery, SearchResult
from .lexical import LexicalRetriever
from .metadata import metadata, validate_query
from .ranking import candidate_ranks, reciprocal_rank_score


class SearchEngine:
    def __init__(self, objects):
        self.objects = objects
        self.lexical = LexicalRetriever(objects)

    def search(self, query: SearchQuery, policy='soft', window=2, k=5, min_score=0.0,
               visual_scores=None, mode='text') -> SearchResult:
        query = validate_query(query)
        if policy not in ('soft', 'strict') or mode not in ('text', 'visual', 'hybrid'):
            raise ValueError('Política o modalidad desconocida')
        if not 0 <= window <= 365 or not 1 <= k <= 100:
            raise ValueError('Ventana o número de resultados fuera de rango')
        if not math.isfinite(min_score) or not -1 <= min_score <= 1:
            raise ValueError('Umbral fuera de rango')
        if mode != 'text' and visual_scores is None:
            raise ValueError('La modalidad visual requiere un índice de imágenes')
        lexical = self.lexical.scores(query['description'])
        visual_scores = visual_scores or {}
        eligible, excluded = [], []
        for obj in self.objects:
            meta = metadata(obj, query, window)
            if policy == 'strict' and meta['excluded_reasons']:
                excluded.append({'id': obj['id'], 'reasons': meta['excluded_reasons']})
            else:
                eligible.append((obj, meta))
        text_rank, visual_rank = candidate_ranks(eligible, lexical, visual_scores)
        results = []
        for obj, meta in eligible:
            oid = obj['id']
            raw_visual = visual_scores.get(oid)
            if mode == 'text':
                content = lexical[oid]
                if content <= 0:
                    continue  # Location alone is not enough to propose an object.
            elif mode == 'visual':
                if raw_visual is None:
                    continue
                content = raw_visual
            else:
                ranks = [r[oid] for r in (text_rank, visual_rank) if oid in r]
                if not ranks:
                    continue
                content = reciprocal_rank_score(ranks)
            if content < min_score:
                continue
            results.append({'id': oid, 'description': obj['description'],
                            'found_date': obj.get('found_date'), 'found_line': obj.get('found_line'),
                            'score': content + meta['bonus'], 'content_score': content,
                            'text_score': lexical[oid], 'visual_score': raw_visual,
                            'metadata': meta})
        results.sort(key=lambda row: (-row['score'], row['id']))
        return {'results': results[:k], 'eligible_ids': [o['id'] for o, _ in eligible],
                'excluded': excluded, 'policy': policy, 'mode': mode,
                'notice': 'Puntuaciones experimentales; no acreditan propiedad.'}
