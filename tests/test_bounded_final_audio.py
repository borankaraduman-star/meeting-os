import tempfile,unittest,weakref
from pathlib import Path
from unittest.mock import patch
import numpy as np,soundfile as sf
from meeting_os.audio import read_audio
from meeting_os.pipeline import Pipeline
from meeting_os.store import Store

class BoundedFinalTests(unittest.TestCase):
 def test_samples_embeddings_and_timeline_equal_full_buffer(self):
  class Emb:
   model_id='fake'
   def __init__(self):self.inputs=[]
   def embed(self,x):self.inputs.append(x.copy());return None
  class Diar:
   mode='sherpa'
   def __init__(self):self.embedder=Emb()
   def turns(self,x,s):return [(0,2,s+':S0'),(2,5,s+':S1')]
  class ASR:
   def __init__(self):self.inputs=[]
   def transcribe(self,x):
    self.inputs.append(x.copy())
    return [{'start':.1,'end':1.0,'text':'İpek rollout','words':[{'word':'İpek','start':.1,'end':.5},{'word':' rollout','start':.5,'end':1.0}]}]
  with tempfile.TemporaryDirectory() as tmp:
   p=Path(tmp);wav=p/'audio.wav';sf.write(wav,np.linspace(-.7,.7,80000,dtype=np.float32),16000,subtype='PCM_16');store=Store(p/'db')
   try:
    a,b=ASR(),ASR();d,e=Diar(),Diar()
    with patch('meeting_os.pipeline.speech_regions',return_value=[(8000,32000),(48000,80000)]):
     x,tx,dx=Pipeline(a,d,store).process(wav,offset=12)
     y,ty,dy=Pipeline(b,e,store).process(wav,offset=12,bounded_final=True)
    self.assertEqual([r.to_dict() for r in x],[r.to_dict() for r in y]);self.assertEqual((tx,dx),(ty,dy))
    for old,new in zip(a.inputs,b.inputs):np.testing.assert_array_equal(old,new)
    for old,new in zip(d.embedder.inputs,e.embedder.inputs):np.testing.assert_array_equal(old,new)
   finally:store.close()
 def test_full_array_released_before_asr(self):
  refs=[];case=self
  def load(path):
   x=read_audio(path);refs.append(weakref.ref(x));return x
  class D:
   mode='cluster'
   def turns(self,x,s):refs.append(weakref.ref(x));return []
  class A:
   def transcribe(self,x):case.assertIsNone(refs[0]());return []
  with tempfile.TemporaryDirectory() as tmp:
   p=Path(tmp)/'audio.wav';sf.write(p,np.ones(32000)*.1,16000)
   with patch('meeting_os.pipeline.read_audio',side_effect=load),patch('meeting_os.pipeline.speech_regions',new=lambda x:[(0,32000)]):
    Pipeline(A(),D(),None).process(p,bounded_final=True)
 def test_bounded_path_rejects_resampling_or_live_usage(self):
  with tempfile.TemporaryDirectory() as tmp:
   p=Path(tmp)/'audio.wav';sf.write(p,np.ones(48000)*.1,48000)
   with self.assertRaises(ValueError):Pipeline(None,None,None).process(p,bounded_final=True)
   with self.assertRaises(ValueError):Pipeline(None,None,None).process(p,bounded_final=True,provisional=True)
 def test_retained_numpy_view_stays_valid_after_processing(self):
  class D:
   mode='cluster'
   def turns(self,x,s):self.view=x[10:20];return []
  class A:
   def transcribe(self,x):return []
  with tempfile.TemporaryDirectory() as tmp:
   p=Path(tmp)/'audio.wav';sf.write(p,np.ones(32000)*.1,16000)
   d=D()
   with patch('meeting_os.pipeline.speech_regions',new=lambda x:[(0,32000)]):Pipeline(A(),d,None).process(p,bounded_final=True)
   np.testing.assert_array_equal(d.view,read_audio(p)[10:20])
 def test_retained_view_valid_after_analysis_failure(self):
  class D:
   def turns(self,x,s):self.view=x[10:20];raise ValueError('diarization failed')
  with tempfile.TemporaryDirectory() as tmp:
   p=Path(tmp)/'audio.wav';sf.write(p,np.ones(32000)*.1,16000)
   d=D()
   with patch('meeting_os.pipeline.speech_regions',new=lambda x:[(0,32000)]),self.assertRaises(ValueError):Pipeline(None,d,None).process(p,bounded_final=True)
   np.testing.assert_array_equal(d.view,read_audio(p)[10:20])

 def test_short_initial_read_fails_and_closes_reader(self):
  class Reader:
   frames=32000;samplerate=16000;channels=1;closed=False
   def __enter__(self):return self
   def __exit__(self,*args):self.closed=True
   def read(self,*,out):return out[:-1]
  reader=Reader()
  with patch('soundfile.SoundFile',return_value=reader),self.assertRaisesRegex(ValueError,'truncated'):
   Pipeline(None,None,None).process('unused',bounded_final=True)
  self.assertTrue(reader.closed)

 def test_isolated_file_diarization_releases_mapping_before_child(self):
  refs=[];case=self
  class D:
   mode='sherpa';isolate_sherpa=True
   def turns_file(self,path,source,frames):
    case.assertIsNone(refs[0]())
    case.assertEqual(frames,32000)
    return []
   def turns(self,*args):raise AssertionError('must use immutable file')
  class A:
   def transcribe(self,x):return []
  def vad(x):refs.append(weakref.ref(x));return [(0,32000)]
  with tempfile.TemporaryDirectory() as tmp:
   p=Path(tmp)/'audio.wav';sf.write(p,np.ones(32000)*.1,16000,subtype='FLOAT')
   with patch('meeting_os.pipeline.speech_regions',new=vad):
    Pipeline(A(),D(),None).process(p,bounded_final=True)
