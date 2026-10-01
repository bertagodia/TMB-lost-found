"""Estructura del informe de evaluación."""
from .metrics import mean_available


def build_report(rows, policy, window, k, min_score):
    return {'policy': policy, 'window': window, 'k': k, 'min_score': min_score,
            'dataset_note': 'Demo sintética de regresión; no estima rendimiento en TMB.',
            'definitions': {'precision_at_k': 'aciertos/k; posiciones vacías cuentan como cero',
                            'recall_at_k': 'media solo sobre consultas con correspondencia',
                            'filter_recall': 'supervivencia antes del ranking y del umbral'},
            'summary': {key: mean_available(rows, key) for key in ('filter_recall', 'recall_at_k',
                        'precision_at_k', 'no_match_false_alarm', 'latency_ms')}, 'queries': rows}
