import json,math,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np,soundfile as sf
from meeting_os.final_identity import FinalEmbedder,validate_spans,validate_vectors

class Tests(unittest.TestCase):
 def test_large_valid_result_uses_bounded_batches_without_losing_order_or_none(self):
  # Removing batching recreates the >32 MiB failure; distinct vectors expose
  # reordered batches, while None values exercise short-clip result alignment.
  expected=[]
  for i in range(7000):
   vector=[math.sin(j+1+i/7000) for j in range(256)]
   norm=math.sqrt(sum(x*x for x in vector))
   expected.append(None if i%509==0 else [x/norm for x in vector])
  from meeting_os.final_identity import MAX_OUTPUT
  self.assertGreater(len(json.dumps({'model_id':'fixture','rows':[{'index':i,'vector':v} for i,v in enumerate(expected)]}).encode()),MAX_OUTPUT)
  with tempfile.TemporaryDirectory() as d:
   p=Path(d);weights=p/'weights';weights.write_bytes(b'fixture');e=FinalEmbedder(weights)
   audio=p/'a.wav';sf.write(audio,np.zeros(23000),16000,subtype='FLOAT')
   spans=[(i,i+16000) for i in range(7000)];requests=[]
   def worker(cmd,**kwargs):
    request=json.loads(Path(cmd[-2]).read_text());batch=request['spans'];requests.append(batch)
    self.assertLessEqual(len(batch),512)
    payload={'model_id':e.model_id,'rows':[{'index':i,'vector':expected[a]} for i,(a,b) in enumerate(batch)]}
    encoded=json.dumps(payload).encode();self.assertLessEqual(len(encoded),MAX_OUTPUT)
    Path(cmd[-1]).write_bytes(encoded)
   with patch('meeting_os.final_identity.run_guarded',side_effect=worker):actual=e.embed_file(audio,spans)
   self.assertEqual(actual,expected)
   self.assertEqual([span for batch in requests for span in batch],[list(span) for span in spans])
   self.assertEqual([len(batch) for batch in requests],[512]*13+[344])
 def test_later_batch_failure_never_returns_partial_vectors(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d);weights=p/'weights';weights.write_bytes(b'fixture');e=FinalEmbedder(weights)
   audio=p/'a.wav';sf.write(audio,np.zeros(17000),16000,subtype='FLOAT');requests=[]
   def worker(cmd,**kwargs):
    batch=json.loads(Path(cmd[-2]).read_text())['spans'];requests.append(batch)
    if len(requests)==2:raise RuntimeError('later batch failed')
    Path(cmd[-1]).write_text(json.dumps({'model_id':e.model_id,'rows':[{'index':i,'vector':None} for i in range(len(batch))]}))
   with patch('meeting_os.final_identity.run_guarded',side_effect=worker),self.assertRaisesRegex(RuntimeError,'later batch failed'):
    e.embed_file(audio,[(i,i+16000) for i in range(600)])
   self.assertEqual([len(batch) for batch in requests],[512,88])
 def test_missing_later_output_cannot_reuse_previous_batch(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d);weights=p/'weights';weights.write_bytes(b'fixture');e=FinalEmbedder(weights)
   audio=p/'a.wav';sf.write(audio,np.zeros(18000),16000,subtype='FLOAT');requests=[]
   def worker(cmd,**kwargs):
    batch=json.loads(Path(cmd[-2]).read_text())['spans'];requests.append(batch)
    if len(requests)==1:
     Path(cmd[-1]).write_text(json.dumps({'model_id':e.model_id,'rows':[{'index':i,'vector':None} for i in range(len(batch))]}))
   with patch('meeting_os.final_identity.run_guarded',side_effect=worker),self.assertRaises(FileNotFoundError):
    e.embed_file(audio,[(i,i+16000) for i in range(1024)])
   self.assertEqual([len(batch) for batch in requests],[512,512])
 def test_later_batch_input_change_rejects_entire_result(self):
  for changed in ('audio','weights'):
   with self.subTest(changed=changed),tempfile.TemporaryDirectory() as d:
    p=Path(d);weights=p/'weights';weights.write_bytes(b'fixture');e=FinalEmbedder(weights)
    audio=p/'a.wav';sf.write(audio,np.zeros(17000),16000,subtype='FLOAT');requests=[]
    def worker(cmd,**kwargs):
     request=json.loads(Path(cmd[-2]).read_text());requests.append(request)
     Path(cmd[-1]).write_text(json.dumps({'model_id':e.model_id,'rows':[{'index':i,'vector':None} for i in range(len(request['spans']))]}))
     if len(requests)==2:(audio if changed=='audio' else weights).write_bytes(b'changed')
    with patch('meeting_os.final_identity.run_guarded',side_effect=worker),self.assertRaisesRegex(ValueError,'Identity input changed'):
     e.embed_file(audio,[(i,i+16000) for i in range(600)])
    self.assertEqual(len(requests),2)
    self.assertEqual(requests[0]['signature'],requests[1]['signature'])
    self.assertEqual(requests[0]['weight_signature'],requests[1]['weight_signature'])
    self.assertEqual(requests[0]['digest'],requests[1]['digest'])
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
