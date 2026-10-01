"""Fusión de rankings; puntuaciones experimentales no calibradas."""


def candidate_ranks(eligible, lexical, visual_scores):
    # Reciprocal-rank fusion avoids treating cosine and BM25 as calibrated probabilities.
    text_order = sorted(eligible, key=lambda x: (-lexical[x[0]['id']], x[0]['id']))
    text_rank = {o['id']: i + 1 for i, (o, _) in enumerate(text_order) if lexical[o['id']] > 0}
    visual_order = sorted((x for x in eligible if x[0]['id'] in visual_scores),
                          key=lambda x: (-visual_scores[x[0]['id']], x[0]['id']))
    visual_rank = {o['id']: i + 1 for i, (o, _) in enumerate(visual_order)}
    return text_rank, visual_rank


def reciprocal_rank_score(ranks):
    return sum(1 / (60 + rank) for rank in ranks) * 61 / 2
