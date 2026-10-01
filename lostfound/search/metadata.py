"""Validación de consulta y señales de fecha y ubicación."""
from datetime import date

from .lexical import tokens


def validate_query(query):
    description = query.get('description', '').strip()
    if not description or len(description) > 2000:
        raise ValueError('Introduce una descripción de entre 1 y 2000 caracteres')
    result = {key: str(query.get(key, '')).strip()
              for key in ('description', 'date', 'line', 'direction')}
    if result['date']:
        date.fromisoformat(result['date'])
    if len(result['line']) > 20 or len(result['direction']) > 100:
        raise ValueError('Línea o sentido demasiado largos')
    result['date_approximate'] = query.get('date_approximate') in (True, 'true', 'on')
    return result


def metadata(obj, query, window):
    # A reception date is NEVER substituted for the unknown finding date.
    delta = None
    if obj.get('found_date') and query['date']:
        delta = (date.fromisoformat(obj['found_date']) - date.fromisoformat(query['date'])).days
    line_match = None
    if query['line'] and obj.get('found_line'):
        line_match = query['line'].casefold() == obj['found_line'].casefold()
    direction_match = None
    if query['direction'] and obj.get('found_direction'):
        direction_match = tokens(query['direction']) == tokens(obj['found_direction'])
    excluded = []
    if delta is not None and abs(delta) > window:
        excluded.append('fuera de la ventana temporal')
    if line_match is False:
        excluded.append('línea distinta')
    # Experimental, explicitly uncalibrated ranking bonus. Unknowns are neutral.
    temporal = 0 if delta is None else 1 / (1 + abs(delta))
    uncertain = query['date_approximate'] or obj.get('found_date_quality') != 'confirmed'
    bonus = (0.04 if uncertain else 0.08) * temporal
    bonus += 0.08 if line_match else 0
    bonus += 0.02 if direction_match else 0
    return {'day_delta': delta, 'line_match': line_match,
            'direction_match': direction_match, 'excluded_reasons': excluded,
            'bonus': bonus}
