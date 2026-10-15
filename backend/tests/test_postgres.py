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

from PIL import Image
import psycopg
from psycopg import sql
from psycopg.conninfo import make_conninfo

from backend.postgres import PostgresApplication
from search.extraction import ExtractionError
from database.migrate import migrate
from database.repository import ConflictError


@unittest.skipUnless(os.environ.get('TEST_DATABASE_URL'),'Requires isolated PostgreSQL integration-test service')
class PostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.admin=os.environ['TEST_DATABASE_URL']
        cls.name='tmb_http_test_'+uuid4().hex
        with psycopg.connect(cls.admin,autocommit=True) as conn:
            conn.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(cls.name)))
        cls.addClassCleanup(cls.cleanup)
        cls.dsn=make_conninfo(cls.admin,dbname=cls.name)
        migrate(cls.dsn)

    @classmethod
    def cleanup(cls):
        with psycopg.connect(cls.admin,autocommit=True) as conn:
            conn.execute(sql.SQL('DROP DATABASE {} WITH (FORCE)').format(sql.Identifier(cls.name)))

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.app=PostgresApplication(self.temp.name,self.dsn,'test-model')
        with self.app.repo.connect() as conn:
            conn.execute('TRUNCATE tmb.http_submissions,tmb.report_contacts,tmb.lost_reports,tmb.object_reviews,tmb.extraction_runs,tmb.photos,tmb.found_objects')
        data=io.BytesIO();Image.new('RGB',(24,24),'orange').save(data,format='JPEG')
        self.photo=dict(data='data:image/jpeg;base64,'+base64.b64encode(data.getvalue()).decode())
        self.fields=dict(colors=['Taronja','Negre'],objectType='Ampolla',material='Metall',description='Orange bottle')
        self.record=dict(id='test-record',photos=[self.photo,self.photo],details=self.fields,reviewed=True,
                         vehicle=dict(line='H12',vehicle='001',source='manual'),capturedAt='2026-10-09T10:00:00Z')
        self.draft=dict(object_name='bottle',visible_features=['Orange body'],colors=['orange','black'],material='metal',quality='usable',sensitive_content=False)

    def extraction(self):
        with patch('backend.server.model_digest',return_value='digest'),patch('backend.postgres.model_digest',return_value='digest'),patch('search.form_extraction.request_json',return_value=json.dumps(self.draft)):
            return self.app.extract(dict(photo=self.photo))

    def test_registration_persists_files_and_survives_restart(self):
        self.app.submit(self.record)
        restarted=PostgresApplication(self.temp.name,self.dsn,'test-model')
        results=restarted.search(dict(description='bottle',filters={'colors':['Taronja']}))
        self.assertEqual(results['candidates'][0]['id'],'test-record')
        self.assertNotIn('storage_key',json.dumps(results))
        self.assertEqual(len(restarted.repo.get_object('test-record')['photos']),2)
        photo_id=results['candidates'][0]['photo_url'].split('/')[-1]
        self.assertTrue(restarted.photo_bytes(photo_id).startswith(b'\xff\xd8'))
        self.assertTrue(restarted.submit(self.record)['duplicate'])

    def test_extract_cache_adoption_and_reuse_for_another_object(self):
        first,second=self.extraction(),self.extraction()
        self.assertNotEqual(first['id'],second['id'])
        self.assertTrue(second['cached'])
        self.app.submit({**self.record,'extractionId':first['id']})
        self.app.submit({**self.record,'id':'other','extractionId':first['id']})
        one=self.app.repo.get_object('test-record');two=self.app.repo.get_object('other')
        self.assertNotEqual(one['reviews'][0]['extraction_id'],two['reviews'][0]['extraction_id'])
        self.assertTrue(self.app.submit({**self.record,'id':'other','extractionId':first['id']})['duplicate'])

    def test_reject_return_and_stale_revision(self):
        self.app.submit(self.record)
        payload=dict(id='test-record',revision=1,reviewed=True,details=self.fields,status='rejected')
        self.app.review(payload)
        self.assertEqual(self.app.search(dict(description='bottle'))['candidates'],[])
        with self.assertRaises(ConflictError):self.app.review(payload)
        self.app.review({**payload,'revision':2,'status':'approved'})
        self.app.status(dict(id='test-record',status='returned'))
        self.assertEqual(self.app.search(dict(description='bottle'))['candidates'],[])

    def test_conflicting_request_and_bad_image_leave_no_partial_object(self):
        self.app.submit(self.record)
        with self.assertRaises(ConflictError):self.app.submit({**self.record,'details':{**self.fields,'description':'changed'}})
        with self.assertRaises(ExtractionError):self.app.submit({**self.record,'id':'bad','photos':[self.photo,dict(data='data:image/jpeg;base64,YmFk')]})
        self.assertIsNone(self.app.repo.get_object('bad'))
        self.assertEqual(len(list((Path(self.temp.name)/'photos').iterdir())),2)

    def test_concurrent_http_retries_are_idempotent(self):
        with ThreadPoolExecutor(max_workers=3) as pool:
            results=list(pool.map(lambda _:self.app.submit(self.record),range(3)))
        self.assertEqual(sum(not r['duplicate'] for r in results),1)
        self.assertEqual(len(self.app.repo.get_object('test-record')['reviews']),1)

    def test_report_contact_and_reference_photo_are_private_and_retryable(self):
        self.app.submit(self.record)
        report=dict(id='report-1',description='orange bottle',filters={'colors':['Taronja']},
                    incident={'location':'Station','lossDate':'2026-10-08'},contact={'name':'Test','email':'test@example.invalid'},referencePhoto=self.photo)
        first=self.app.lost_report(report)
        self.assertEqual(first['candidates'][0]['id'],'test-record')
        self.assertNotIn('test@example.invalid',json.dumps(first))
        self.app.lost_report(report)
        with self.app.repo.connect() as conn:
            self.assertEqual(conn.execute('SELECT count(*) AS n FROM tmb.lost_reports').fetchone()['n'],1)
            photo=conn.execute("SELECT id FROM tmb.photos WHERE report_id='report-1'").fetchone()
        with self.assertRaises(FileNotFoundError):self.app.photo_bytes(photo['id'])
        with self.assertRaises(ConflictError):self.app.lost_report({**report,'description':'Different request'})

    def test_missing_model_records_failed_attempt_and_manual_entry_still_works(self):
        with patch('backend.postgres.model_digest',side_effect=RuntimeError('Model unavailable')):
            with self.assertRaises(RuntimeError):self.app.extract(dict(photo=self.photo))
        with self.app.repo.connect() as conn:
            self.assertEqual(conn.execute('SELECT status FROM tmb.extraction_runs').fetchone()['status'],'failed')
        self.app.submit(self.record)
        self.assertEqual(len(self.app.search(dict(description='bottle'))['candidates']),1)
