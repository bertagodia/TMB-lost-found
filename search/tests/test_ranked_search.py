from datetime import date
import unittest
from search import FoundObject, SearchEngine, SearchQuery


class RankedSearchTests(unittest.TestCase):
    def rank(self, objects, **query):
        return SearchEngine(objects).search(SearchQuery('bottle',**query),policy='ranked').candidates

    def test_dominant_color_wins_but_mismatches_remain(self):
        objects = [FoundObject('accent','bottle',colors=('Negre','Taronja'),color_order_known=True),
                   FoundObject('body','bottle',colors=('Taronja','Negre'),color_order_known=True),
                   FoundObject('other','bottle',colors=('Blau',),color_order_known=True)]
        results=self.rank(objects,colors=('Taronja','Vermell'))
        self.assertEqual([r.object_id for r in results],['body','accent','other'])
        self.assertIn('principal',' '.join(results[0].signals))

    def test_unknown_legacy_color_order_is_not_invented(self):
        objects=[FoundObject('a','bottle',colors=('Negre','Taronja')),
                 FoundObject('b','bottle',colors=('Taronja','Negre'))]
        results=self.rank(objects,colors=('Taronja',))
        self.assertEqual(results[0].rank_score,results[1].rank_score)

    def test_line_is_a_real_boost_not_only_a_tiebreaker(self):
        objects=[FoundObject('same','bottle with a patterned sleeve and a long strap',found_line='H12',found_transport='bus'),
                 FoundObject('other','bottle',found_line='H14',found_transport='bus'),
                 FoundObject('unknown','bottle'),FoundObject('irrelevant','umbrella',found_line='H12',found_transport='bus')]
        results=self.rank(objects,line='H12',transport='bus')
        self.assertEqual(results[0].object_id,'same')
        self.assertIn('unknown',[r.object_id for r in results])
        self.assertNotIn('irrelevant',[r.object_id for r in results])

    def test_date_favors_nearby_after_loss_and_retains_unknown(self):
        objects=[FoundObject('prior','bottle',found_date=date(2026,10,7),date_quality='confirmed'),
                 FoundObject('near','bottle',found_date=date(2026,10,9),date_quality='confirmed'),
                 FoundObject('later','bottle',found_date=date(2026,10,12),date_quality='confirmed'),
                 FoundObject('unknown','bottle')]
        self.assertEqual([r.object_id for r in self.rank(objects,lost_date=date(2026,10,8))],['near','later','unknown','prior'])

    def test_approximate_dates_reduce_strength(self):
        objects=[FoundObject('same','bottle',found_date=date(2026,10,8),date_quality='confirmed')]
        exact=self.rank(objects,lost_date=date(2026,10,8))[0]
        approx=self.rank(objects,lost_date=date(2026,10,8),date_approximate=True)[0]
        self.assertLess(approx.metadata_score,exact.metadata_score)
