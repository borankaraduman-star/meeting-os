import tempfile
import unittest
from pathlib import Path
from meeting_os.store import Store
from meeting_os.types import Segment
from meeting_os.metrics import text_metrics, diarization_error

class CoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Store(Path(self.tmp.name) / 'db.sqlite')
    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()
    def test_unknown_and_model_isolation(self):
        self.assertIsNone(self.db.identify([1, 0], 'a')['name'])
        self.db.enroll('Boran', [1, 0], 'a', 5)
        self.assertEqual(self.db.identify([1, 0], 'a')['name'], 'Boran')
        self.assertIsNone(self.db.identify([1, 0], 'b')['name'])
        self.assertIsNone(self.db.identify([0, 1], 'a')['name'])
    def test_ambiguous_identity_abstains(self):
        self.db.enroll('Boran', [1, 0], 'a', 5)
        self.db.enroll('Ali', [0.99, 0.01], 'a', 5)
        self.assertIsNone(self.db.identify([1, 0], 'a')['name'])
    def test_bad_enrollment_rejected(self):
        for vector, duration in [([1, 0], 1), ([0, 0], 5), ([float('nan'), 1], 5)]:
            with self.assertRaises(ValueError):
                self.db.enroll('Boran', vector, 'a', duration)
    def test_correction_does_not_train(self):
        m = self.db.create_meeting('test')
        sid = self.db.add_segment(m, Segment(0, 4, 'Merhaba', 'mic', 'mic:S0'))
        self.db.correct(m, 'mic:S0', 'Boran')
        self.assertEqual(self.db.segments(m)[0]['speaker_name'], 'Boran')
        self.assertEqual(self.db.profiles(), [])
        self.assertEqual(self.db.segments(m)[0]['id'], sid)
    def test_turkish_and_entities(self):
        result = text_metrics('IŞIK İpek rollout', 'ışık ipek rollout', ['İpek', 'rollout'])
        self.assertEqual(result['wer'], 0)
        self.assertEqual(result['entity_recall'], 1)
    def test_empty_reference_false_positive(self):
        self.assertEqual(text_metrics('', '')['wer'], 0)
        self.assertIsNone(text_metrics('', 'Merhaba')['wer'])
        self.assertEqual(text_metrics('', 'Merhaba')['insertions'], 1)
    def test_der_permutation_and_overlap(self):
        ref = [(0, 2, 'a'), (1, 3, 'b')]
        self.assertEqual(diarization_error(ref, [(0, 2, 'x'), (1, 3, 'y')])['der'], 0)
        self.assertGreater(diarization_error(ref, [(0, 3, 'x')])['der'], 0)

if __name__ == '__main__': unittest.main()
