"""FastAPI contracts adapted from PR #7 to the current browser payloads.

Use exclude_unset when handing payloads to services: adding omitted defaults
would change hashes of requests already queued or committed by older versions.
"""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, StrictBool


class Input(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)


class PhotoInput(Input):
    data: str
    name: str | None = None
    capturedAt: str | None = None
    mimeType: str | None = None


class Details(Input):
    colors: list[str] | None = None
    color: str | None = None  # Original single-color offline queues.
    colorOrderKnown: StrictBool = False
    objectType: str | None = None
    material: str | None = None
    description: str = ''


class Vehicle(Input):
    line: str | None = None
    vehicle: str | None = None
    transport: str | None = None
    source: Literal['manual','nfc'] | None = None


class Origin(Input):
    kind: Literal['station','depot']
    location: str
    destination: str | None = None  # Two-field legacy requests remain supported.


class Finding(Input):
    transport: str | None = None
    line: str | None = None
    date: str | None = None
    dateQuality: Literal['unknown','approximate','confirmed'] | None = None


class ObjectCreate(Input):
    id: str = Field(min_length=1,max_length=160)
    photos: list[PhotoInput | str] = Field(min_length=1,max_length=2)
    details: Details
    reviewed: StrictBool
    vehicle: Vehicle | None = None
    origin: Origin | None = None
    finding: Finding | None = None
    capturedAt: str | None = None
    extractionId: str | None = None
    status: str | None = None


class Filters(Input):
    objectType: str | None = None
    colors: list[str] = Field(default_factory=list)


class SearchCreate(Input):
    description: str = Field(min_length=1,max_length=500)
    filters: Filters | None = None
    lostDate: str | None = None
    transport: str | None = None
    line: str | None = None
    dateApproximate: StrictBool = False


class Incident(Input):
    location: str | None = None
    lossDate: str | None = None
    transport: str | None = None
    line: str | None = None
    dateApproximate: StrictBool = False


class Contact(Input):
    name: str | None = Field(default=None,max_length=120)
    email: str | None = Field(default=None,max_length=254)
    phone: str | None = Field(default=None,max_length=40)


class ReportCreate(Input):
    id: str = Field(min_length=1,max_length=160)
    description: str = Field(min_length=1,max_length=500)
    createdAt: str | None = None
    status: str | None = None
    incident: Incident | None = None
    filters: Filters | None = None
    referencePhoto: PhotoInput | str | None = None
    contact: Contact | None = None


class ReviewCreate(Input):
    id: str
    revision: int = Field(ge=1)
    reviewed: StrictBool
    status: Literal['approved','rejected'] = 'approved'
    details: Details
    finding: Finding | None = None


class StatusChange(Input):
    id: str
    status: Literal['registered','returned','archived']


class MatchCreate(Input):
    action: Literal['list','link','unlink','location','return','reopen'] = 'list'
    recordId: str | None = None
    reportId: str | None = None
    revision: int | None = Field(default=None,ge=1)
    foundLocation: str | None = None
    destination: str | None = None


class ExtractCreate(Input):
    photo: PhotoInput | str


class Receipt(BaseModel):
    id: str
    status: str
    queued: bool = False
    duplicate: bool = False


class ErrorView(BaseModel):
    error: str
    code: str
    details: list[dict] | None = None


class HealthView(BaseModel):
    status: Literal['ready']
    model: str
    storage: Literal['postgres','json']
