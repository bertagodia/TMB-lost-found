"""Lectura y validación de inventarios JSON."""
from datetime import date
import json
from pathlib import Path

from ..config import DEMO_OBJECTS
from ..schemas import ObjectRecord


def load_objects(path=DEMO_OBJECTS) -> list[ObjectRecord]:
    objects = json.loads(Path(path).read_text())
    ids = [o['id'] for o in objects]
    if len(ids) != len(set(ids)):
        raise ValueError('Identificadores de objeto duplicados')
    for obj in objects:
        for key in ('found_date', 'received_date'):
            if obj.get(key):
                date.fromisoformat(obj[key])
        if not isinstance(obj.get('description'), str):
            raise ValueError('Cada objeto necesita una descripción textual')
    return objects
