"""Application services: validated forms, local files and PostgreSQL transactions."""
import base64
import binascii
import hashlib
import json
import logging
from pathlib import Path
import tempfile
import threading
from uuid import uuid4

from PIL import Image
import psycopg

from database.repository import Repository
from search.extraction import MAX_BYTES, PREPROCESS_VERSION, ExtractionError, _prepare_image
from search.form_extraction import FORM_PROMPT_VERSION, extract_form
from search.pipeline import model_digest
from search.settings import DEFAULT_MODEL

from .models import ObjectCreate, PhotoInput, ReportCreate

logger = logging.getLogger(__name__)


class APIError(Exception):
    def __init__(self, status, message, code):
        self.status, self.message, self.code = status, message, code


def decode_image(photo):
    if isinstance(photo, PhotoInput):
        data = photo.data
    else:
        data = photo.get('data') if isinstance(photo, dict) else photo
    if not isinstance(data, str) or ',' not in data:
        raise ValueError('La fotografia ha de ser una data URL.')
    prefix, encoded = data.split(',', 1)
    if prefix not in {'data:image/jpeg;base64', 'data:image/png;base64', 'data:image/webp;base64'}:
        raise ValueError('Utilitza JPEG, PNG o WebP.')
    if len(encoded) > 28 * 1024 * 1024:
        raise APIError(413, 'La fotografia supera 20 MiB.', 'image_too_large')
    try:
        raw = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError('Fotografia invàlida.') from exc
    if not raw or len(raw) > MAX_BYTES:
        raise ValueError('La fotografia ha de tenir entre 1 byte i 20 MiB.')
    return raw


def optional_text(value):
    return None if value in (None, '', '—') else value


def extraction_view(row, *, cached=False):
    result = row['raw_output'] or {}
    return dict(id=row['id'], photo_id=row['photo_id'], status=row['status'], cached=cached,
        fields=row['proposed_fields'], recognized_object=result.get('recognized_object'),
        quality=row['quality'], sensitive_content=row['sensitive_content'], warnings=row['warnings'],
        timings=row['timings'], review_status='pending', model=row['model_name'],
        model_digest=row['model_digest'], prompt_version=row['prompt_version'],
        preprocessing_version=row['preprocessing_version'], image_sha256=row['input_image_sha256'],
        created_at=row['created_at'], completed_at=row['completed_at'], error_message=row['error_message'])


