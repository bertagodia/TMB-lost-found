"""Integration tests against an isolated, disposable real PostgreSQL database."""
from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from uuid import uuid4

import psycopg
from psycopg import sql
from psycopg.conninfo import make_conninfo

from database.migrate import migrate, MIGRATIONS
from database.repository import Repository, ConflictError
from database.seed import seed
from search import FoundObject, SearchEngine, SearchQuery

FIELDS = dict(colors=['Gris','Taronja','Negre'], objectType='Ampolla', material='Metall', description='')


class DatabaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.admin = os.environ.get('TEST_DATABASE_URL')
        if not cls.admin:
            raise RuntimeError('Set TEST_DATABASE_URL to a local PostgreSQL role with CREATEDB; tests never use DATABASE_URL')
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
            conn.execute('TRUNCATE tmb.http_submissions,tmb.report_contacts,tmb.lost_reports,tmb.object_reviews,tmb.extraction_runs,tmb.photos,tmb.found_objects')

    def photo(self, position=1, digest='a'*64):
        return self.repo.create_photo(storage_key='fixtures/'+uuid4().hex+'.jpg',image_sha256=digest,
            media_type='image/jpeg',size_bytes=100,width=20,height=30,position=position)

    def extraction(self, photo):
        run = self.repo.start_extraction(photo['id'],model_name='test-model',model_digest='digest',
                                       prompt_version='v1',preprocessing_version='test')
        return self.repo.complete_extraction(run['id'],raw_output={'object_name':'bottle'},
            proposed_fields=FIELDS,quality='usable',sensitive_content=False)

    def register(self, id='legacy-001', photos=None, **kwargs):
        return self.repo.register_object(id,photo_ids=[p['id'] for p in (photos or [])],
                                        details=FIELDS,reviewed=True,**kwargs)

    def execute(self, query, params=()):
        with self.repo.connect() as conn:
            return conn.execute(query,params).fetchall() if query.lstrip().upper().startswith('SELECT') else conn.execute(query,params)

    def test_two_photos_extraction_before_registration_and_search_mapping(self):
        first, second = self.photo(), self.photo(2)
        run = self.extraction(first)
        self.assertEqual(self.repo.searchable_objects(),[])
        obj = self.register(photos=[first,second],extraction_id=run['id'],registered_line='H12',
                            client_registered_at='2026-10-09T10:00:00Z')
        found = self.repo.get_object(obj['id'])
        self.assertEqual(len(found['photos']),2)
        self.assertEqual(found['reviews'][0]['colors'],FIELDS['colors'])
        candidate = self.repo.searchable_objects()[0]
        self.assertEqual(set(candidate),{'id','description','found_date','date_quality','found_line','found_direction','review_id','revision'})
        self.assertIsNone(candidate['found_date'])
        self.assertIsNone(candidate['found_line'])
        self.assertEqual(candidate['date_quality'],'unknown')
        self.assertIn('Ampolla',candidate['description'])

    def test_review_history_latest_rejection_and_status(self):
        self.register()
        changed = {**FIELDS,'colors':['Blau']}
        review = self.repo.add_review('legacy-001',changed)
        self.assertEqual(review['revision'],2)
        self.assertIn('Blau',self.repo.searchable_objects()[0]['description'])
        self.repo.add_review('legacy-001',changed,status='rejected')
        self.assertEqual(self.repo.searchable_objects(),[])
        self.repo.add_review('legacy-001',FIELDS)
        for status in ('returned','archived'):
            self.repo.set_status('legacy-001',status)
            self.assertEqual(self.repo.searchable_objects(),[])
        self.assertEqual(len(self.repo.get_object('legacy-001')['reviews']),4)

    def test_manual_registration_after_failed_extraction_and_reprocessing(self):
        photo = self.photo()
        run = self.repo.start_extraction(photo['id'],model_name='offline')
        self.repo.fail_extraction(run['id'],'Model unavailable')
        self.register(photos=[photo])
        new = self.extraction(photo)
        self.repo.add_review('legacy-001',FIELDS,extraction_id=new['id'])
        self.assertEqual(len(self.execute('SELECT * FROM tmb.extraction_runs')),2)
        self.assertEqual(len(self.repo.get_object('legacy-001')['reviews']),2)

    def test_idempotency_survives_new_review_and_status(self):
        photo = self.photo()
        self.register(photos=[photo])
        self.repo.add_review('legacy-001',{**FIELDS,'description':'Corrected'})
        self.repo.set_status('legacy-001','returned')
        self.assertTrue(self.register(photos=[photo])['duplicate'])
        same_bytes = self.photo()
        self.assertTrue(self.register(photos=[same_bytes])['duplicate'])
        with self.assertRaises(ConflictError):
            self.repo.register_object('legacy-001',photo_ids=[photo['id']],details={**FIELDS,'description':'Changed initial request'},reviewed=True)
        self.assertEqual(len(self.repo.get_object('legacy-001')['reviews']),2)

    def test_wrong_object_extraction_rolls_back_whole_registration(self):
        first = self.photo()
        run = self.extraction(first)
        self.register('one',photos=[first],extraction_id=run['id'])
        other = self.photo()
        with self.assertRaises(psycopg.errors.CheckViolation):
            self.register('two',photos=[other],extraction_id=run['id'])
        self.assertIsNone(self.repo.get_object('two'))
        self.assertIsNone(self.execute('SELECT object_id FROM tmb.photos WHERE id=%s',(other['id'],))[0]['object_id'])

    def test_equal_hashes_do_not_merge_objects_or_allow_photo_reassignment(self):
        first, second = self.photo(), self.photo()
        self.register('one',photos=[first])
        self.register('two',photos=[second])
        self.assertEqual(len(self.repo.searchable_objects()),2)
        with self.assertRaises(ConflictError):
            self.register('three',photos=[first])
        with self.assertRaises(psycopg.errors.CheckViolation):
            self.execute("UPDATE tmb.photos SET object_id='two' WHERE id=%s",(first['id'],))

    def test_constraints_and_immutable_history(self):
        photo = self.photo()
        run = self.extraction(photo)
        self.register(photos=[photo],extraction_id=run['id'])
        queries = ["UPDATE tmb.found_objects SET date_quality='confirmed'",
                   "UPDATE tmb.found_objects SET found_line=''",
                   "UPDATE tmb.found_objects SET original_details='{}'",
                   "UPDATE tmb.object_reviews SET colors=ARRAY['Negre']",
                   "DELETE FROM tmb.object_reviews", "DELETE FROM tmb.extraction_runs",
                   "DELETE FROM tmb.photos",
                   "UPDATE tmb.extraction_runs SET raw_output='{}'",
                   "UPDATE tmb.photos SET image_sha256=repeat('b',64)"]
        for query in queries:
            with self.subTest(query=query), self.assertRaises(psycopg.errors.CheckViolation):
                self.execute(query)
        with self.assertRaises(psycopg.errors.CheckViolation):
            self.execute("INSERT INTO tmb.object_reviews(id,object_id,status,source,colors,search_text) VALUES ('bad','legacy-001','approved','manual',ARRAY['Negre','Negre'],'x')")
        with self.assertRaises(psycopg.errors.CheckViolation):
            self.execute("INSERT INTO tmb.object_reviews(id,object_id,status,source,search_text) VALUES ('bad','legacy-001','approved','manual','')")
        with self.assertRaises(psycopg.errors.ForeignKeyViolation):
            self.execute("INSERT INTO tmb.extraction_runs(id,photo_id,input_image_sha256,model_name) VALUES ('wrong',%s,repeat('b',64),'test')",(photo['id'],))

    def test_concurrent_reviews_and_registrations(self):
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(lambda _: self.register(),range(4)))
        self.assertEqual(sum(not r['duplicate'] for r in results),1)
        with ThreadPoolExecutor(max_workers=4) as pool:
            reviews = list(pool.map(lambda n:self.repo.add_review('legacy-001',{**FIELDS,'description':str(n)}),range(8)))
        self.assertEqual(sorted(r['revision'] for r in reviews),list(range(2,10)))

    def test_search_snapshot_works_with_current_wp5_engine(self):
        self.register()
        def engine():
            return SearchEngine(FoundObject(**{key:value for key,value in row.items()
                                               if key not in {'review_id','revision'}})
                                for row in self.repo.searchable_objects())
        self.assertEqual(engine().search(SearchQuery('Ampolla Taronja')).candidates[0].object_id,'legacy-001')
        self.repo.add_review('legacy-001',FIELDS,status='rejected')
        self.assertEqual(engine().search(SearchQuery('Ampolla Taronja')).candidates,())

    def test_demo_repeat_preserves_subsequent_reviews(self):
        seed(self.dsn)
        self.assertEqual(len(self.repo.searchable_objects()),2)
        self.repo.add_review('demo-wp3-bottle',FIELDS,status='rejected')
        seed(self.dsn)
        self.assertEqual(len(self.repo.searchable_objects()),1)
        self.assertEqual(len(self.repo.get_object('demo-wp3-bottle')['reviews']),2)

    def test_migrations_repeat_checksum_and_atomic_failure(self):
        self.assertEqual(migrate(self.dsn),2)
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            for migration in MIGRATIONS.glob('*.sql'):
                shutil.copyfile(migration,folder/migration.name)
            first = folder/'001_inventory.sql'
            shutil.copyfile(MIGRATIONS/first.name,first)
            first.write_text(first.read_text()+'\n-- modified\n')
            with self.assertRaisesRegex(ValueError,'changed'):
                migrate(self.dsn,folder)
            shutil.copyfile(MIGRATIONS/first.name,first)
            (folder/'003_broken.sql').write_text('CREATE TABLE tmb.should_rollback(id int); SELECT missing_column;')
            with self.assertRaises(psycopg.errors.UndefinedColumn):
                migrate(self.dsn,folder)
            self.assertIsNone(self.execute("SELECT to_regclass('tmb.should_rollback') AS name")[0]['name'])
            self.assertEqual(len(self.execute('SELECT * FROM public.tmb_schema_migrations')),2)


if __name__ == '__main__':
    unittest.main()
