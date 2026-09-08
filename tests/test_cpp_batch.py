import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np,soundfile as sf
from meeting_os.backends import ASR
class CppBatchTests(unittest.TestCase):
 def test_multiple_inputs_one_guarded_child_and_separate_outputs(self):
  with tempfile.TemporaryDirectory() as tmp:
   model=Path(tmp)/'model';model.touch();asr=ASR('cpp',model,vocabulary=['Boran'])
   clips=[np.full(16000,.1),np.full(32000,.2)]
   def run(command,**kwargs):
    inputs=[Path(command[i+1]) for i,v in enumerate(command) if v=='-f'];outputs=[Path(command[i+1]) for i,v in enumerate(command) if v=='-of']
    self.assertEqual(len(inputs),2);self.assertEqual(len(outputs),2);self.assertIn('-ng',command)
    self.assertEqual(command[command.index('-t')+1],'2');self.assertEqual(kwargs['timeout'],120)
    for i,(inp,out) in enumerate(zip(inputs,outputs)):
     audio,rate=sf.read(inp);self.assertEqual(len(audio),len(clips[i]));self.assertEqual(rate,16000)
     self.assertTrue(np.allclose(audio,clips[i],atol=1/32768))
     out.with_suffix('.json').write_text(json.dumps({'transcription':[{'offsets':{'from':0,'to':1000},'text':str(i)}]}))
   with patch('meeting_os.backends.run_guarded',side_effect=run) as guard:
    rows=asr.transcribe_batch(clips);guard.assert_called_once()
   self.assertEqual([x[0]['text'] for x in rows],['0','1'])
   self.assertEqual([x[0]['start'] for x in rows],[0,0])
 def test_missing_output_fails_without_partial_results(self):
  with tempfile.TemporaryDirectory() as tmp:
   model=Path(tmp)/'model';model.touch();asr=ASR('cpp',model)
   with patch('meeting_os.backends.run_guarded'):
    with self.assertRaises(FileNotFoundError):asr.transcribe_batch([np.zeros(16000),np.zeros(16000)])
 def test_bounds_fail_before_native_process(self):
  with tempfile.TemporaryDirectory() as tmp:
   model=Path(tmp)/'model';model.touch();asr=ASR('cpp',model)
   with patch('meeting_os.backends.run_guarded') as guard:
    self.assertEqual(asr.transcribe_batch([]),[])
    for clips in ([np.zeros(16000*13)],[np.zeros(1)]*33,[np.zeros(0)]):
     with self.assertRaises(ValueError):asr.transcribe_batch(clips)
    guard.assert_not_called()

 def test_timeout_after_partial_output_cleans_temporary_inputs(self):
  from meeting_os.supervisor import JobTimeoutError
  with tempfile.TemporaryDirectory() as tmp:
   model=Path(tmp)/'model';model.touch();asr=ASR('cpp',model);created=[]
   def run(command,**kwargs):
    paths=[Path(command[i+1]) for i,v in enumerate(command) if v=='-of'];created.extend(paths)
    paths[0].with_suffix('.json').write_text('{"transcription":[]}')
    raise JobTimeoutError('test deadline')
   with patch('meeting_os.backends.run_guarded',side_effect=run):
    with self.assertRaises(JobTimeoutError):asr.transcribe_batch([np.zeros(16000),np.zeros(16000)])
   self.assertTrue(created);self.assertTrue(all(not p.parent.exists() for p in created))
