"""Local WP4 server and Ollama adapter: python -m backend.server --port 8001."""
import argparse
import base64
import binascii
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
from pathlib import Path
import secrets
import tempfile
import threading
from urllib.parse import urlsplit

from search.extraction import MAX_BYTES, _prepare_image
from search.form_extraction import FormFields, FORM_PROMPT_VERSION, extract_form
from search.extraction import PREPROCESS_VERSION
from search.pipeline import model_digest
from search.settings import DEFAULT_MODEL
from search.storage import write_json

ROOT = Path(__file__).resolve().parent.parent
MAX_REQUEST = 58 * 1024 * 1024


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
                return {**json.loads(cache.read_text()), 'cached': True}
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
                if json.loads(target.read_text()) != normalized:
                    raise FileExistsError('Aquest ID ja existeix amb dades diferents.')
                return {'id': object_id, 'queued': False, 'status': 'received-local', 'duplicate': True}
            extraction_id = record.get('extractionId')
            if extraction_id:
                if not isinstance(extraction_id, str) or len(extraction_id) != 64 or any(c not in '0123456789abcdef' for c in extraction_id):
                    raise ValueError('Referència d’extracció invàlida.')
                extraction_path = self.data_dir / 'extractions' / (extraction_id + '.json')
                extraction = json.loads(extraction_path.read_text())
                if extraction['image_sha256'] != hashlib.sha256(decode_image(photos[0])).hexdigest():
                    raise ValueError('L’extracció no correspon a la fotografia principal.')
            write_json(target, normalized)
        return {'id': object_id, 'queued': False, 'status': 'received-local'}


class Handler(BaseHTTPRequestHandler):
    def respond(self, status, body, content_type='application/json; charset=utf-8'):
        raw = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(raw)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('X-Frame-Options', 'DENY')
        self.end_headers()
        self.wfile.write(raw)

    def allowed(self, post=False):
        hosts = {f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}'}
        if self.headers.get('Host') not in hosts:
            return False
        if self.headers.get('Origin') and self.headers['Origin'] not in {'http://' + h for h in hosts}:
            return False
        return not post or secrets.compare_digest(self.headers.get('X-Local-Token', ''), self.server.token)

    def do_GET(self):
        if not self.allowed():
            return self.respond(403, {'error': 'Accés local únicament.'})
        path = urlsplit(self.path).path
        if path == '/api/health':
            return self.respond(200, {'model': self.server.app.model, 'status': 'ready'})
        files = {'/': 'index.html', '/index.html': 'index.html', '/app.js': 'app.js',
                 '/styles.css': 'styles.css', '/manifest.webmanifest': 'manifest.webmanifest',
                 '/form-options.json': 'form-options.json'}
        if path not in files:
            return self.respond(404, {'error': 'No trobat.'})
        file = ROOT / 'client' / files[path]
        raw = file.read_bytes()
        if file.name == 'index.html':
            raw = raw.replace(b'__LOCAL_TOKEN__', self.server.token.encode())
        self.respond(200, raw, (mimetypes.guess_type(file.name)[0] or 'application/octet-stream') + '; charset=utf-8')

    def do_POST(self):
        if not self.allowed(post=True):
            return self.respond(403, {'error': 'Recarrega la pàgina per continuar.'})
        try:
            size = int(self.headers.get('Content-Length', '0'))
            if not 0 < size <= MAX_REQUEST:
                return self.respond(413, {'error': 'Petició massa gran o buida.'})
            if self.headers.get_content_type() != 'application/json':
                return self.respond(415, {'error': 'Cal enviar JSON.'})
            payload = json.loads(self.rfile.read(size))
            if not isinstance(payload, dict):
                raise ValueError('Cal enviar un objecte JSON.')
            path = urlsplit(self.path).path
            if path == '/api/extract':
                return self.respond(200, self.server.app.extract(payload))
            if path == '/lost-found':
                return self.respond(200, self.server.app.submit(payload))
            self.respond(404, {'error': 'No trobat.'})
        except BlockingIOError as exc:
            self.respond(409, {'error': str(exc)})
        except FileExistsError as exc:
            self.respond(409, {'error': str(exc)})
        except (ValueError, KeyError, TypeError, OSError, RuntimeError) as exc:
            self.respond(400, {'error': str(exc)})

    def log_message(self, format, *args):
        pass


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8001)
    parser.add_argument('--model', default=DEFAULT_MODEL)
    parser.add_argument('--data-dir', type=Path, default=Path('artifacts/wp4'))
    args = parser.parse_args()
    try:
        with ThreadingHTTPServer(('127.0.0.1', args.port), Handler) as server:
            server.app = Application(args.data_dir, args.model)
            server.token = secrets.token_hex(32)
            print(f'WP4 + Ollama: http://127.0.0.1:{server.server_port}', flush=True)
            server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    main()
