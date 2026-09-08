import unittest,tempfile,json
from pathlib import Path
from unittest.mock import patch
import numpy as np,soundfile as sf
from meeting_os.final_vad import isolated_regions,validate_regions
class Tests(unittest.TestCase):
 def test_invalid_timeline_rejected(self):
  for rows in ([[0,16001]],[[2,2]],[[True,3]],[[4,5],[1,2]]):
   with self.assertRaises(ValueError):validate_regions(rows,16000)
 def test_worker_failure_and_changed_snapshot_rejected(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'a.wav';sf.write(p,np.zeros(16000),16000,subtype='FLOAT')
   with patch('meeting_os.final_vad.run_guarded',side_effect=RuntimeError('failed')),self.assertRaises(RuntimeError):isolated_regions(p,16000)
   def worker(cmd,**kwargs):
    Path(cmd[-2]).write_text('[[0,16000]]');p.write_bytes(b'changed')
   with patch('meeting_os.final_vad.run_guarded',side_effect=worker),self.assertRaises(ValueError):isolated_regions(p,16000)
