import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np,soundfile as sf
from meeting_os.final_identity import FinalEmbedder,validate_spans,validate_vectors

class Tests(unittest.TestCase):
 def test_model_id_without_loading_encoder_and_failed_child_has_no_result(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d);weights=p/'weights';weights.write_bytes(b'fixture')
   with patch('meeting_os.speakers.Embedder',side_effect=AssertionError('parent load')):
    e=FinalEmbedder(weights)
   self.assertEqual(e.model_id,'resemblyzer:f16d05ec6b29248d')
   audio=p/'a.wav';sf.write(audio,np.zeros(16000),16000,subtype='FLOAT')
   with patch('meeting_os.final_identity.run_guarded',side_effect=RuntimeError('worker failed')):
    with self.assertRaisesRegex(RuntimeError,'worker failed'):e.embed_file(audio,[(0,16000)])
 def test_result_count_index_model_and_vector_checks(self):
  good={'model_id':'a','rows':[{'index':0,'vector':[1.]+[0.]*255}]}
  self.assertEqual(len(validate_vectors(good,1,'a')),1)
  for value in ({'model_id':'b','rows':good['rows']},{'model_id':'a','rows':[]},{'model_id':'a','rows':[{'index':1,'vector':None}]},{'model_id':'a','rows':[{'index':0,'vector':[float('nan')]*256}]},{'model_id':'a','rows':[{'index':0}]}, {'model_id':'a','rows':[{'index':0,'vector':[0.]*256}]}):
   with self.assertRaises(ValueError):validate_vectors(value,1,'a')
 def test_span_bounds(self):
  validate_spans([(0,0),(0,16000)],16000)
  for spans in ([(0,16001)],[(True,1)],[(-1,2)],[(2,1)],[(0,16000*61)]):
   with self.assertRaises(ValueError):validate_spans(spans,16000*120 if spans==[(0,16000*61)] else 16000)
 def test_input_changed_after_worker_rejected(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d);weights=p/'weights';weights.write_bytes(b'fixture');e=FinalEmbedder(weights)
   audio=p/'a.wav';sf.write(audio,np.zeros(16000),16000,subtype='FLOAT')
   def worker(cmd,**kwargs):
    Path(cmd[-1]).write_text(json.dumps({'model_id':e.model_id,'rows':[{'index':0,'vector':None}]}))
    weights.write_bytes(b'changed')
   with patch('meeting_os.final_identity.run_guarded',side_effect=worker),self.assertRaises(ValueError):e.embed_file(audio,[(0,16000)])
 def test_worker_preserves_post_vad_torch_thread_budget(self):
  import hashlib,sys
  from unittest.mock import Mock
  from meeting_os.final_identity import main
  from meeting_os.asr_checkpoints import _signature
  with tempfile.TemporaryDirectory() as d:
   p=Path(d);weights=p/'weights';weights.write_bytes(b'fixture');audio=p/'a.wav';sf.write(audio,np.zeros(16000),16000,subtype='FLOAT')
   digest=hashlib.sha256(b'fixture').hexdigest();request=p/'request';out=p/'result'
   request.write_text(json.dumps({'weights':str(weights),'digest':digest,'weight_signature':_signature(weights),'path':str(audio),'signature':_signature(audio),'frames':16000,'spans':[[0,16000]]}))
   torch=Mock();encoder=Mock();encoder.model_id='resemblyzer:'+digest[:16];encoder.embed.return_value=[1.]+[0.]*255
   def create(*a):torch.set_num_threads.assert_called_once_with(1);return encoder
   with patch.dict(sys.modules,{'torch':torch}),patch('sys.argv',['worker',str(request),str(out)]),patch('meeting_os.speakers.Embedder',side_effect=create),patch('meeting_os.asr_checkpoints.check_pressure'):main()
   self.assertEqual(len(json.loads(out.read_text())['rows']),1)
