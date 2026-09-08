import tempfile,unittest
from pathlib import Path
import numpy as np,soundfile as sf
class SourceSignalTests(unittest.TestCase):
 def test_silence_signal_and_unknown_are_distinct(self):
  from meeting_os.source_signal import inspect_signal
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);p=root/'mic.wav'
   self.assertEqual(inspect_signal(p,root)['state'],'unavailable')
   sf.write(p,np.zeros((4800,2)),48000,subtype='FLOAT')
   self.assertEqual(inspect_signal(p,root)['state'],'digital_silence')
   sf.write(p,np.tile([.1,-.1],(4800,1)),48000,subtype='FLOAT')
   result=inspect_signal(p,root);self.assertEqual(result['state'],'signal');self.assertAlmostEqual(result['rms'],.1,places=5)
   sf.write(p,np.full(4800,np.nan),48000,subtype='FLOAT')
   self.assertEqual(inspect_signal(p,root)['state'],'unavailable')
 def test_outside_path_and_oversized_duration_are_not_read_as_signal(self):
  from meeting_os.source_signal import inspect_signal
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);p=root/'audio.wav';sf.write(p,np.zeros(16000*66),16000)
   self.assertEqual(inspect_signal(p,root)['state'],'unavailable')
   self.assertEqual(inspect_signal(p,root/'other')['state'],'unavailable')

 def test_invalid_path_and_extreme_samples_fail_closed(self):
  from meeting_os.source_signal import inspect_signal
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);p=root/'audio.wav'
   self.assertEqual(inspect_signal(None,root)['state'],'unavailable')
   sf.write(p,np.full(1600,1e300),16000,subtype='DOUBLE')
   self.assertEqual(inspect_signal(p,root)['state'],'unavailable')
