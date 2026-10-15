"""Local FastAPI + PostgreSQL + Ollama server: python -m backend.server --port 8001."""
import argparse
import logging
import mimetypes
import os
from pathlib import Path
import secrets

from fastapi import APIRouter, Depends, FastAPI, Query, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.security import APIKeyHeader
from pydantic import ValidationError
import psycopg
from starlette.exceptions import HTTPException
import uvicorn

from database.repository import ConflictError, Repository
from search.extraction import ExtractionError
from search.settings import DEFAULT_MODEL

from .application import APIError, Application, extraction_view
from .models import (ContactView, ErrorView, ExtractCreate, ExtractionView, HealthView, ObjectCreate, ObjectStatus,
    ObjectStatusChange, ObjectView, Page, Receipt, ReportCreate, ReportStatus,
    ReportStatusChange, ReportView, ReviewCreate, ReviewView)

ROOT = Path(__file__).resolve().parent.parent
MAX_REQUEST = 58 * 1024 * 1024
logger = logging.getLogger(__name__)


def error_response(status, message, code, **extra):
    return JSONResponse({'error': message, 'code': code, **extra}, status_code=status)


class LocalMiddleware:
    """Bounded JSON bodies and same-origin loopback access, including chunked bodies."""
    def __init__(self, app, port):
        self.app = app
        self.hosts = {f'127.0.0.1:{port}', f'localhost:{port}'}

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)

        async def secure_send(message):
            if message['type'] == 'http.response.start':
                message['headers'] = [*message.get('headers', []),
                    (b'cache-control', b'no-store'), (b'x-content-type-options', b'nosniff'),
                    (b'x-frame-options', b'DENY')]
            await send(message)

        async def reject(status, message, code):
            await error_response(status, message, code)(scope, receive, secure_send)

        headers = {k.decode('latin-1').lower(): v.decode('latin-1') for k, v in scope['headers']}
        host = headers.get('host', '')
        if host not in self.hosts or (headers.get('origin') and headers['origin'] != 'http://' + host):
            return await reject(403, 'Accés local i mateix origen únicament.', 'local_access_only')
        if scope['method'] in {'POST', 'PATCH', 'PUT'}:
            if headers.get('content-type', '').split(';')[0].strip().lower() != 'application/json':
                return await reject(415, 'Cal enviar JSON.', 'json_required')
            try:
                length = int(headers.get('content-length', '0'))
            except ValueError:
                return await reject(400, 'Content-Length invàlid.', 'invalid_length')
            if length < 0 or length > MAX_REQUEST:
                return await reject(413, 'Petició massa gran.', 'request_too_large')
            body = bytearray()
            while True:
                message = await receive()
                if message['type'] == 'http.disconnect':
                    return
                body.extend(message.get('body', b''))
                if len(body) > MAX_REQUEST:
                    return await reject(413, 'Petició massa gran.', 'request_too_large')
                if not message.get('more_body', False):
                    break
            if not body:
                return await reject(400, 'Petició buida.', 'empty_request')
            delivered = False

            async def bounded_receive():
                nonlocal delivered
                if not delivered:
                    delivered = True
                    return {'type': 'http.request', 'body': bytes(body), 'more_body': False}
                return await receive()

            return await self.app(scope, bounded_receive, secure_send)
        await self.app(scope, receive, secure_send)


