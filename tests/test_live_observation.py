import importlib.util,json,sqlite3,tempfile,unittest
from pathlib import Path
import numpy as np,soundfile as sf
spec=importlib.util.spec_from_file_location('observe_live',Path(__file__).resolve().parents[1]/'scripts/observe-live.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
class ObservationTests(unittest.TestCase):
 def test_numeric_snapshot_never_returns_transcript(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);path=root/'db.sqlite'
   with sqlite3.connect(path) as db:
    db.execute('create table meetings(id,status,metadata,created)');db.execute('create table segments(meeting,end,text)')
    db.execute('insert into meetings values(?,?,?,?)',('test','processing',json.dumps({'capture_dir':tmp}),0));db.execute('insert into segments values(?,?,?)',('test',4,'PRIVATE TEXT'))
   wav=root/'system.wav';sf.write(wav,np.zeros(16000),16000)
   (root/'capture-native.jsonl').write_text(json.dumps({'event':'chunk','source':'system','path':str(wav),'start':5,'duration':1})+'\n{"partial')
   result=module.observe(path)
   self.assertEqual(result['unprocessed_span_seconds'],2)
   self.assertTrue(result['sources']['system']['digital_silence'])
   self.assertNotIn('PRIVATE',json.dumps(result))
 def test_no_active_candidate(self):
  with tempfile.TemporaryDirectory() as tmp:
   path=Path(tmp)/'db.sqlite'
   with sqlite3.connect(path) as db:db.execute('create table meetings(id,status,metadata,created)')
   self.assertEqual(module.observe(path),{'active_candidate':False})
