"""HTTP contracts. Transport fields remain compatible with the existing forms."""
from datetime import date, datetime
from typing import Generic, Literal, TypeVar

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StrictBool, field_validator, model_validator

from search.form_extraction import FormFields, Color, ObjectType

ObjectStatus = Literal['registered', 'returned', 'archived']
ReportStatus = Literal['open', 'closed', 'cancelled']


class Input(BaseModel):
    model_config = ConfigDict(extra='forbid')


class Details(FormFields):
    # FastAPI validates Python dictionaries, whereas FormFields uses strict JSON.
    model_config = ConfigDict(extra='forbid', strict=False)

    @model_validator(mode='before')
    @classmethod
    def legacy_color(cls, value):
        if isinstance(value, dict) and 'color' in value:
            value = dict(value)
            color = value.pop('color')
            value.setdefault('colors', [color] if color else [])
        return value


class PhotoInput(Input):
    data: str
    name: str | None = Field(default=None, max_length=255)
    capturedAt: AwareDatetime | None = None
    mimeType: str | None = None  # Informational; the backend verifies the bytes.


Photo = PhotoInput | str


class Vehicle(Input):
    line: str | None = None
    vehicle: str | None = None
    source: Literal['manual', 'nfc'] | None = None


class IdentifiedInput(Input):
    id: str = Field(min_length=1, max_length=160)

    @field_validator('id')
    @classmethod
    def nonblank_id(cls, value):
        if not value.strip():
            raise ValueError('ID cannot be blank')
        return value


class ObjectCreate(IdentifiedInput):
    details: Details
    photos: list[Photo] = Field(min_length=1, max_length=2)
    reviewed: StrictBool
    vehicle: Vehicle | None = None
    capturedAt: AwareDatetime | None = None
    extractionId: str | None = Field(default=None, min_length=1, max_length=160)
    status: str | None = None  # Browser transport status, never the inventory status.
    found_date: date | None = None
    date_quality: Literal['unknown', 'approximate', 'confirmed'] = 'unknown'
    found_line: str | None = None
    found_direction: str | None = None
    found_location: str | None = None
    received_at: AwareDatetime | None = None

    @model_validator(mode='after')
    def reviewed_and_consistent(self):
        if not self.reviewed:
            raise ValueError('Confirma la revisió dels camps abans de desar.')
        if not self.details.colors or self.details.objectType is None or self.details.material is None:
            raise ValueError('Revisa colors, tipus i material abans de desar.')
        if (self.found_date is None) != (self.date_quality == 'unknown'):
            raise ValueError('Unknown finding dates require date_quality=unknown')
        for value in (self.found_line, self.found_direction):
            if value is not None and not value.strip():
                raise ValueError('Use null for unknown finding context')
        return self


class Incident(Input):
    location: str | None = Field(default=None, max_length=100)
    lossDate: date | None = None
    dateApproximate: StrictBool = False
    line: str | None = None
    direction: str | None = None

    @field_validator('lossDate', mode='before')
    @classmethod
    def empty_date(cls, value):
        return None if value == '' else value


class Filters(Input):
    objectType: ObjectType | None = None
    colors: list[Color] = Field(default_factory=list)

    @field_validator('objectType', mode='before')
    @classmethod
    def empty_type(cls, value):
        return None if value == '' else value

    @field_validator('colors')
    @classmethod
    def unique_colors(cls, values):
        return list(dict.fromkeys(values))


class Contact(Input):
    name: str | None = Field(default=None, max_length=120)
    email: str | None = Field(default=None, max_length=254)
    phone: str | None = Field(default=None, max_length=40)

    @field_validator('name', 'email', 'phone', mode='before')
    @classmethod
    def optional_text(cls, value):
        return value.strip() or None if isinstance(value, str) else value

    @field_validator('email')
    @classmethod
    def email_format(cls, value):
        if value is not None and (value.count('@') != 1 or any(c.isspace() for c in value)
                                  or not all(value.split('@'))):
            raise ValueError('Invalid email address')
        return value


class ReportCreate(IdentifiedInput):
    description: str = Field(min_length=1, max_length=500)
    createdAt: AwareDatetime | None = None
    status: str | None = None
    incident: Incident = Field(default_factory=Incident)
    filters: Filters = Field(default_factory=Filters)
    referencePhoto: Photo | None = None
    contact: Contact | None = None

    @field_validator('description')
    @classmethod
    def nonblank_description(cls, value):
        if not value.strip():
            raise ValueError('Description cannot be blank')
        return value


class ReviewCreate(Input):
    details: Details
    status: Literal['approved', 'rejected'] = 'approved'
    extraction_id: str | None = None
    reviewer_ref: str | None = None
    review_seconds: float | None = Field(default=None, ge=0, allow_inf_nan=False)


class ObjectStatusChange(Input):
    status: ObjectStatus


class ReportStatusChange(Input):
    status: ReportStatus


class ExtractCreate(Input):
    photo: Photo


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
    database: Literal['ready']
    model: str


class PhotoView(BaseModel):
    id: str
    position: int
    media_type: str
    image_sha256: str
    size_bytes: int
    width: int
    height: int
    created_at: datetime
    client_selected_at: datetime | None


class ReviewView(BaseModel):
    id: str
    object_id: str
    revision: int
    status: str
    source: str
    extraction_id: str | None
    object_type: str | None
    material: str | None
    colors: list[str]
    description: str
    search_text: str
    reviewed_at: datetime
    reviewer_ref: str | None
    review_seconds: float | None


class ObjectView(BaseModel):
    id: str
    status: ObjectStatus
    created_at: datetime
    updated_at: datetime
    client_registered_at: datetime | None
    registered_line: str | None
    registered_vehicle: str | None
    vehicle_source: str | None
    found_date: date | None
    date_quality: str
    found_line: str | None
    found_direction: str | None
    found_location: str | None
    received_at: datetime | None
    original_details: dict
    photos: list[PhotoView] = Field(default_factory=list)
    reviews: list[ReviewView] = Field(default_factory=list)


class ReportView(BaseModel):
    id: str
    status: ReportStatus
    created_at: datetime
    updated_at: datetime
    client_created_at: datetime | None
    original_description: str
    lost_date: date | None
    date_approximate: bool
    location_text: str | None
    line: str | None
    direction: str | None
    object_type: str | None
    colors: list[str]
    photos: list[PhotoView] = Field(default_factory=list)


class ContactView(Contact):
    report_id: str
    created_at: datetime
    updated_at: datetime


T = TypeVar('T')


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    limit: int
    offset: int


class ExtractionView(BaseModel):
    id: str
    photo_id: str
    status: str
    cached: bool = False
    fields: Details | None = None
    recognized_object: str | None = None
    quality: str | None = None
    sensitive_content: bool | None = None
    warnings: list = Field(default_factory=list)
    timings: dict = Field(default_factory=dict)
    review_status: str = 'pending'
    model: str | None = None
    model_digest: str | None = None
    prompt_version: str | None = None
    preprocessing_version: str | None = None
    image_sha256: str
    created_at: datetime
    completed_at: datetime | None
    error_message: str | None = None
