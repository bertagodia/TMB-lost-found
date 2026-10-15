import json
import os
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient
from backend.api import create_app
import backend.tests.test_postgres as fixtures


class TransportTests(unittest.TestCase):
    def setUp(self):
        self.service=SimpleNamespace(model='test',extract=Mock(return_value={'fields':{}}))
        self.app=create_app(service=self.service)
        self.client=self.enterContext(TestClient(self.app,base_url='http://127.0.0.1:8001'))
        self.headers={'X-Local-Token':self.app.state.token}

    def test_docs_static_files_health_and_local_boundary(self):
        for path in ['/','/app.js','/match.js','/location-assignment-data.json','/docs','/openapi.json']:
            r=self.client.get(path);self.assertEqual(r.status_code,200,path)
            self.assertEqual(r.headers['cache-control'],'no-store')
        self.assertIn(self.app.state.token,self.client.get('/').text)
        schema=self.client.get('/openapi.json').json()
        self.assertIn('/api/matches',schema['paths'])
        self.assertIn('ObjectCreate',schema['components']['schemas'])
        self.assertEqual(self.client.get('/api/health').json()['storage'],'json')
        self.assertEqual(self.client.get('/',headers={'Host':'evil.example'}).status_code,403)
        self.assertEqual(self.client.get('/',headers={'Origin':'https://evil.example'}).status_code,403)
        self.assertEqual(self.client.post('/api/extract',json={'photo':'secret'}).status_code,403)
        self.assertEqual(self.client.post('/api/inventory',json={},headers=self.headers).status_code,503)

    def test_invalid_and_oversized_bodies_do_not_reach_model(self):
        r=self.client.post('/api/extract',json={'photo':{'data':123,'private':'do-not-echo'}},headers=self.headers)
        self.assertEqual(r.status_code,422)
        self.assertNotIn('do-not-echo',r.text)
        self.assertEqual(self.client.post('/api/extract',content='not json',headers={**self.headers,'Content-Type':'text/plain'}).status_code,415)
        self.assertEqual(self.client.post('/api/extract',content='{',headers={**self.headers,'Content-Type':'application/json'}).status_code,422)
        with patch('backend.middleware.MAX_REQUEST',32):
            r=self.client.post('/api/extract',content=iter([b'{"photo":"',b'x'*40,b'"}']),headers={**self.headers,'Content-Type':'application/json'})
            self.assertEqual(r.status_code,413)
        self.service.extract.assert_not_called()

    def test_errors_and_success_keep_browser_contract(self):
        self.assertEqual(self.client.post('/api/extract',json={'photo':'test'},headers=self.headers).json(),{'fields':{}})
        self.service.extract.side_effect=BlockingIOError('Busy')
        r=self.client.post('/api/extract',json={'photo':'test'},headers=self.headers)
        self.assertEqual(r.status_code,409);self.assertEqual(r.json()['error'],'Busy')


@unittest.skipUnless(os.environ.get('TEST_DATABASE_URL'),'Requires isolated PostgreSQL service')
class PostgresAPITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixtures.PostgresTests.setUpClass.__func__(cls)

    @classmethod
    def cleanup(cls):
        fixtures.PostgresTests.cleanup.__func__(cls)

    def setUp(self):
        fixtures.PostgresTests.setUp(self)
        self.service=self.app
        self.api=create_app(service=self.service)
        self.client=self.enterContext(TestClient(self.api,base_url='http://127.0.0.1:8001'))
        self.headers={'X-Local-Token':self.api.state.token}

    def post(self,path,body,status=200):
        r=self.client.post(path,json=body,headers=self.headers)
        self.assertEqual(r.status_code,status,r.text)
        return r.json()

    def test_current_fields_strict_search_review_and_photos(self):
        record={**self.record,'origin':{'kind':'station','location':'Alfons X','destination':'Sagrada Família'},
                'finding':{'transport':'bus','line':'H12','date':'2026-04-03','dateQuality':'confirmed'},
                'vehicle':{**self.record['vehicle'],'transport':'bus'}}
        self.post('/api/objects',record)
        self.assertTrue(self.post('/lost-found',record)['duplicate'])
        inventory=self.post('/api/inventory',{})['objects'][0]
        self.assertEqual(inventory['origin_destination'],'Sagrada Família')
        self.assertEqual(inventory['colors'],['Taronja','Negre'])
        self.assertEqual(self.client.get('/api/objects',headers=self.headers).status_code,200)
        query={'description':'Orange bottle','line':'H12','transport':'bus','lostDate':'2026-04-10','filters':{'colors':['Taronja']}}
        result=self.post('/api/search',query);self.assertEqual(len(result['candidates']),1)
        for override in [{'line':'H14'},{'lostDate':'2026-04-11'},{'filters':{'colors':['Blau']}}]:
            self.assertEqual(self.post('/api/search',{**query,**override})['candidates'],[])
        photo=result['candidates'][0]['photo_url']
        self.assertEqual(self.client.get(photo).status_code,200)
        self.assertEqual(self.client.get(photo+'/content').status_code,200)
        review=dict(id=record['id'],revision=1,reviewed=True,details=self.fields)
        self.post('/api/review',review)
        self.post('/api/review',review,409)
        self.post('/api/status',{'id':record['id'],'status':'returned'})
        self.assertEqual(self.client.get(photo).status_code,404)
        self.assertEqual(self.post('/api/search',query)['candidates'],[])

    def test_saved_legacy_retries_and_report_match_contract(self):
        legacy={**self.record,'details':{k:v for k,v in self.fields.items() if k!='colorOrderKnown'}}
        self.service.submit(legacy)
        self.assertTrue(self.post('/lost-found',legacy)['duplicate'])
        report=dict(id='report',description='Orange bottle',incident={'transport':'bus','line':'H12'},contact={'email':'private@example.invalid'})
        # Confirm that previously saved reports retain the same retry signature.
        self.service.lost_report(report)
        result=self.post('/api/lost-reports',report)
        self.assertIn('candidates',result);self.assertNotIn('private@example.invalid',json.dumps(result))
        matches=self.post('/api/matches',dict(action='link',recordId=legacy['id'],reportId='report'))
        self.assertEqual(matches['records'][0]['matchedReportIds'],['report'])
        self.assertEqual(matches['reports'][0]['contact']['email'],'private@example.invalid')
        self.assertEqual(self.client.post('/api/matches',json={}).status_code,403)

    def test_extraction_cache_and_provenance_through_http(self):
        with patch('backend.server.model_digest',return_value='digest'),patch('backend.postgres.model_digest',return_value='digest'),patch('search.form_extraction.request_json',return_value=json.dumps(self.draft)) as infer:
            first=self.post('/api/extract',{'photo':self.photo})
            second=self.post('/api/extract',{'photo':self.photo})
            self.assertFalse(first['cached']);self.assertTrue(second['cached'])
            self.assertEqual(infer.call_count,1)
        self.post('/lost-found',{**self.record,'extractionId':first['id']})
