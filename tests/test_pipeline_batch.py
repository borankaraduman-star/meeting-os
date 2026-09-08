import tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np,soundfile as sf
from meeting_os.pipeline import Pipeline
from meeting_os.store import Store
class BatchPipelineTests(unittest.TestCase):
 def test_batch_preserves_gaps_offsets_and_final_pass_remains_serial(self):
  class Recognizer:
   engine='cpp';batch_regions=True
   def __init__(self):self.batches=0;self.singles=0
   def transcribe(self,a):self.singles+=1;return [{'start':0,'end':1,'text':'test'}]
   def transcribe_batch(self,clips):self.batches+=1;return [[{'start':0,'end':1,'text':'test'}] for _ in clips]
  class Emb:
   model_id='fake'
   def embed(self,a):return None
  class Diar:
   embedder=Emb();mode='cluster'
   def turns(self,a,s):return [(0,5,s+':S0')]
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);wav=root/'audio.wav';sf.write(wav,np.ones(80000)*.1,16000);store=Store(root/'db')
   try:
    asr=Recognizer();pipe=Pipeline(asr,Diar(),store)
    with patch('meeting_os.pipeline.speech_regions',return_value=[(16000,32000),(64000,80000)]):
     rows,_,_=pipe.process(wav,offset=12,provisional=True)
     self.assertEqual(asr.batches,1);self.assertEqual(asr.singles,0)
     self.assertEqual([(r.start,r.end) for r in rows],[(13,14),(16,17)])
     pipe.process(wav,offset=12,provisional=False)
     self.assertEqual(asr.batches,1);self.assertEqual(asr.singles,2)
   finally:store.close()
