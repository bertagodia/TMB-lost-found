from datetime import date,timedelta
import unittest
from backend.transit import CATALOGUE, calendar_date, finding, transit

class TransitTests(unittest.TestCase):
    def test_catalogue_and_mode_validation(self):
        self.assertEqual(len(CATALOGUE['modes']['bus']),108)
        self.assertEqual(len(CATALOGUE['modes']['metro']),11)
        self.assertEqual(transit('metro','l9 n'),('metro','L9N'))
        for mode,line in [('bus','L1'),('metro','H12'),(None,'H12'),('tram','T1')]:
            with self.assertRaises(ValueError):transit(mode,line)
        self.assertEqual(transit('bus',''),('bus',None))

    def test_calendar_and_unknown_finding(self):
        self.assertEqual(calendar_date('2026-04-03'),date(2026,4,3))
        for value in ['03/04/2026','2026-02-30',(date.today()+timedelta(days=1)).isoformat()]:
            with self.assertRaises(ValueError):calendar_date(value)
        self.assertEqual(finding({})['date_quality'],'unknown')
        with self.assertRaises(ValueError):finding({'dateQuality':'confirmed'})
