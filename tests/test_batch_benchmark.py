import importlib.util,unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
spec=importlib.util.spec_from_file_location('batch_benchmark',Path(__file__).resolve().parents[1]/'scripts/benchmark-cpp-batch.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
class BenchmarkTests(unittest.TestCase):
 def test_abba_order_and_output_difference_is_not_hidden(self):
  class Fake:
   def __init__(self):self.calls=[]
   def transcribe(self,x):self.calls.append('serial');return [{'text':'sensitive'}]
   def transcribe_batch(self,x):self.calls.append('batch');return [[{'text':'different'}] for _ in x]
  asr=Fake();report=module.compare(asr,[np.zeros(16000),np.zeros(16000)])
  self.assertEqual(asr.calls,['serial','serial','batch','batch','serial','serial'])
  self.assertFalse(report['exact_output_match']);self.assertNotIn('sensitive',str(report));self.assertNotIn('different',str(report))
 def test_active_job_check(self):
  with patch.object(module.subprocess,'check_output',return_value='python -m meeting_os record /tmp/audio --live'):
   self.assertTrue(module.competing_job())
  with patch.object(module.subprocess,'check_output',return_value='python scripts/benchmark-cpp-batch.py'):
   self.assertFalse(module.competing_job())
 def test_attention_comparison_is_matched_and_restores_setting(self):
  class Fake:
   flash_attention=False
   def __init__(self):self.flags=[]
   def transcribe(self,x):self.flags.append(self.flash_attention);return [{'text':'same'}]
  asr=Fake();report=module.compare_attention(asr,[np.zeros(16000)])
  self.assertEqual(asr.flags,[True,False,False,True]);self.assertFalse(asr.flash_attention)
  self.assertTrue(report['exact_output_match'])
 def test_attention_setting_restored_after_failure(self):
  class Fake:
   flash_attention=False
   def transcribe(self,x):raise ValueError('failure')
  asr=Fake()
  with self.assertRaises(ValueError):module.compare_attention(asr,[np.zeros(16000)])
  self.assertFalse(asr.flash_attention)
 def test_window_preserves_silence_and_reports_reference_errors(self):
  class Fake:
   def __init__(self):self.lengths=[]
   def transcribe(self,x):
    self.lengths.append(len(x))
    if len(x)>32000:
     np.testing.assert_array_equal(x[16000:19200],np.zeros(3200))
     return [{'text':'İpek yanlış','start':0,'end':2.2,'words':[{'word':'İpek','start':0,'end':.5},{'word':'yanlış','start':1.2,'end':1.7}]}]
    text='İpek' if x[0]==1 else 'rollout'
    return [{'text':text,'start':0,'end':1,'words':[{'word':text,'start':0,'end':.5}]}]
  asr=Fake();r=module.compare_window(asr,[np.ones(16000),np.full(16000,2)],['İpek','rollout'])
  self.assertEqual(asr.lengths,[16000,16000,35200,35200,16000,16000])
  self.assertEqual([x['wer'] for x in r['runs']],[0,.5,.5,0])
  self.assertEqual(r['runs'][0]['word_time_bounds_violations'],0)
  self.assertFalse(r['normalized_text_match'])
  self.assertNotIn('yanlış',str(r))
 def test_window_rejects_oversize_before_inference(self):
  from unittest.mock import Mock
  asr=Mock()
  with self.assertRaises(ValueError):module.compare_window(asr,[np.zeros(16000*6),np.zeros(16000*6)])
  asr.transcribe.assert_not_called()
 def test_window_timing_flags_missing_reference_and_gap_hallucination(self):
  class Fake:
   def transcribe(self,x):
    return [{'text':'fixture','words':[{'start':1.01,'end':1.19},{'start':0,'end':float('nan')},{'start':0,'end':99},{'start':0}]}]
  r=module.compare_window(Fake(),[np.zeros(16000),np.zeros(16000)])
  for run in r['runs'][1:3]:
   self.assertIsNone(run['wer'])
   self.assertEqual(run['words_in_inserted_gaps'],1)
   self.assertEqual(run['word_time_bounds_violations'],3)

 def test_window_rejects_empty_audio(self):
  from unittest.mock import Mock
  asr=Mock()
  with self.assertRaises(ValueError):module.compare_window(asr,[np.zeros(0),np.zeros(16000)])
  asr.transcribe.assert_not_called()
