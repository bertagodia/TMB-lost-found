"""FastAPI transport using PR #7's structure and the current application services."""
from contextlib import asynccontextmanager
import mimetypes
import os
from pathlib import Path
import secrets

from fastapi import APIRouter, Depends, FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.security import APIKeyHeader
from pydantic import ValidationError
import psycopg
from starlette.concurrency import run_in_threadpool
from starlette.exceptions import HTTPException

from database.repository import ConflictError
from search.extraction import ExtractionError
from search.settings import DEFAULT_MODEL
from .middleware import LocalMiddleware
from .models import (ErrorView, ExtractCreate, HealthView, Input, MatchCreate,
                     ObjectCreate, Receipt, ReportCreate, ReviewCreate, SearchCreate, StatusChange)

ROOT = Path(__file__).resolve().parent.parent


def error_response(status, message, code, **extra):
    return JSONResponse({'error':message,'code':code,**extra},status_code=status)


def create_app(*, dsn=None, data_dir=Path('artifacts/wp4'), model=DEFAULT_MODEL,
               port=8001, service=None):
    """Build an app without opening network connections; migrate only at startup."""
    database_url = dsn or os.environ.get('DATABASE_URL')
    supplied_service = service is not None
    if service is None:
        if database_url:
            from .postgres import PostgresApplication
            service = PostgresApplication(data_dir,database_url,model)
        else:
            from .server import Application
            service = Application(data_dir,model)

    @asynccontextmanager
    async def lifespan(app):
        if database_url and not supplied_service:
            from database.migrate import migrate
            await run_in_threadpool(migrate,database_url)
        yield

    app = FastAPI(title='TMB Lost & Found API',version='0.1',redoc_url=None,lifespan=lifespan)
    app.state.service = service
    app.state.token = secrets.token_hex(32)
    app.add_middleware(LocalMiddleware,port=port)
    key_header = APIKeyHeader(name='X-Local-Token',auto_error=False)

    def authorize(key=Depends(key_header)):
        if not secrets.compare_digest((key or '').encode(),app.state.token.encode()):
            raise HTTPException(403,'Recarrega la pàgina per continuar.')

    router = APIRouter(dependencies=[Depends(authorize)],responses={
        400:{'model':ErrorView},403:{'model':ErrorView},409:{'model':ErrorView},
        422:{'model':ErrorView},503:{'model':ErrorView}})

    def invoke(method,payload):
        operation = getattr(service,method,None)
        if operation is None:
            raise HTTPException(503,'Aquesta funció necessita PostgreSQL. Configura DATABASE_URL.')
        # Preserve absent keys and input strings for existing idempotency hashes.
        return operation(payload.model_dump(mode='json',exclude_unset=True))

    @app.exception_handler(RequestValidationError)
    @app.exception_handler(ValidationError)
    async def validation_error(request,exc):
        # No photo bytes, input values, contact details or exception contexts in errors.
        details = [{'loc':e['loc'],'type':e['type']} for e in exc.errors()]
        return error_response(422,'Dades invàlides.','validation_error',details=details)

    @app.exception_handler(ConflictError)
    @app.exception_handler(FileExistsError)
    @app.exception_handler(BlockingIOError)
    async def conflict_error(request,exc):
        return error_response(409,str(exc),'conflict')

    @app.exception_handler(psycopg.IntegrityError)
    async def integrity_error(request,exc):
        return error_response(400,'Les dades no compleixen el contracte. Revisa els camps.','integrity_error')

    @app.exception_handler(psycopg.Error)
    async def database_error(request,exc):
        return error_response(503,'PostgreSQL no està disponible. Les dades no s’han confirmat.','database_unavailable')

    @app.exception_handler(ExtractionError)
    async def extraction_error(request,exc):
        return error_response(502,str(exc),'extraction_failed')

    @app.exception_handler(ValueError)
    @app.exception_handler(TypeError)
    @app.exception_handler(KeyError)
    async def value_error(request,exc):
        return error_response(400,'Dades invàlides. Revisa els camps.' if isinstance(exc,(TypeError,KeyError)) else str(exc),'invalid_data')

    @app.exception_handler(OSError)
    @app.exception_handler(RuntimeError)
    async def storage_error(request,exc):
        return error_response(500,'No s’ha pogut completar l’operació.','operation_failed')

    @app.exception_handler(HTTPException)
    async def http_error(request,exc):
        return error_response(exc.status_code,str(exc.detail),'http_error')

    @app.exception_handler(Exception)
    async def unexpected_error(request,exc):
        return error_response(500,'Error intern del servidor.','internal_error')

    @app.get('/api/health',response_model=HealthView,tags=['Health'])
    def health():
        if hasattr(service,'repo'):
            with service.repo.connect() as conn:
                conn.execute('SELECT 1')
        return dict(status='ready',model=service.model,storage='postgres' if hasattr(service,'repo') else 'json')

    @router.post('/api/extract',tags=['Extraction'])
    def extract(payload:ExtractCreate):
        return invoke('extract',payload)

    @router.post('/lost-found',response_model=Receipt,tags=['Inventory'])
    @router.post('/api/objects',response_model=Receipt,tags=['Inventory'])
    def create_object(payload:ObjectCreate):
        return invoke('submit',payload)

    @router.post('/api/inventory',tags=['Inventory'])
    def inventory(payload:Input):
        return invoke('inventory',payload)

    @router.get('/api/objects',tags=['Inventory'])
    def objects():
        return invoke('inventory',Input())

    @router.post('/api/review',tags=['Inventory'])
    def review(payload:ReviewCreate):
        return invoke('review',payload)

    @router.post('/api/status',tags=['Inventory'])
    def status(payload:StatusChange):
        return invoke('status',payload)

    @router.post('/api/search',tags=['Search'])
    def search(payload:SearchCreate):
        return invoke('search',payload)

    @router.post('/api/lost-reports',tags=['Reports'])
    def report(payload:ReportCreate):
        return invoke('lost_report',payload)

    @router.post('/api/matches',tags=['Match'])
    def matches(payload:MatchCreate):
        return invoke('matches',payload)

    # Browser <img> elements cannot send X-Local-Token; keep the existing rule:
    # only approved, registered inventory photos are retrievable through these URLs.
    @app.get('/api/photos/{photo_id}',tags=['Photos'])
    @app.get('/api/photos/{photo_id}/content',tags=['Photos'])
    def photo(photo_id:str):
        operation = getattr(service,'photo_bytes',None)
        if operation is None:
            raise HTTPException(404,'Fotografia no disponible.')
        try:
            return Response(operation(photo_id),media_type='image/jpeg')
        except (OSError,ValueError):
            raise HTTPException(404,'Fotografia no disponible.')

    app.include_router(router)
    filenames = ('app.js','styles.css','manifest.webmanifest','form-options.json',
                 'transit-options.json','location-assignment.js','location-assignment.css',
                 'location-assignment-data.json','match.js','match.css')
    files = {'/':'index.html','/index.html':'index.html',**{('/'+name):name for name in filenames}}

    def static_file(filename):
        def serve():
            path = ROOT/'client'/filename
            if filename=='index.html':
                return HTMLResponse(path.read_text(encoding='utf-8').replace('__LOCAL_TOKEN__',app.state.token))
            return Response(path.read_bytes(),media_type=mimetypes.guess_type(path.name)[0] or 'application/octet-stream')
        return serve

    for path,filename in files.items():
        app.add_api_route(path,static_file(filename),methods=['GET'],include_in_schema=False)
    return app
