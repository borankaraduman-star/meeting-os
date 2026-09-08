import unittest
from unittest.mock import patch,Mock
from meeting_os.cli import parser,make_pipeline
class Tests(unittest.TestCase):
 def test_proxy_only_for_supported_retry(self):
  for command,engine,diar,embedding,low,expected in [('retry','cpp','sherpa','resemblyzer',True,True),('transcribe','cpp','sherpa','resemblyzer',True,False),('retry','cpp','cluster','resemblyzer',True,False),('retry','cpp','sherpa','ecapa',True,False),('retry','cpp','sherpa','resemblyzer',False,False)]:
   with self.subTest(values=(command,diar,embedding,low)):
    a=parser().parse_args([command,'unused','--engine',engine,'--diarization',diar,'--embedding',embedding]);store=Mock();store.profiles.return_value=[]
    with patch('meeting_os.resources.check_pressure'),patch('meeting_os.resources.low_memory_mac',return_value=low),patch('meeting_os.backends.ASR'),patch('meeting_os.speakers.Diarizer'),patch('meeting_os.speakers.Embedder') as eager,patch('meeting_os.final_identity.FinalEmbedder') as isolated:
     make_pipeline(a,store)
     self.assertEqual(isolated.called,expected);self.assertEqual(eager.called,not expected)
