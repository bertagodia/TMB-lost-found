"""Referencia textual BM25 con metadatos secundarios y filtrado experimental."""
from collections import Counter
import math
import re
import unicodedata
from typing import Iterable

from .models import Candidate, FoundObject, SearchQuery, SearchResult

STOPWORDS = frozenset('a al con de del el en la las los mi para por un una y'.split())


def normalize(text):
    return ''.join(char for char in unicodedata.normalize('NFKD', text.casefold())
                   if not unicodedata.combining(char)).strip()


def tokenize(text):
    return [word for word in re.findall(r'\w+', normalize(text)) if word not in STOPWORDS]


class SearchEngine:
    """Instantánea del inventario. Reconstruir cuando cambien sus objetos."""

    def __init__(self, objects: Iterable[FoundObject]):
        self.objects = tuple(objects)
        ids = [obj.id for obj in self.objects]
        if len(ids) != len(set(ids)):
            raise ValueError('IDs duplicados: un objeto físico debe tener un solo registro')
        self.documents = tuple(Counter(tokenize(obj.description)) for obj in self.objects)
        self.frequencies = Counter(term for document in self.documents for term in document)
        self.average_length = sum(sum(doc.values()) for doc in self.documents) / max(1, len(self.documents))

    def _text_score(self, terms, document):
        score = 0.0
        length = sum(document.values())
        for term in terms:
            frequency = document[term]
            if not frequency:
                continue
            idf = math.log(1 + (len(self.documents) - self.frequencies[term] + 0.5)
                           / (self.frequencies[term] + 0.5))
            score += idf * frequency * 2.5 / (
                frequency + 1.5 * (0.25 + 0.75 * length / max(1, self.average_length)))
        return score

    def search(self, query: SearchQuery, *, policy='soft', window_days=2,
               limit=5, min_text_score=0.0) -> SearchResult:
        if policy not in ('soft', 'strict', 'ranked'):
            raise ValueError('policy debe ser soft o strict')
        if type(window_days) is not int or not 0 <= window_days <= 365:
            raise ValueError('window_days debe ser un entero entre 0 y 365')
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError('limit debe ser un entero entre 1 y 100')
        if not math.isfinite(min_text_score) or min_text_score < 0:
            raise ValueError('min_text_score debe ser finito y no negativo')
        terms = set(tokenize(query.description))
        candidates, eligible, excluded = [], [], []
        for obj, document in zip(self.objects, self.documents):
            delta = (obj.found_date - query.lost_date).days if obj.found_date and query.lost_date else None
            line_match = (normalize(obj.found_line) == normalize(query.line)
                          if obj.found_line and query.line else None)
            if policy == 'strict' and (line_match is False or (delta is not None and abs(delta) > window_days)):
                excluded.append(obj.id)
                continue
            eligible.append(obj.id)
            score = self._text_score(terms, document)
            if score <= 0 or score < min_text_score:
                continue
            signals = []
            metadata_score = 0.0
            if line_match:
                metadata_score += 1
                signals.append('Línea coincidente')
            if delta is not None:
                precision = 0.5 if query.date_approximate or obj.date_quality == 'approximate' else 1
                metadata_score += precision / (1 + abs(delta))
                signals.append(f'Hallazgo respecto a pérdida: {delta:+d} días')
            if obj.found_direction and query.direction and normalize(obj.found_direction) == normalize(query.direction):
                metadata_score += 0.25
                signals.append('Sentido coincidente')
            rank_score = score
            if policy == 'ranked':
                # Bound lexical relevance so metadata can meaningfully rerank matches.
                # No metadata can create a candidate without positive text overlap.
                metadata_score = 0.0
                if query.transport and obj.found_transport:
                    metadata_score += 0.15 if query.transport == obj.found_transport else -0.15
                    if query.transport != obj.found_transport:
                        line_match = False if query.line and obj.found_line else None
                if query.line:
                    metadata_score += 0.9 if line_match else (-0.2 if line_match is False else 0)
                    if line_match is None:
                        signals.append('Línea de hallazgo desconocida')
                    elif line_match is False:
                        signals.append('Otra línea de hallazgo')
                if delta is not None:
                    precision = 0.5 if query.date_approximate or obj.date_quality == 'approximate' else 1.0
                    # Objects can be found days after loss; earlier confirmed finds are less plausible.
                    metadata_score += precision * (0.5 / (1 + delta / 7) if delta >= 0 else -0.5)
                elif query.lost_date:
                    signals.append('Fecha de hallazgo desconocida')
                if query.colors and obj.colors:
                    wanted = {normalize(c) for c in query.colors}
                    weights = [(1 / (i + 1) if obj.color_order_known else 1) for i in range(len(obj.colors))]
                    overlap = sum(w for c,w in zip(obj.colors,weights) if normalize(c) in wanted) / sum(weights)
                    metadata_score += 0.45 * overlap
                    if overlap:
                        signals.append('Coincidencia de color' + (' principal' if obj.color_order_known and normalize(obj.colors[0]) in wanted else ' secundario' if obj.color_order_known else ''))
                rank_score = score / (1 + score) + metadata_score
            candidates.append(Candidate(obj.id, score, metadata_score, tuple(signals), rank_score))
        # Metadata breaks lexical ties; provisional weights never override text relevance.
        candidates.sort(key=lambda item: (-item.rank_score, -item.metadata_score, item.object_id))
        return SearchResult(tuple(candidates[:limit]), tuple(eligible), tuple(excluded))
