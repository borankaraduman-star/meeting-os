import sys
import types
import unittest
from unittest.mock import patch
import numpy as np
from meeting_os.audio import speech_regions


class SilenceGateTests(unittest.TestCase):
 def test_gate_uses_bounded_abs_and_preserves_threshold_and_vad_arguments(self):
  threshold=np.float32(1e-5);below=np.nextafter(threshold,np.float32(0))
  for value in (np.float32(0),below,threshold,np.float32(-1.5),np.float32('nan')):
   for index in (0,65535,65536,131072):
    with self.subTest(value=value,index=index):
     audio=np.zeros(131073,dtype='float32');audio[index]=value
     expected_silent=np.max(np.abs(audio))<1e-5
     sizes=[];absolute=np.abs;received=[];model=object()
     def bounded_abs(a):
      sizes.append(a.size);self.assertLessEqual(a.size,65536);return absolute(a)
     def timestamps(tensor,actual_model,**kwargs):
      self.assertIs(tensor,audio);self.assertIs(actual_model,model);received.append(kwargs)
      return [{'start':3,'end':9}]
     torch=types.SimpleNamespace(from_numpy=lambda a:a)
     silero=types.SimpleNamespace(get_speech_timestamps=timestamps)
     with patch.dict(sys.modules,{'torch':torch,'silero_vad':silero}),patch('meeting_os.audio.vad_model',return_value=model),patch('meeting_os.audio.np.abs',side_effect=bounded_abs):
      actual=speech_regions(audio)
     self.assertEqual(actual,[] if expected_silent else [(3,9)])
     self.assertEqual(sum(sizes),len(audio))
     self.assertEqual(received,[] if expected_silent else [{'sampling_rate':16000,'min_speech_duration_ms':250,'min_silence_duration_ms':500,'speech_pad_ms':200,'max_speech_duration_s':28,'return_seconds':False}])
 def test_empty_audio_does_not_load_model(self):
  with patch('meeting_os.audio.vad_model',side_effect=AssertionError('empty model load')):
   self.assertEqual(speech_regions(np.array([],dtype='float32')),[])
