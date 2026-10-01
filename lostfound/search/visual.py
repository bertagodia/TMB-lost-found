"""Similitud visual y agregación de fotos por identidad del objeto."""
from ..imaging.encoder import ImageTextEncoder
from ..indexing.store import index_signature


def dot(left, right):
    if len(left) != len(right):
        raise ValueError('Dimensiones de embeddings incompatibles')
    return sum(a * b for a, b in zip(left, right))


def visual_scores(index, text, encoder: ImageTextEncoder, query_image=None):
    if index['signature'] != index_signature(encoder):
        raise ValueError('El índice y el codificador no son compatibles; reindexa')
    vectors = []
    if text:
        vectors.append(encoder.text(text))
    if query_image:
        vectors.append(encoder.image(query_image)[0])
    if not vectors:
        raise ValueError('Falta texto o imagen de consulta')
    scores = {}
    for row in index['images']:
        # Equal weights are an experimental baseline, not a validated fusion.
        score = sum(dot(v, row['vector']) for v in vectors) / len(vectors)
        oid = row['object_id']
        scores[oid] = max(scores.get(oid, -float('inf')), score)
    return scores
