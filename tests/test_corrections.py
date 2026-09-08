import tempfile
import unittest
from pathlib import Path
from meeting_os.store import Store
from meeting_os.types import Segment
class CorrectionTests(unittest.TestCase):
    def test_one_misclustered_segment_can_be_corrected(self):
        with tempfile.TemporaryDirectory() as tmp:
            db=Store(Path(tmp)/'db'); mid=db.create_meeting('test')
            first=db.add_segment(mid,Segment(0,4,'a','mic','mic:S0'))
            db.add_segment(mid,Segment(4,8,'b','mic','mic:S0'))
            db.correct_segment(mid,first,'İpek')
            rows=db.segments(mid)
            self.assertEqual(rows[0]['speaker_name'],'İpek'); self.assertIsNone(rows[1]['speaker_name'])
            self.assertEqual(db.profiles(),[]); db.close()
