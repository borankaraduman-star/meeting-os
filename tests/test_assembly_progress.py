import json,os,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
import soundfile as sf
from meeting_os.audio import assemble_capture,read_audio

class AssemblyProgressTests(unittest.TestCase):
 def fixture(self,root):
  events=[]
  for source,count in [('mic',2),('system',1)]:
   for i in range(count):
    path=root/f'{source}-{i}.wav';sf.write(path,np.full(160,.25),16000,subtype='FLOAT')
    events.append({'event':'chunk','source':source,'path':str(path),'start':i*.02})
  (root/'events.jsonl').write_text('\n'.join(json.dumps(e) for e in events))
 def test_progress_counts_completed_chunks_separately_and_preserves_pcm(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);self.fixture(root);progress=root/'progress.json';observed=[]
   def read(path):
    observed.append(json.loads(progress.read_text()));return read_audio(path)
   with patch.dict(os.environ,{'MEETING_OS_PROGRESS_PATH':str(progress)}),patch('meeting_os.audio.read_audio',side_effect=read):result=assemble_capture(root)
   self.assertEqual([(e['source'],e['current'],e['total']) for e in observed],[('mic',0,2),('mic',1,2),('system',0,1)])
   final=json.loads(progress.read_text());self.assertEqual((final['stage'],final['source'],final['current'],final['total']),('assembling','system',1,1))
   np.testing.assert_array_equal(sf.read(result['mic'],dtype='float32')[0],np.r_[np.full(160,.25,dtype=np.float32),np.zeros(160,dtype=np.float32),np.full(160,.25,dtype=np.float32)])
 def test_failed_chunk_is_not_reported_complete(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);self.fixture(root);progress=root/'progress.json'
   def read(path):
    if path.name=='mic-1.wav':raise ValueError('decode failed')
    return read_audio(path)
   with patch.dict(os.environ,{'MEETING_OS_PROGRESS_PATH':str(progress)}),patch('meeting_os.audio.read_audio',side_effect=read),self.assertRaisesRegex(ValueError,'decode failed'):assemble_capture(root)
   final=json.loads(progress.read_text());self.assertEqual((final['source'],final['current'],final['total']),('mic',1,2))