class Application:
    def __init__(self, data_dir, model=DEFAULT_MODEL, *, repository: Repository):
        self.data_dir = Path(data_dir).resolve()
        self.model = model
        self.repo = repository
        self.extraction_lock = threading.Lock()

    def store_photo(self, photo, position):
        raw = decode_image(photo)
        with tempfile.TemporaryDirectory() as folder:
            temporary = Path(folder) / 'image'
            temporary.write_bytes(raw)
            _prepare_image(temporary)
            with Image.open(temporary) as image:
                media_type, suffix = {'JPEG': ('image/jpeg', '.jpg'), 'MPO': ('image/jpeg', '.jpg'),
                    'PNG': ('image/png', '.png'), 'WEBP': ('image/webp', '.webp')}[image.format]
                width, height = image.size
        key = 'photos/' + uuid4().hex + suffix
        target = self.data_dir / key
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            with target.open('xb') as handle:
                handle.write(raw)
            return self.repo.create_photo(storage_key=key, image_sha256=hashlib.sha256(raw).hexdigest(),
                media_type=media_type, size_bytes=len(raw), width=width, height=height, position=position,
                original_filename=photo.name if isinstance(photo, PhotoInput) else None,
                client_selected_at=photo.capturedAt if isinstance(photo, PhotoInput) else None)
        except Exception:
            target.unlink(missing_ok=True)
            raise

    def cleanup(self, photos):
        for photo in photos:
            try:
                removed = self.repo.discard_photo(photo['id'])
                if removed:
                    (self.data_dir / removed['storage_key']).unlink(missing_ok=True)
            except (psycopg.Error, OSError):
                # Never delete a possibly committed attachment after a connection loss.
                logger.error('Could not clean staged photo %s', photo['id'])

    def extract(self, payload):
        if not self.extraction_lock.acquire(blocking=False):
            raise APIError(409, 'Hi ha una extracció en curs. Torna-ho a provar.', 'extraction_busy')
        photo = None
        run = None
        try:
            value = payload.photo if hasattr(payload, 'photo') else payload['photo']
            if isinstance(value, dict):
                value = PhotoInput.model_validate(value)
            photo = self.store_photo(value, 1)
            # The model lookup is not inference; record a failed attempt if it is unavailable.
            try:
                digest = model_digest(self.model)
            except (RuntimeError, OSError, ValueError) as exc:
                run = self.repo.start_extraction(photo['id'], model_name=self.model,
                    prompt_version=FORM_PROMPT_VERSION, preprocessing_version=PREPROCESS_VERSION)
                self.repo.fail_extraction(run['id'], 'Ollama model unavailable')
                raise APIError(502, 'Ollama no està disponible. Pots completar els camps manualment.', 'ollama_unavailable') from exc
            key = hashlib.sha256(json.dumps([photo['image_sha256'], digest,
                FORM_PROMPT_VERSION, PREPROCESS_VERSION]).encode()).hexdigest()
            run = self.repo.start_extraction(photo['id'], model_name=self.model, model_digest=digest,
                prompt_version=FORM_PROMPT_VERSION, preprocessing_version=PREPROCESS_VERSION, cache_key=key)
            try:
                previous = self.repo.cached_extraction(key)
                result = previous['raw_output'] if previous else extract_form(self.data_dir / photo['storage_key'], model=self.model)
                if model_digest(self.model) != digest:
                    raise ExtractionError('Model changed during extraction')
                completed = self.repo.complete_extraction(run['id'], raw_output=result,
                    proposed_fields=result['fields'], quality=result['quality'],
                    sensitive_content=result['sensitive_content'], warnings=result.get('warnings'),
                    timings=result.get('timings'))
                return extraction_view(completed, cached=previous is not None)
            except (RuntimeError, OSError, ValueError) as exc:
                timeout = isinstance(exc, TimeoutError) or 'timed out' in str(exc).lower()
                self.repo.fail_extraction(run['id'], 'Ollama timeout' if timeout else 'Ollama extraction failed')
                raise APIError(504 if timeout else 502, 'No s’ha pogut extreure. Pots completar els camps manualment.',
                               'ollama_timeout' if timeout else 'extraction_failed') from exc
        finally:
            if photo and run is None:
                self.cleanup([photo])
            self.extraction_lock.release()

    def submit(self, payload):
        record = payload if isinstance(payload, ObjectCreate) else ObjectCreate.model_validate(payload)
        new_photos = []
        photos = []
        try:
            for index, incoming in enumerate(record.photos, 1):
                if index == 1 and record.extractionId:
                    run = self.repo.get_extraction(record.extractionId)
                    if run is None or run['status'] != 'succeeded':
                        raise ValueError('Referència d’extracció invàlida o incompleta.')
                    photo = self.repo.get_photo(run['photo_id'])
                    if photo['image_sha256'] != hashlib.sha256(decode_image(incoming)).hexdigest():
                        raise ValueError('L’extracció no correspon a la fotografia principal.')
                else:
                    photo = self.store_photo(incoming, index)
                    new_photos.append(photo)
                photos.append(photo)
            vehicle = record.vehicle
            row = self.repo.register_object(record.id, photo_ids=[p['id'] for p in photos],
                details=record.details.model_dump(mode='json'), reviewed=record.reviewed,
                extraction_id=record.extractionId, client_registered_at=record.capturedAt,
                registered_line=optional_text(vehicle.line) if vehicle else None,
                registered_vehicle=optional_text(vehicle.vehicle) if vehicle else None,
                vehicle_source=vehicle.source if vehicle else None,
                **record.model_dump(include={'found_date','date_quality','found_line','found_direction','found_location','received_at'}))
            return dict(id=row['id'], status=row['status'], queued=False, duplicate=row['duplicate'])
        finally:
            self.cleanup(new_photos)

    def submit_report(self, payload):
        report = payload if isinstance(payload, ReportCreate) else ReportCreate.model_validate(payload)
        new_photos = []
        try:
            if report.referencePhoto is not None:
                new_photos.append(self.store_photo(report.referencePhoto, 1))
            contact = report.contact.model_dump() if report.contact else {}
            contact = contact if any(contact.values()) else {}
            filters = report.filters.model_dump(mode='json')
            data = dict(client_created_at=report.createdAt, original_description=report.description,
                lost_date=report.incident.lossDate, date_approximate=report.incident.dateApproximate,
                location_text=optional_text(report.incident.location), line=optional_text(report.incident.line),
                direction=optional_text(report.incident.direction), object_type=filters['objectType'], colors=filters['colors'])
            row = self.repo.register_report(report.id, data=data, contact=contact,
                photo_ids=[p['id'] for p in new_photos])
            return dict(id=row['id'], status=row['status'], queued=False, duplicate=row['duplicate'])
        finally:
            self.cleanup(new_photos)

    def photo_content(self, photo_id):
        photo = self.repo.get_photo(photo_id)
        if photo is None:
            raise KeyError(photo_id)
        target = (self.data_dir / photo['storage_key']).resolve()
        if not target.is_relative_to(self.data_dir) or not target.is_file():
            raise KeyError(photo_id)
        return target, photo['media_type']
