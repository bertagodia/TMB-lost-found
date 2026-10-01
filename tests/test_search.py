import unittest

from lostfound.evaluation.runner import evaluate
from lostfound.search import SearchEngine
from lostfound.data.loader import load_objects


class SearchTests(unittest.TestCase):
    def setUp(self):
        self.engine = SearchEngine(load_objects())
        self.query = {'description': 'Mochila negra cremallera roja bolsillo delantero',
                      'date': '2026-09-11', 'line': 'L3', 'direction': ''}

    def test_late_finding_is_retrievable_with_soft_policy(self):
        soft = self.engine.search(self.query)
        strict = self.engine.search(self.query, policy='strict')
        self.assertIn('DEMO-001', [r['id'] for r in soft['results']])
        self.assertNotIn('DEMO-001', strict['eligible_ids'])

    def test_unknown_date_does_not_fall_back_to_reception(self):
        query = {**self.query, 'description': 'Paraguas amarillo madera'}
        response = self.engine.search(query, policy='strict')
        result = next(r for r in response['results'] if r['id'] == 'DEMO-003')
        self.assertIsNone(result['metadata']['day_delta'])

    def test_location_alone_cannot_create_candidate(self):
        response = self.engine.search({**self.query, 'description': 'Violín violeta'})
        self.assertEqual(response['results'], [])

    def test_invalid_input(self):
        for changes in ({'date': '2026-02-30'}, {'description': ''}):
            with self.assertRaises(ValueError):
                self.engine.search({**self.query, **changes})
        with self.assertRaises(ValueError):
            self.engine.search(self.query, min_score=float('nan'))

    def test_metrics_count_filter_loss_and_no_match_false_alarms(self):
        queries = [{**self.query, 'id': 'late', 'relevant_ids': ['DEMO-001']},
                   {**self.query, 'id': 'absent', 'relevant_ids': []}]
        report = evaluate(self.engine, queries, policy='strict')
        self.assertEqual(report['queries'][0]['filter_recall'], 0)
        self.assertEqual(report['queries'][0]['recall_at_k'], 0)
        self.assertTrue(report['queries'][1]['no_match_false_alarm'])

    def test_visual_mode_and_hybrid_preserve_text_only_route(self):
        scores = {'DEMO-002': 0.7}
        visual = self.engine.search(self.query, mode='visual', visual_scores=scores)
        self.assertEqual([r['id'] for r in visual['results']], ['DEMO-002'])
        hybrid = self.engine.search(self.query, mode='hybrid', visual_scores=scores, k=8)
        self.assertIn('DEMO-001', [r['id'] for r in hybrid['results']])


if __name__ == '__main__':
    unittest.main()
