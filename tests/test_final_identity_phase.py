import unittest,tempfile
from pathlib import Path
from unittest.mock import patch
import numpy as np
import soundfile as sf
from meeting_os.pipeline import Pipeline
from meeting_os.store import Store

class Tests(unittest.TestCase):
 def test_all_asr_precedes_embeddings_with_exact_spans_and_same_output(self):
  events=[]
  class ASR:
   engine='cpp'
   def transcribe(self,x):
    events.append('asr');return [{'start':.125,'end':1.75,'text':'test'}]
  class Emb:
   model_id='fixture'
   def embed(self,x):return [1.,0.]
  class Deferred(Emb):
   isolated_final=True
   def embed(self,x):raise AssertionError('parent embed forbidden')
   def embed_file(self,path,spans):
    events.append('embedding');self.spans=spans
    return [[1.,0.] for _ in spans]
  class Diar:
   mode='sherpa';isolate_sherpa=True
   def __init__(self,e):self.embedder=e
   def turns(self,a,s):return [(0,5,s+':S0')]
   def turns_file(self,path,source,frames):return self.turns(None,source)
  with tempfile.TemporaryDirectory() as d:
   p=Path(d);wav=p/'a.wav';sf.write(wav,np.ones(80000,dtype=np.float32)*.1,16000,subtype='FLOAT');db=Store(p/'db')
   db.enroll('Boran',[1.,0.],'fixture',10,'prior')
   with patch('meeting_os.pipeline.speech_regions',return_value=[(8000,40000),(48000,80000)]),patch('meeting_os.final_vad.isolated_regions',return_value=[(8000,40000),(48000,80000)]):
    baseline=Pipeline(ASR(),Diar(Emb()),db).process(wav,bounded_final=True,offset=3)
    events.clear();e=Deferred();actual=Pipeline(ASR(),Diar(e),db).process(wav,bounded_final=True,offset=3)
   self.assertEqual(events,['asr','asr','embedding'])
   self.assertEqual(e.spans,[(10000,36000),(50000,76000)])
   self.assertEqual([r.to_dict() for r in actual[0]],[r.to_dict() for r in baseline[0]])
   self.assertEqual(actual[1:],baseline[1:]);db.close()
 def test_ambiguous_segment_never_requests_embedding(self):
  class E:
   isolated_final=True;model_id='fixture'
   def embed_file(self,*args):raise AssertionError('ambiguous enrollment request')
  class D:
   mode='sherpa';isolate_sherpa=True;embedder=E()
   def turns_file(self,*args):return [(0,2,'system:S0'),(0,2,'system:S1')]
  class A:
   engine='cpp'
   def transcribe(self,a):return [{'start':0.,'end':2.,'text':'test'}]
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'a.wav';sf.write(p,np.ones(32000),16000,subtype='FLOAT')
   with patch('meeting_os.final_vad.isolated_regions',return_value=[(0,32000)]):
    rows,_,_=Pipeline(A(),D(),None).process(p,bounded_final=True)
   self.assertIsNone(rows[0].embedding);self.assertIn('speaker_ambiguous',rows[0].flags)
