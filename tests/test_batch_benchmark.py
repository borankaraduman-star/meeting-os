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
