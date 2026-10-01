"""Métricas sobre candidatos, no adjudicaciones."""


def retrieval_metrics(relevant, returned, eligible, k):
    hits = len(returned & relevant)
    return {
        "filter_recall": len(eligible & relevant) / len(relevant) if relevant else None,
        "recall_at_k": hits / len(relevant) if relevant else None,
        "precision_at_k": hits / k,
        "false_positive_candidates": len(returned - relevant),
        "false_negatives_at_k": len(relevant - returned),
        "no_match_false_alarm": bool(returned) if not relevant else None,
    }


def mean_available(rows, key):
    values = [row[key] for row in rows if row[key] is not None]
    return sum(values) / len(values) if values else None
