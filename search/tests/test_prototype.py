import contextlib
from datetime import date
import io
import json
from pathlib import Path
import tempfile
import unittest

from search import FoundObject, SearchEngine, SearchQuery
from search.cli import main
from search.evaluation import evaluate, extraction_summary
from search.storage import Inventory

FIXTURES = Path(__file__).resolve().parents[1] / 'fixtures'


class PrototypeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'inventory.json'
        self.inventory = Inventory(self.path)
        self.inventory.import_file(FIXTURES / 'objects.json')

    def approve(self, object_id='DEMO-001', **kwargs):
        self.inventory.review(object_id, text='Mochila negra con cremallera roja',
                              status='approved', reviewer='tester', source='manual', **kwargs)

    def test_review_gate_persistence_and_rejection(self):
        self.assertEqual(self.inventory.objects(), [])
        self.approve()
        restored = Inventory(self.path)
        self.assertEqual([o.id for o in restored.objects()], ['DEMO-001'])
        self.assertEqual(restored.objects()[0].found_date, date(2026, 9, 14))
        restored.review('DEMO-001', text='', status='rejected', reviewer='tester', source='manual')
        self.assertEqual(Inventory(self.path).objects(), [])
        self.assertEqual(len(restored.get('DEMO-001')['reviews']), 2)
        self.assertIn('cremallera', restored.get('DEMO-001')['original_description'])

    def test_duplicate_import_does_not_change_disk(self):
        before = self.path.read_bytes()
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            self.inventory.import_file(FIXTURES / 'objects.json')
        self.assertEqual(before, self.path.read_bytes())

    def test_extraction_review_requires_provenance(self):
        with self.assertRaisesRegex(ValueError, 'extraction key'):
            self.inventory.review('DEMO-001', text='negra', status='approved', reviewer='a',
                                  source='extraction', extraction_key='missing')
        self.assertEqual(self.inventory.get('DEMO-001')['reviews'], [])

    def test_unknown_schema_rejected(self):
        self.path.write_text('{"schema_version": 99, "objects": {}}')
        with self.assertRaisesRegex(ValueError, 'schema'):
            Inventory(self.path)

    def test_soft_strict_and_unknown_metadata(self):
        objects = self.inventory.objects('manual')
        engine = SearchEngine(objects)
        query = SearchQuery('mochila negra', lost_date=date(2026, 9, 11), line='L3')
        self.assertEqual(engine.search(query).candidates[0].object_id, 'DEMO-001')
        strict = engine.search(query, policy='strict')
        self.assertEqual(set(strict.excluded_ids), {'DEMO-001', 'DEMO-003'})
        self.assertIn('DEMO-002', strict.eligible_ids)
        self.assertFalse(engine.search(SearchQuery('telefono')).candidates)
        self.assertFalse(engine.search(SearchQuery('con la de')).candidates)
        self.assertFalse(engine.search(query, min_text_score=1e6).candidates)

    def test_evaluation_diagnostics_and_no_match(self):
        cases = json.loads((FIXTURES / 'queries.json').read_text())
        unreviewed = evaluate(self.inventory, cases)
        self.assertEqual(unreviewed['queries'][0]['unindexed_relevant_ids'], ['DEMO-001'])
        result = evaluate(self.inventory, cases, variant='manual', policy='strict')
        self.assertEqual(result['queries'][0]['filtered_relevant_ids'], ['DEMO-001'])
        self.assertEqual(result['summary']['no_match_false_positive_rate'], 0)
        self.assertEqual(result['queries'][1]['at_k']['1']['recall'], 1)
        self.assertIsNone(result['queries'][2]['at_k']['1']['recall'])
        self.assertAlmostEqual(result['queries'][1]['at_k']['3']['precision'], 1 / 3)
        self.assertIsNone(extraction_summary(self.inventory)['attribute_errors'])

    def test_normalization_and_empty_inventory(self):
        obj = FoundObject(id='one', description='BOLÍGRAFO azul')
        self.assertTrue(SearchEngine([obj]).search(SearchQuery('boligrafo')).candidates)
        self.assertFalse(SearchEngine([]).search(SearchQuery('boligrafo')).candidates)
        with self.assertRaises(ValueError):
            SearchEngine([obj, obj])
        with self.assertRaises(ValueError):
            FoundObject(id='bad', description='', found_date=date.today())

    def run_cli(self, *args):
        output, errors = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
            code = main(['--store', str(self.path), *args])
        return code, output.getvalue(), errors.getvalue()

    def test_photo_requires_explicit_resolution_and_preserves_sources(self):
        self.approve()
        photo = Path(self.tmp.name) / 'photo.json'
        photo.write_text(json.dumps({'key': 'example', 'result': {
            'source': 'claimant', 'draft_search_text': 'Mochila azul'}}))
        code, _, error = self.run_cli('search', 'mochila negra', '--photo-result', str(photo))
        self.assertEqual(code, 1)
        self.assertIn('photo-action', error)
        code, output, _ = self.run_cli('search', 'mochila negra', '--photo-result', str(photo),
                                     '--photo-action', 'combine', '--reviewed-photo-text', 'cremallera roja')
        self.assertEqual(code, 0)
        result = json.loads(output)
        self.assertEqual(result['sources']['original_description'], 'mochila negra')
        self.assertEqual(result['sources']['photo_extraction']['result']['draft_search_text'], 'Mochila azul')
        self.assertIn('roja', result['query']['description'])
        self.assertEqual(result['candidates'][0]['object_id'], 'DEMO-001')

    def test_cli_evaluation_writes_report(self):
        output = Path(self.tmp.name) / 'report.json'
        code, _, error = self.run_cli('evaluate', str(FIXTURES / 'queries.json'), '--output', str(output))
        self.assertEqual(code, 0, error)
        self.assertEqual(len(json.loads(output.read_text())['runs']), 3)


if __name__ == '__main__':
    unittest.main()
