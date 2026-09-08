import unittest
from meeting_os.capture_metrics import timeline_metrics


class CaptureMetricsTests(unittest.TestCase):
    def test_union_gap_overlap_and_late_arrival(self):
        rows = [dict(source='mic', start=0., duration=2.),
                dict(source='mic', start=3., duration=2.),
                dict(source='mic', start=1., duration=3.),
                dict(source='system', start=.5, duration=1.)]
        result = timeline_metrics(rows)
        mic = result['sources']['mic']
        self.assertEqual(mic['covered_seconds'], 5.)
        self.assertEqual(mic['gap_seconds'], 0.)
        self.assertEqual(mic['overlap_seconds'], 2.)
        self.assertEqual(mic['out_of_order_chunks'], 1)
        self.assertEqual(result['sources']['system']['first_start'], .5)

    def test_gaps_and_missing_source_are_explicit(self):
        result = timeline_metrics([dict(source='mic', start=1., duration=2.),dict(source='mic', start=4., duration=1.)])
        self.assertEqual(result['sources']['mic']['gap_seconds'], 1.)
        self.assertEqual(result['sources']['system']['chunks'], 0)
        self.assertIsNone(result['sources']['system']['first_start'])

    def test_bad_metadata_and_bound(self):
        for row in [dict(source='x',start=0,duration=1),dict(source='mic',start=True,duration=1),
                    dict(source='mic',start=0,duration=float('nan')),dict(source='mic',start=0,duration=0)]:
            with self.assertRaises(ValueError): timeline_metrics([row])
        with self.assertRaises(ValueError):
            timeline_metrics([dict(source='mic',start=0,duration=1)]*10001)
