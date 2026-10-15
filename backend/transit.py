"""Shared catalogue validation for confirmed finding metadata and citizen queries."""
from datetime import date
import json
from pathlib import Path
import re

CATALOGUE = json.loads((Path(__file__).resolve().parents[1]/'client/transit-options.json').read_text(encoding='utf-8'))


def transit(mode=None, line=None):
    mode = mode or None
    line = line or None
    if mode is not None and mode not in CATALOGUE['modes']:
        raise ValueError('Selecciona Bus, Metro o desconegut.')
    if line is not None:
        if not isinstance(line, str) or not mode:
            raise ValueError('Selecciona el transport abans de la línia.')
        line = re.sub(r'\s+', '', line).upper()
        if line not in {item['id'] for item in CATALOGUE['modes'][mode]}:
            raise ValueError('La línia no correspon al transport seleccionat.')
    return mode, line


def calendar_date(value):
    if not value:
        return None
    if not isinstance(value, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
        raise ValueError('Data invàlida: utilitza AAAA-MM-DD a l’API.')
    parsed = date.fromisoformat(value)
    if parsed > date.today():
        raise ValueError('La data no pot ser futura.')
    return parsed


def finding(value):
    if not isinstance(value, dict):
        raise ValueError('Dades de la troballa invàlides.')
    mode, line = transit(value.get('transport'), value.get('line'))
    day = calendar_date(value.get('date'))
    quality = value.get('dateQuality') or ('confirmed' if day else 'unknown')
    if quality not in ('confirmed','approximate','unknown') or ((day is None) != (quality == 'unknown')):
        raise ValueError('Revisa la data i la seva precisió.')
    return dict(found_transport=mode, found_line=line, found_date=day, date_quality=quality)
