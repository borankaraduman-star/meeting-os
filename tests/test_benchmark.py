import unittest
from meeting_os.benchmark import validate_manifest,identity_metrics
class BenchmarkTests(unittest.TestCase):
    def test_leakage_rejected(self):
        with self.assertRaisesRegex(ValueError,'leakage'):
            validate_manifest({'kind':'real','cases':[{'session':'a','reference':'a.json'}],'enrollment':[{'session':'a'}]})
    def test_identity_false_accept(self):
        m=identity_metrics([(0,2,'stranger')],[{'start':0,'end':2,'speaker_name':'Boran'}],{'Boran'})
        self.assertEqual(m['unknown_false_accept_rate'],1)
    def test_missing_identity_not_zero(self):
        self.assertIsNone(identity_metrics([],[],set())['false_reject_rate'])
