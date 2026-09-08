import unittest,tempfile
from pathlib import Path
from unittest.mock import patch,Mock
import numpy as np,soundfile as sf
from meeting_os.cli import parser,make_pipeline
from meeting_os.pipeline import Pipeline
from meeting_os.store import Store

class Tests(unittest.TestCase):
 def test_record_factory_defers_embedding_load(self):
  args=parser().parse_args(['record','unused','--live','--engine','cpp']);db=Mock();db.profiles.return_value=[]
  with patch('meeting_os.resources.check_pressure'),patch('meeting_os.resources.low_memory_mac',return_value=True),patch('meeting_os.backends.ASR'),patch('meeting_os.speakers.Diarizer'),patch('meeting_os.speakers.Embedder') as eager,patch('meeting_os.final_identity.FinalEmbedder') as deferred:
   make_pipeline(args,db);deferred.assert_called_once();eager.assert_not_called()
 def test_live_isolation_retains_samples_offsets_flags_identity_and_order(self):
  self.check_live_parity(False)
 def test_live_batch_reader_retains_exact_clips_and_output(self):
  self.check_live_parity(True)
 def check_live_parity(self,batch):
  order=[];clips=[]
  class A:
   engine='cpp';batch_regions=batch
   def transcribe_batch(self,clips):
    for clip in clips:self.assert_mono(clip)
    return [self.transcribe(clip) for clip in clips]
   def assert_mono(self,clip):
    assert clip.ndim==1 and clip.dtype==np.float32
   def transcribe(self,x):order.append('asr');clips.append(x.copy());return [{'start':0.,'end':1.5,'text':'test'}]
  class E:
   model_id='fixture'
   def embed(self,x):return [1.,0.]
  class Isolated(E):
   isolated_final=True
   def embed(self,x):raise AssertionError('eager embedding')
   def embed_file(self,path,spans):order.append('identity');return [[1.,0.] for _ in spans]
  class D:
   mode='sherpa';isolate_sherpa=True
   def __init__(self,e):self.embedder=e
   def turns(self,x,s):return [(0,4,s+':S0')]
   def turns_file(self,p,s,n):order.append('diar');return self.turns(None,s)
  with tempfile.TemporaryDirectory() as d:
   p=Path(d);wav=p/'capture.wav';x=np.random.default_rng(7).uniform(-1.5,1.5,(192000,2)).astype(np.float32);sf.write(wav,x,48000,subtype='FLOAT');raw=wav.read_bytes();db=Store(p/'db');db.enroll('Boran',[1.,0.],'fixture',10,'prior')
   regions=[(0,32000),(32000,64000)]
   with patch('meeting_os.pipeline.speech_regions',return_value=regions):baseline=Pipeline(A(),D(E()),db).process(wav,'mic',12,True)
   baseline_clips=clips.copy();clips.clear();order.clear()
   with patch('meeting_os.pipeline.speech_regions',side_effect=AssertionError('parent VAD')),patch('meeting_os.final_vad.isolated_regions',side_effect=lambda p,n:(order.append('vad') or regions)):
    actual=Pipeline(A(),D(Isolated()),db).process(wav,'mic',12,True)
   self.assertEqual(order,['vad','diar','asr','asr','identity'])
   for before,after in zip(baseline_clips,clips):np.testing.assert_array_equal(before,after)
   self.assertEqual([r.to_dict() for r in actual[0]],[r.to_dict() for r in baseline[0]])
   self.assertEqual(actual[1:],baseline[1:]);self.assertEqual(raw,wav.read_bytes());db.close()

 def test_live_failure_cleans_private_snapshot_and_keeps_source(self):
  seen=[]
  class E:isolated_final=True
  class D:embedder=E()
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'input.wav';sf.write(p,np.ones(16000),16000,subtype='FLOAT');original=p.read_bytes()
   def fail(path,*args):seen.append(Path(path));raise RuntimeError('worker failed')
   with patch('meeting_os.pipeline.Pipeline._process',side_effect=fail),self.assertRaisesRegex(RuntimeError,'worker failed'):
    Pipeline(None,D(),None).process(p,'mic',0,True)
   self.assertEqual(p.read_bytes(),original);self.assertEqual(len(seen),1);self.assertFalse(seen[0].exists())
 def test_oversized_live_chunk_rejected_before_full_read(self):
  class E:isolated_final=True
  class D:embedder=E()
  with patch('soundfile.info',return_value=Mock(frames=16000*61,samplerate=16000)),patch('meeting_os.pipeline.read_audio') as read,self.assertRaisesRegex(ValueError,'60 seconds'):
   Pipeline(None,D(),None).process('oversized.wav','mic',0,True)
  read.assert_not_called()