def create_app(*, dsn=None, data_dir=Path('artifacts/wp4'), model=DEFAULT_MODEL, port=8001, repository=None):
    dsn = dsn or os.environ.get('DATABASE_URL')
    if repository is None and not dsn:
        raise ValueError('Set DATABASE_URL and run python -m database.migrate first.')
    repository = repository or Repository(dsn)
    service = Application(data_dir, model, repository=repository)
    token = secrets.token_hex(32)
    app = FastAPI(title='TMB Lost & Found — Local API', version='1.0.0', redoc_url=None)
    app.state.service, app.state.token = service, token
    app.add_middleware(LocalMiddleware, port=port)
    key_header = APIKeyHeader(name='X-Local-Token', auto_error=False)

    def authorize(key=Depends(key_header)):
        if not secrets.compare_digest((key or '').encode(), token.encode()):
            raise APIError(403, 'Recarrega la pàgina o introdueix el token local.', 'invalid_token')

    router = APIRouter(dependencies=[Depends(authorize)], responses={
        403: {'model': ErrorView, 'description': 'Local token and origin required'},
        404: {'model': ErrorView, 'description': 'Resource not found'},
        409: {'model': ErrorView, 'description': 'Conflicting submission or busy extraction'},
        413: {'model': ErrorView, 'description': 'Request too large'},
        415: {'model': ErrorView, 'description': 'JSON required'},
        422: {'model': ErrorView, 'description': 'Invalid data'},
        500: {'model': ErrorView, 'description': 'Local storage or internal error'},
        502: {'model': ErrorView, 'description': 'Ollama unavailable or invalid output'},
        503: {'model': ErrorView, 'description': 'Database unavailable or migrations required'},
        504: {'model': ErrorView, 'description': 'Ollama timeout'}})

    @app.exception_handler(APIError)
    async def api_error(request, exc):
        return error_response(exc.status, exc.message, exc.code)

    @app.exception_handler(RequestValidationError)
    @app.exception_handler(ValidationError)
    async def validation_error(request, exc):
        # Never echo input values: they can contain photo bytes or contact details.
        details = [{k: e[k] for k in ('loc', 'msg', 'type')} for e in exc.errors()]
        return error_response(422, 'Dades invàlides.', 'validation_error', details=details)

    @app.exception_handler(ConflictError)
    async def conflict_error(request, exc):
        return error_response(409, str(exc), 'conflict')

    @app.exception_handler(ValueError)
    @app.exception_handler(ExtractionError)
    async def value_error(request, exc):
        return error_response(422, str(exc), 'invalid_data')

    @app.exception_handler(KeyError)
    async def missing_error(request, exc):
        return error_response(404, 'No trobat.', 'not_found')

    @app.exception_handler(psycopg.IntegrityError)
    async def integrity_error(request, exc):
        if isinstance(exc, psycopg.errors.UniqueViolation):
            return error_response(409, 'El registre entra en conflicte amb dades existents.', 'conflict')
        return error_response(422, 'Les dades incompleixen les regles de la base de dades.', 'integrity_error')

    @app.exception_handler(psycopg.Error)
    async def database_error(request, exc):
        return error_response(503, 'PostgreSQL no està disponible o necessita migracions.', 'database_unavailable')

    @app.exception_handler(OSError)
    async def storage_error(request, exc):
        logger.error('Local storage operation failed: %s', type(exc).__name__)
        return error_response(500, 'No s’ha pogut accedir als fitxers locals.', 'storage_error')

    @app.exception_handler(HTTPException)
    async def http_error(request, exc):
        return error_response(exc.status_code, 'No trobat.' if exc.status_code == 404 else str(exc.detail), 'http_error')

    @app.exception_handler(Exception)
    async def unexpected_error(request, exc):
        logger.error('API operation failed: %s', type(exc).__name__)
        return error_response(500, 'Error intern del servidor.', 'internal_error')

    def required(row):
        if row is None:
            raise KeyError('not_found')
        return row

    @app.get('/api/health', response_model=HealthView,
             responses={503: {'model': ErrorView}}, tags=['Health'])
    def health():
        try:
            repository.health()
        except (psycopg.Error, RuntimeError):
            raise APIError(503, 'PostgreSQL no està disponible o necessita migracions.', 'database_unavailable')
        return {'status': 'ready', 'database': 'ready', 'model': model}

    @router.post('/api/objects', response_model=Receipt, status_code=201,
                 responses={200: {'model': Receipt, 'description': 'Identical retry'}}, tags=['Inventory'])
    def create_object(payload: ObjectCreate, response: Response):
        result = service.submit(payload)
        response.status_code = 200 if result['duplicate'] else 201
        return result

    @router.post('/lost-found', response_model=Receipt, tags=['Inventory'])
    def legacy_create_object(payload: ObjectCreate):
        result = service.submit(payload)
        return {**result, 'status': 'received-local'}

    @router.get('/api/objects', response_model=Page[ObjectView], tags=['Inventory'])
    def objects(limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0), status: ObjectStatus | None = None):
        return repository.list_records('objects', limit=limit, offset=offset, status=status)

    @router.get('/api/objects/{object_id}', response_model=ObjectView, tags=['Inventory'])
    def get_object(object_id: str):
        return required(repository.get_object(object_id))

    @router.post('/api/objects/{object_id}/reviews', response_model=ReviewView, status_code=201, tags=['Inventory'])
    def review(object_id: str, payload: ReviewCreate):
        required(repository.get_object(object_id))
        return repository.add_review(object_id, payload.details.model_dump(mode='json'),
            **payload.model_dump(exclude={'details'}))

    @router.patch('/api/objects/{object_id}/status', response_model=ObjectView, tags=['Inventory'])
    def object_status(object_id: str, payload: ObjectStatusChange):
        return repository.set_status(object_id, payload.status)

    @router.post('/api/lost-reports', response_model=Receipt, status_code=201,
                 responses={200: {'model': Receipt, 'description': 'Identical retry'}}, tags=['Lost reports'])
    def create_report(payload: ReportCreate, response: Response):
        result = service.submit_report(payload)
        response.status_code = 200 if result['duplicate'] else 201
        return result

    @router.get('/api/lost-reports', response_model=Page[ReportView], tags=['Lost reports'])
    def reports(limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0), status: ReportStatus | None = None):
        return repository.list_records('reports', limit=limit, offset=offset, status=status)

    @router.get('/api/lost-reports/{report_id}', response_model=ReportView, tags=['Lost reports'])
    def get_report(report_id: str):
        return required(repository.get_report(report_id))

    @router.patch('/api/lost-reports/{report_id}/status', response_model=ReportView, tags=['Lost reports'])
    def report_status(report_id: str, payload: ReportStatusChange):
        return repository.set_report_status(report_id, payload.status)

    @router.get('/api/lost-reports/{report_id}/contact', response_model=ContactView, tags=['Lost reports'])
    def contact(report_id: str):
        return required(repository.get_contact(report_id))

    @router.post('/api/extract', response_model=ExtractionView, tags=['Extraction'])
    def extract(payload: ExtractCreate):
        return service.extract(payload)

    @router.get('/api/extractions/{extraction_id}', response_model=ExtractionView, tags=['Extraction'])
    def get_extraction(extraction_id: str):
        return extraction_view(required(repository.get_extraction(extraction_id)))

    @router.get('/api/photos/{photo_id}/content', response_class=FileResponse, tags=['Photos'])
    def photo(photo_id: str):
        path, media_type = service.photo_content(photo_id)
        return FileResponse(path, media_type=media_type)

    app.include_router(router)
    files = {'/': 'index.html', '/index.html': 'index.html', '/app.js': 'app.js',
             '/sync.mjs': 'sync.mjs',
             '/styles.css': 'styles.css', '/manifest.webmanifest': 'manifest.webmanifest',
             '/form-options.json': 'form-options.json'}

    def static_file(filename):
        def serve():
            path = ROOT / 'client' / filename
            if filename == 'index.html':
                return HTMLResponse(path.read_text().replace('__LOCAL_TOKEN__', token))
            return FileResponse(path, media_type=mimetypes.guess_type(path.name)[0])
        return serve

    for path, filename in files.items():
        app.add_api_route(path, static_file(filename), methods=['GET'], include_in_schema=False)
    return app


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8001)
    parser.add_argument('--model', default=DEFAULT_MODEL)
    parser.add_argument('--data-dir', type=Path, default=Path('artifacts/wp4'))
    args = parser.parse_args()
    try:
        app = create_app(data_dir=args.data_dir, model=args.model, port=args.port)
    except ValueError as exc:
        parser.exit(1, str(exc) + '\n')
    print(f'TMB API: http://127.0.0.1:{args.port} — /docs', flush=True)
    print(f'X-Local-Token: {app.state.token}', flush=True)
    uvicorn.run(app, host='127.0.0.1', port=args.port, proxy_headers=False)


if __name__ == '__main__':
    main()
