import unittest,importlib.util
from pathlib import Path
from meeting_os.speakers import Diarizer
from meeting_os.audio import read_audio,RATE
ROOT=Path(__file__).resolve().parents[1]
@unittest.skipUnless(importlib.util.find_spec('sherpa_onnx') and (ROOT/'models/sherpa/titanet-small.onnx').exists() and (ROOT/'benchmarks/human-constructed/four-voices.wav').exists(),'Local ONNX models and public fixture required')
class SherpaRegression(unittest.TestCase):
 def test_global_clusters_reset_and_stay_inside_audio(self):
  audio=read_audio(ROOT/'benchmarks/human-constructed/four-voices.wav')
  diar=Diarizer(None,'sherpa',None,.9)
  first=diar.turns(audio,'system');second=diar.turns(audio,'system')
  self.assertEqual(first,second)
  self.assertEqual(len(set(t[2] for t in first)),4)
  self.assertTrue(all(0<=a<b<=len(audio)/RATE for a,b,_ in first))
