import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch
import numpy as np
from meeting_os.speakers import Diarizer
from meeting_os.live import record
from meeting_os.store import Store

class RegressionTests(unittest.TestCase):
    def test_short_tail_uses_full_context(self):
        class Emb:
            def embed(self,x): return [1,0] if len(x)>=16000 else None
        with patch('meeting_os.speakers.speech_regions',return_value=[(0,48000)]):
            turns=Diarizer(Emb()).turns(np.ones(48000,dtype=np.float32),'system')
        self.assertEqual(turns,[(0,3,'system:S0')])
    def test_missing_binary_does_not_leave_processing(self):
        with tempfile.TemporaryDirectory() as tmp:
            db=Store(Path(tmp)/'db')
            with self.assertRaises(FileNotFoundError): record('/does-not-exist',Path(tmp)/'capture',1,1,store=db)
            self.assertNotIn('processing',[m['status'] for m in db.meetings()])
            db.close()
    def test_conflicting_centroid_abstains(self):
        with tempfile.TemporaryDirectory() as tmp:
            db=Store(Path(tmp)/'db')
            db.enroll('a',[1,0],'model',5)
            db.enroll('a',[-1,0],'model',5)
            self.assertIsNone(db.identify([1,0],'model')['name'])
            db.close()
