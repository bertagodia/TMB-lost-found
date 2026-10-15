"""HTTP and persistence integration tests with real, isolated PostgreSQL databases."""
import base64
from concurrent.futures import ThreadPoolExecutor
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4

from fastapi.testclient import TestClient
from PIL import Image
import psycopg
from psycopg import sql
from psycopg.conninfo import make_conninfo
from pydantic import ValidationError

from backend.server import create_app, MAX_REQUEST
from database.migrate import migrate
from database.repository import Repository
from search.extraction import ExtractionError
from search.form_extraction import FormFields, extract_form


class IntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.admin = os.environ.get('TEST_DATABASE_URL')
        if not cls.admin:
            raise RuntimeError('Set TEST_DATABASE_URL to a local PostgreSQL role with CREATEDB')
        cls.name = 'tmb_test_' + uuid4().hex
        with psycopg.connect(cls.admin, autocommit=True) as conn:
            conn.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(cls.name)))
        cls.addClassCleanup(cls.drop_database)
        cls.dsn = make_conninfo(cls.admin, dbname=cls.name)
        migrate(cls.dsn)
        cls.repo = Repository(cls.dsn)

    @classmethod
    def drop_database(cls):
        with psycopg.connect(cls.admin, autocommit=True) as conn:
            conn.execute(sql.SQL('DROP DATABASE {} WITH (FORCE)').format(sql.Identifier(cls.name)))

    def setUp(self):
        with self.repo.connect() as conn:
            conn.execute('TRUNCATE public.report_contacts,public.object_reviews,public.extraction_runs,public.photos,public.found_objects,public.lost_reports')
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        image = io.BytesIO()
        Image.new('RGB', (24, 24), 'gray').save(image, format='PNG')
        self.raw = image.getvalue()
        self.photo = {'data': 'data:image/png;base64,' + base64.b64encode(self.raw).decode(),
                      'name': '../../original.png', 'capturedAt': '2026-10-08T09:00:00Z'}
        self.fields = dict(colors=['Gris', 'Negre'], objectType='Motxilla', material='Tèxtil',
                           description='backpack. Front cord')
        self.draft = dict(object_name='backpack', visible_features=['Front cord'], colors=['gray', 'black'],
                          material='textile', quality='usable', sensitive_content=False)
        self.app = create_app(dsn=self.dsn, data_dir=self.root)
        self.client = TestClient(self.app, base_url='http://127.0.0.1:8001',
                                 headers={'X-Local-Token': self.app.state.token})
        self.addCleanup(self.client.close)
        self.record = dict(id='test-1', details=self.fields, photos=[self.photo, self.photo],
                           reviewed=True, vehicle={'line': 'H12', 'vehicle': '3421', 'source': 'manual'},
                           capturedAt='2026-10-08T10:00:00Z', status='pending')
        self.report = dict(id='citizen-1', createdAt='2026-10-08T10:00:00Z', status='pending',
            description='He perdut una motxilla grisa', incident={'lossDate': '', 'location': 'H12'},
            filters={'objectType': 'Motxilla', 'colors': ['Gris', 'Negre']},
            referencePhoto=self.photo, contact={'name': 'Test Person', 'email': 'test@example.invalid', 'phone': ''})

    def assert_status(self, response, expected):
        self.assertEqual(response.status_code, expected, response.text)
        return response.json()

    def count(self, table):
        with self.repo.connect() as conn:
            return conn.execute(sql.SQL('SELECT count(*) AS n FROM public.{}').format(sql.Identifier(table))).fetchone()['n']

    def extract(self):
        with patch('backend.application.model_digest', return_value='digest'), \
             patch('search.form_extraction.request_json', return_value=json.dumps(self.draft)):
            return self.assert_status(self.client.post('/api/extract', json={'photo': self.photo}), 200)

    def test_order_multi_colors_and_strict_choices(self):
        self.assertEqual(list(FormFields.model_fields), ['colors', 'objectType', 'material', 'description'])
        value = FormFields.model_validate_json(json.dumps(self.fields))
        self.assertEqual(value.model_dump(mode='json')['colors'], ['Gris', 'Negre'])
        for details in ({**self.fields, 'colors': ['invented']}, {**self.fields, 'description': 'x' * 251}):
            with self.assertRaises(ValidationError):
                FormFields.model_validate_json(json.dumps(details))
            self.assert_status(self.client.post('/api/objects', json={**self.record, 'details': details}), 422)

    def test_real_contract_and_unusable_output_gate(self):
        path = self.root / 'input.png'
        path.write_bytes(self.raw)
        with patch('search.form_extraction.request_json', return_value=json.dumps(self.draft)) as model:
            result = extract_form(path)
            self.assertEqual(result['fields'], self.fields)
            self.assertEqual(result['review_status'], 'pending')
            self.assertIn('WHOLE object', model.call_args.kwargs['prompt'])
        with patch('search.form_extraction.request_json', return_value=json.dumps({**self.draft, 'sensitive_content': True})):
            self.assertEqual(extract_form(path)['fields'], dict(colors=[], objectType=None, material=None, description=''))
        with patch('search.form_extraction.request_json', return_value='{}'):
            with self.assertRaises(ExtractionError):
                extract_form(path)

    def test_inventory_idempotency_history_and_file_cleanup(self):
        first = self.assert_status(self.client.post('/api/objects', json=self.record), 201)
        self.assertEqual(first['status'], 'registered')
        detail = self.assert_status(self.client.get('/api/objects/test-1'), 200)
        self.assertIsNone(detail['found_date'])
        self.assertIsNone(detail['found_line'])
        self.assertEqual(detail['registered_line'], 'H12')
        self.assertEqual(len(detail['photos']), 2)
        self.assertEqual(detail['reviews'][0]['revision'], 1)
        self.assertNotIn('submission_hash', detail)
        self.assertNotIn('storage_key', detail['photos'][0])
        photo = self.client.get('/api/photos/' + detail['photos'][0]['id'] + '/content')
        self.assertEqual(photo.content, self.raw)
        self.assertTrue(photo.headers['content-type'].startswith('image/png'))
        self.assert_status(self.client.post('/api/objects/test-1/reviews', json={
            'details': {**self.fields, 'description': 'Corrected'}}), 201)
        self.assert_status(self.client.patch('/api/objects/test-1/status', json={'status': 'returned'}), 200)
        repeated = self.assert_status(self.client.post('/api/objects', json=self.record), 200)
        self.assertTrue(repeated['duplicate'])
        self.assertEqual(repeated['status'], 'returned')
        self.assert_status(self.client.post('/api/objects', json={**self.record,
            'details': {**self.fields, 'description': 'Different submission'}}), 409)
        self.assertEqual(self.count('photos'), 2)
        self.assertEqual(len(list((self.root/'photos').iterdir())), 2)
        self.assertEqual(self.count('object_reviews'), 2)
        page = self.assert_status(self.client.get('/api/objects?limit=1&status=returned'), 200)
        self.assertEqual((page['total'], len(page['items'])), (1, 1))
        self.assert_status(self.client.get('/api/objects?limit=101'), 422)
        self.assert_status(self.client.get('/api/objects?offset=-1'), 422)

    def test_cache_has_distinct_attempts_and_primary_photo_provenance(self):
        with patch('backend.application.model_digest', return_value='digest'), \
             patch('search.form_extraction.request_json', return_value=json.dumps(self.draft)) as model:
            first = self.assert_status(self.client.post('/api/extract', json={'photo': self.photo}), 200)
            second = self.assert_status(self.client.post('/api/extract', json={'photo': self.photo}), 200)
            self.assertFalse(first['cached'])
            self.assertTrue(second['cached'])
            self.assertNotEqual(first['id'], second['id'])
            self.assertNotEqual(first['photo_id'], second['photo_id'])
            self.assertEqual(model.call_count, 1)
        record = {**self.record, 'extractionId': first['id']}
        self.assert_status(self.client.post('/lost-found', json={**record, 'reviewed': False}), 422)
        self.assert_status(self.client.post('/lost-found', json=record), 200)
        self.assertTrue(self.assert_status(self.client.post('/lost-found', json=record), 200)['duplicate'])
        self.assert_status(self.client.post('/api/objects', json={**self.record, 'id': 'two', 'extractionId': second['id']}), 201)
        self.assert_status(self.client.post('/api/objects', json={**record, 'id': 'three'}), 409)
        detail = self.assert_status(self.client.get('/api/objects/test-1'), 200)
        self.assertEqual(detail['photos'][0]['id'], first['photo_id'])
        self.assertEqual(detail['reviews'][0]['extraction_id'], first['id'])
        saved = self.assert_status(self.client.get('/api/extractions/' + first['id']), 200)
        self.assertEqual(saved['status'], 'succeeded')
        self.assertNotIn('raw_output', saved)

    def test_failed_extraction_is_audited_and_manual_registration_works(self):
        with patch('backend.application.model_digest', return_value='digest'), \
             patch('backend.application.extract_form', side_effect=ExtractionError('invalid output')):
            self.assert_status(self.client.post('/api/extract', json={'photo': self.photo}), 502)
        with self.repo.connect() as conn:
            run = conn.execute('SELECT * FROM public.extraction_runs').fetchone()
        self.assertEqual(run['status'], 'failed')
        self.assert_status(self.client.post('/api/objects', json={**self.record, 'extractionId': run['id']}), 422)
        self.assert_status(self.client.post('/api/objects', json=self.record), 201)
        self.assertEqual(self.count('object_reviews'), 1)
        with patch('backend.application.model_digest', side_effect=ValueError('offline')):
            self.assert_status(self.client.post('/api/extract', json={'photo': self.photo}), 502)
        with patch('backend.application.model_digest', return_value='digest'), \
             patch('backend.application.extract_form', side_effect=TimeoutError('timed out')):
            self.assert_status(self.client.post('/api/extract', json={'photo': self.photo}), 504)
        with self.repo.connect() as conn:
            self.assertEqual(conn.execute("SELECT count(*) AS n FROM public.extraction_runs WHERE status='failed'").fetchone()['n'], 3)

    def test_invalid_photo_and_extraction_do_not_leave_partial_registration(self):
        broken = {'data': 'data:image/png;base64,YmFk'}
        self.assert_status(self.client.post('/api/objects', json={**self.record, 'photos': [self.photo, broken]}), 422)
        self.assertEqual(self.count('found_objects'), 0)
        self.assertEqual(self.count('photos'), 0)
        self.assertEqual(list((self.root/'photos').iterdir()), [])
        self.assert_status(self.client.post('/api/objects', json={**self.record, 'extractionId': 'unknown'}), 422)
        extraction = self.extract()
        other = io.BytesIO()
        Image.new('RGB', (24, 24), 'blue').save(other, format='PNG')
        changed = {'data': 'data:image/png;base64,' + base64.b64encode(other.getvalue()).decode()}
        self.assert_status(self.client.post('/api/objects', json={**self.record,
            'extractionId': extraction['id'], 'photos': [changed]}), 422)
        self.assertEqual(self.count('found_objects'), 0)

    def test_busy_and_legacy_single_color(self):
        with self.app.state.service.extraction_lock:
            self.assert_status(self.client.post('/api/extract', json={'photo': self.photo}), 409)
        details = {**self.fields, 'color': 'Negre'}
        del details['colors']
        result = self.assert_status(self.client.post('/lost-found', json={**self.record, 'details': details}), 200)
        self.assertEqual(result['status'], 'received-local')
        self.assertEqual(self.repo.get_object('test-1')['reviews'][0]['colors'], ['Negre'])

    def test_citizen_report_contact_and_idempotency_after_status_change(self):
        self.assert_status(self.client.post('/api/lost-reports', json=self.report), 201)
        detail = self.assert_status(self.client.get('/api/lost-reports/citizen-1'), 200)
        self.assertIsNone(detail['lost_date'])
        self.assertIsNone(detail['line'])
        self.assertEqual(detail['location_text'], 'H12')
        self.assertNotIn('contact', detail)
        self.assertNotIn('test@example.invalid', json.dumps(detail))
        page = self.assert_status(self.client.get('/api/lost-reports'), 200)
        self.assertNotIn('test@example.invalid', json.dumps(page))
        contact = self.assert_status(self.client.get('/api/lost-reports/citizen-1/contact'), 200)
        self.assertEqual(contact['email'], 'test@example.invalid')
        self.assertIsNone(contact['phone'])
        self.assert_status(self.client.patch('/api/lost-reports/citizen-1/status', json={'status': 'closed'}), 200)
        repeated = self.assert_status(self.client.post('/api/lost-reports', json=self.report), 200)
        self.assertTrue(repeated['duplicate'])
        self.assertEqual(repeated['status'], 'closed')
        self.assert_status(self.client.post('/api/lost-reports', json={**self.report,
            'contact': {'email': 'changed@example.invalid'}}), 409)
        self.assertEqual(self.count('report_contacts'), 1)
        self.assertEqual(self.count('photos'), 1)
        self.assertEqual(len(list((self.root/'photos').iterdir())), 1)

    def test_report_without_optional_photo_or_contact(self):
        report = {'id': 'minimal', 'description': 'Keys', 'contact': {'name': '', 'email': '', 'phone': ''}}
        self.assert_status(self.client.post('/api/lost-reports', json=report), 201)
        self.assert_status(self.client.get('/api/lost-reports/minimal/contact'), 404)
        self.assertEqual(self.count('report_contacts'), 0)
        self.assertEqual(self.count('photos'), 0)
        self.assert_status(self.client.patch('/api/lost-reports/minimal/status', json={'status': 'cancelled'}), 200)
        self.assert_status(self.client.patch('/api/lost-reports/minimal/status', json={'status': 'deleted'}), 422)

    def test_report_constraint_failure_rolls_back_all_rows_and_new_files(self):
        # A database-side rejection after the parent and photo adoption must be atomic.
        with self.repo.connect() as conn:
            conn.execute("ALTER TABLE public.report_contacts ADD CONSTRAINT test_reject_contact CHECK (email <> 'test@example.invalid')")
        try:
            self.assert_status(self.client.post('/api/lost-reports', json=self.report), 422)
            for table in ('lost_reports', 'report_contacts', 'photos'):
                self.assertEqual(self.count(table), 0)
            self.assertEqual(list((self.root/'photos').iterdir()), [])
        finally:
            with self.repo.connect() as conn:
                conn.execute('ALTER TABLE public.report_contacts DROP CONSTRAINT test_reject_contact')

    def test_concurrent_http_reviews_and_submissions(self):
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(lambda _: self.client.post('/api/objects', json=self.record), range(4)))
        self.assertEqual(sorted(r.status_code for r in results), [200, 200, 200, 201])
        self.assertEqual(self.count('photos'), 2)
        with ThreadPoolExecutor(max_workers=4) as pool:
            reviews = list(pool.map(lambda _: self.client.post('/api/objects/test-1/reviews', json={'details': self.fields}), range(4)))
        self.assertEqual(sorted(r.json().get('revision') for r in reviews), [2, 3, 4, 5])
        self.assertEqual(self.count('object_reviews'), 5)

    def test_auth_origin_openapi_and_http_errors(self):
        self.assertEqual(self.client.get('/docs').status_code, 200)
        self.assertIn(self.app.state.token, self.client.get('/').text)
        schema = self.assert_status(self.client.get('/openapi.json'), 200)
        self.assertEqual(schema['components']['securitySchemes']['APIKeyHeader']['name'], 'X-Local-Token')
        responses = schema['paths']['/api/objects']['post']['responses']
        self.assertIn('201', responses)
        self.assertIn('200', responses)
        self.assertEqual(responses['422']['content']['application/json']['schema']['$ref'], '#/components/schemas/ErrorView')
        self.assert_status(self.client.get('/api/objects', headers={'X-Local-Token': ''}), 403)
        self.assert_status(self.client.get('/api/lost-reports/a/contact', headers={'X-Local-Token': ''}), 403)
        self.assert_status(self.client.get('/api/health', headers={'Origin': 'https://example.invalid'}), 403)
        self.assert_status(self.client.get('/api/health', headers={'Host': 'example.invalid'}), 403)
        self.assert_status(self.client.get('/api/health'), 200)
        self.assert_status(self.client.get('/api/objects/missing'), 404)
        self.assert_status(self.client.get('/api/photos/missing/content'), 404)
        self.assert_status(self.client.get('/api/extractions/missing'), 404)
        self.assert_status(self.client.post('/api/objects', content='no', headers={'Content-Type': 'text/plain'}), 415)
        self.assert_status(self.client.post('/api/objects', content='{', headers={'Content-Type': 'application/json'}), 422)
        self.assert_status(self.client.post('/api/objects', content='{}', headers={
            'Content-Type': 'application/json', 'Content-Length': str(MAX_REQUEST + 1)}), 413)
        with patch('backend.server.MAX_REQUEST', 16):
            self.assert_status(self.client.post('/api/objects', content=iter([b'{' + b'x'*20, b'}']),
                headers={'Content-Type': 'application/json'}), 413)

    def test_database_outage_and_restart_preserve_data(self):
        with patch.object(self.repo.__class__, 'connect', side_effect=psycopg.OperationalError('offline')):
            self.assert_status(self.client.get('/api/health'), 503)
            self.assert_status(self.client.post('/api/objects', json=self.record), 503)
        self.assert_status(self.client.post('/api/objects', json=self.record), 201)
        self.assert_status(self.client.post('/api/lost-reports', json=self.report), 201)
        restarted = create_app(dsn=self.dsn, data_dir=self.root)
        with TestClient(restarted, base_url='http://127.0.0.1:8001', headers={'X-Local-Token': restarted.state.token}) as client:
            detail = self.assert_status(client.get('/api/objects/test-1'), 200)
            self.assert_status(client.get('/api/lost-reports/citizen-1/contact'), 200)
            self.assertEqual(client.get('/api/photos/' + detail['photos'][0]['id'] + '/content').content, self.raw)
        self.assertNotEqual(restarted.state.token, self.app.state.token)


if __name__ == '__main__':
    unittest.main()
