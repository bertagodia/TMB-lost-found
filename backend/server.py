"""Local FastAPI server and Ollama adapter: python -m backend.server --port 8001."""
import argparse
import base64
import binascii
import hashlib
import json
from pathlib import Path
import tempfile
import threading

from search.extraction import MAX_BYTES, _prepare_image
from search.form_extraction import FormFields, FORM_PROMPT_VERSION, extract_form
from search.extraction import PREPROCESS_VERSION
from search.pipeline import model_digest
from search.settings import DEFAULT_MODEL
from search.storage import write_json

ROOT = Path(__file__).resolve().parent.parent

LOCATION_ASSIGNMENTS = json.loads((ROOT / 'client' / 'location-assignment-data.json').read_text(encoding='utf-8'))


def origin_metadata(record):
    if 'origin' not in record:
        return dict(origin_kind=None, origin_location=None, origin_destination=None)
    origin = record['origin']
    if not isinstance(origin, dict) or set(origin) != {'kind', 'location', 'destination'}:
        raise ValueError('Origen invàlid.')
    kind, location, destination = origin['kind'], origin['location'], origin['destination']
    if any(not isinstance(value, str) or not value.strip() for value in (kind, location, destination)):
        raise ValueError('Cal indicar l’origen i l’estació de destinació.')
    location, destination = location.strip(), destination.strip()
    if kind == 'station':
        assigned = next((central for central, stations in LOCATION_ASSIGNMENTS['stations'].items()
                         if location in stations), None)
    elif kind == 'depot':
        assigned = LOCATION_ASSIGNMENTS['depots'].get(location)
    else:
        raise ValueError('El tipus d’origen ha de ser estació o cotxera.')
    if assigned != destination:
        raise ValueError('L’estació de destinació no correspon a l’origen seleccionat.')
    return dict(origin_kind=kind, origin_location=location, origin_destination=destination)


def decode_image(photo):
    data = photo.get('data') if isinstance(photo, dict) else photo
    if not isinstance(data, str) or ',' not in data:
        raise ValueError('La fotografia ha de ser una data URL.')
    prefix, encoded = data.split(',', 1)
    if prefix not in {'data:image/jpeg;base64', 'data:image/png;base64', 'data:image/webp;base64'}:
        raise ValueError('Utilitza JPEG, PNG o WebP.')
    if len(encoded) > 28 * 1024 * 1024:
        raise ValueError('La fotografia supera 20 MiB.')
    try:
        raw = base64.b64decode(encoded, validate=True)
    except binascii.Error as exc:
        raise ValueError('Fotografia invàlida.') from exc
    if not raw or len(raw) > MAX_BYTES:
        raise ValueError('La fotografia ha de tenir entre 1 byte i 20 MiB.')
    return raw


class Application:
    def __init__(self, data_dir, model=DEFAULT_MODEL):
        self.data_dir = Path(data_dir)
        self.model = model
        self.extraction_lock = threading.Lock()
        self.save_lock = threading.Lock()

    def extract(self, payload):
        raw = decode_image(payload['photo'])
        # Serialize inference to avoid piling up CPU requests; allow saving concurrently.
        if not self.extraction_lock.acquire(blocking=False):
            raise BlockingIOError('Hi ha una extracció en curs. Torna-ho a provar quan acabi.')
        try:
            digest = model_digest(self.model)
            key = hashlib.sha256(json.dumps([hashlib.sha256(raw).hexdigest(), digest,
                                           FORM_PROMPT_VERSION, PREPROCESS_VERSION]).encode()).hexdigest()
            cache = self.data_dir / 'extractions' / (key + '.json')
            if cache.exists():
                return {**json.loads(cache.read_text(encoding='utf-8')), 'cached': True}
            with tempfile.TemporaryDirectory() as folder:
                image = Path(folder) / 'photo'
                image.write_bytes(raw)
                result = extract_form(image, model=self.model)
            if model_digest(self.model) != digest:
                raise ValueError('El model ha canviat durant l’extracció; torna-ho a provar.')
            result.update(id=key, model_digest=digest)
            write_json(cache, result)
            return {**result, 'cached': False}
        finally:
            self.extraction_lock.release()

    def submit(self, record):
        object_id = record.get('id')
        if not isinstance(object_id, str) or not object_id.strip() or len(object_id) > 160:
            raise ValueError('ID del registre invàlid.')
        if record.get('extractionId') and record.get('reviewed') is not True:
            raise ValueError('Confirma la revisió dels camps extrets abans de desar.')
        details = dict(record['details'])
        # Read legacy one-color queues without changing their IDs.
        if 'colors' not in details:
            details['colors'] = [details['color']] if details.get('color') else []
        details.pop('color', None)
        fields = FormFields.model_validate_json(json.dumps(details))
        if not fields.colors or fields.objectType is None or fields.material is None:
            raise ValueError('Revisa colors, tipus i material abans de desar.')
        photos = record['photos']
        if not isinstance(photos, list) or not 1 <= len(photos) <= 2:
            raise ValueError('El registre necessita una o dues fotografies.')
        with tempfile.TemporaryDirectory() as folder:
            for index, photo in enumerate(photos):
                image = Path(folder) / str(index)
                image.write_bytes(decode_image(photo))
                _prepare_image(image)
        normalized = {**record, 'details': fields.model_dump(mode='json'), 'status': 'received-local'}
        target = self.data_dir / 'records' / (hashlib.sha256(object_id.encode()).hexdigest() + '.json')
        with self.save_lock:
            if target.exists():
                if json.loads(target.read_text(encoding='utf-8')) != normalized:
                    raise FileExistsError('Aquest ID ja existeix amb dades diferents.')
                return {'id': object_id, 'queued': False, 'status': 'received-local', 'duplicate': True}
            extraction_id = record.get('extractionId')
            if extraction_id:
                if not isinstance(extraction_id, str) or len(extraction_id) != 64 or any(c not in '0123456789abcdef' for c in extraction_id):
                    raise ValueError('Referència d’extracció invàlida.')
                extraction_path = self.data_dir / 'extractions' / (extraction_id + '.json')
                extraction = json.loads(extraction_path.read_text(encoding='utf-8'))
                if extraction['image_sha256'] != hashlib.sha256(decode_image(photos[0])).hexdigest():
                    raise ValueError('L’extracció no correspon a la fotografia principal.')
            write_json(target, normalized)
        return {'id': object_id, 'queued': False, 'status': 'received-local'}


# Transport is defined separately so the existing services and cache format remain stable.
def create_app(**kwargs):
    from .api import create_app as factory
    return factory(**kwargs)


def main():
    import uvicorn
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8001)
    parser.add_argument('--model', default=DEFAULT_MODEL)
    parser.add_argument('--data-dir', type=Path, default=Path('artifacts/wp4'))
    args = parser.parse_args()
    app = create_app(data_dir=args.data_dir,model=args.model,port=args.port)
    print(f'TMB FastAPI: http://127.0.0.1:{args.port} — /docs',flush=True)
    uvicorn.run(app,host='127.0.0.1',port=args.port,proxy_headers=False)


if __name__ == '__main__':
    main()
