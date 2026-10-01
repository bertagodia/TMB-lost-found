"""Contratos JSON compartidos. TypedDict documenta tipos; no valida en ejecución."""
from typing import Literal, NotRequired, TypedDict


class ObjectRecord(TypedDict):
    id: str
    description: str
    found_date: NotRequired[str | None]
    found_date_quality: NotRequired[Literal['confirmed', 'approximate', 'unknown']]
    received_date: NotRequired[str | None]
    found_line: NotRequired[str | None]
    found_direction: NotRequired[str | None]
    images: NotRequired[list[str]]
    synthetic: NotRequired[bool]


class SearchQuery(TypedDict):
    description: str
    date: NotRequired[str]
    date_approximate: NotRequired[bool]
    line: NotRequired[str]
    direction: NotRequired[str]


class MetadataSignals(TypedDict):
    day_delta: int | None
    line_match: bool | None
    direction_match: bool | None
    excluded_reasons: list[str]
    bonus: float


class Candidate(TypedDict):
    id: str
    description: str
    found_date: str | None
    found_line: str | None
    score: float
    content_score: float
    text_score: float
    visual_score: float | None
    metadata: MetadataSignals


class ExcludedObject(TypedDict):
    id: str
    reasons: list[str]


class SearchResult(TypedDict):
    results: list[Candidate]
    eligible_ids: list[str]
    excluded: list[ExcludedObject]
    policy: str
    mode: str
    notice: str


class ImageQuality(TypedDict):
    width: NotRequired[int]
    height: NotRequired[int]
    warnings: list[str]


class ImageEmbedding(TypedDict):
    object_id: str
    path: str
    sha256: str
    vector: list[float]
    quality: ImageQuality
