"""Contrato inicial entre backend y búsqueda; fechas de hallazgo, no de recepción."""
from dataclasses import dataclass
from datetime import date
from typing import Literal


def _validate_date(value):
    if value is not None and type(value) is not date:
        raise ValueError('Utiliza datetime.date o None para las fechas')


@dataclass(frozen=True)
class FoundObject:
    id: str
    description: str
    found_date: date | None = None
    found_line: str | None = None
    found_direction: str | None = None
    date_quality: Literal['unknown', 'approximate', 'confirmed'] = 'unknown'

    def __post_init__(self):
        if not isinstance(self.id, str) or not self.id.strip():
            raise ValueError('Cada objeto necesita un ID')
        if not isinstance(self.description, str):
            raise ValueError('La descripción debe ser texto; puede estar vacía si se desconoce')
        _validate_date(self.found_date)
        if self.date_quality not in ('unknown', 'approximate', 'confirmed'):
            raise ValueError('Precisión de fecha desconocida')
        if (self.found_date is None) != (self.date_quality == 'unknown'):
            raise ValueError('Usa fecha None con unknown, o una fecha con approximate/confirmed')
        for value in (self.found_line, self.found_direction):
            if value is not None and (not isinstance(value, str) or not value.strip()):
                raise ValueError('Línea y sentido deben ser texto no vacío o None')


@dataclass(frozen=True)
class SearchQuery:
    description: str
    lost_date: date | None = None
    line: str | None = None
    direction: str | None = None
    date_approximate: bool = False

    def __post_init__(self):
        if not isinstance(self.description, str) or not 1 <= len(self.description.strip()) <= 2000:
            raise ValueError('La descripción debe contener entre 1 y 2000 caracteres')
        _validate_date(self.lost_date)
        if type(self.date_approximate) is not bool:
            raise ValueError('date_approximate debe ser booleano')
        for value in (self.line, self.direction):
            if value is not None and (not isinstance(value, str) or not value.strip()):
                raise ValueError('Línea y sentido deben ser texto no vacío o None')


@dataclass(frozen=True)
class Candidate:
    object_id: str
    text_score: float
    metadata_score: float
    signals: tuple[str, ...]


@dataclass(frozen=True)
class SearchResult:
    candidates: tuple[Candidate, ...]
    eligible_ids: tuple[str, ...]
    excluded_ids: tuple[str, ...]
