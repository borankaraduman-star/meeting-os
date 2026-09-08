import unittest,tempfile,json
from pathlib import Path
from meeting_os.desktop import capture_state
from meeting_os.audio import assemble_capture
class CaptureStateTests(unittest.TestCase):
 def test_native_journal_recovers_without_python_journal(self):
  with tempfile.TemporaryDirectory() as tmp:
   p=Path(tmp);meta={'capture_dir':tmp}
   self.assertEqual(capture_state(meta)['state'],'waiting')
   events=[{'event':'started'},{'event':'chunk','source':'mic','start':1,'duration':12},{'event':'stopped'}]
   (p/'capture-native.jsonl').write_text('\n'.join(json.dumps(e) for e in events)+'\n{"truncated')
   state=capture_state(meta);self.assertEqual(state['state'],'stopped');self.assertEqual(state['sources'],{'mic':13})
 def test_finished_capture_is_not_live_and_empty_failure_not_recoverable(self):
  from meeting_os.desktop import capture_presentation
  self.assertEqual(capture_presentation('provisional','interrupted',{'sources':{'mic':12}}),'pending_finalization')
  self.assertEqual(capture_presentation('provisional','active',{'sources':{'mic':12}}),'capturing')
  self.assertEqual(capture_presentation('incomplete','interrupted',{'sources':{}}),'not_started')
  self.assertEqual(capture_presentation('provisional','unknown',{'sources':{'mic':12}}),'capture_unknown')
