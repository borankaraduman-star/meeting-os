import unittest,tempfile,json
from pathlib import Path
from meeting_os.desktop import capture_state
from meeting_os.audio import assemble_capture
class CaptureStateTests(unittest.TestCase):
 def test_live_processing_status_uses_capture_evidence_without_mislabeling_retry(self):
  from meeting_os.desktop import capture_presentation
  live={'provisional':True}
  cap={'state':'capturing','sources':{'mic':12,'system':12}}
  self.assertEqual(capture_presentation('processing','active',cap,live),'capturing')
  self.assertEqual(capture_presentation('processing','active',cap,{'provisional':True,'retry_attempt':'attempt'}),'processing')
  self.assertEqual(capture_presentation('processing','active',cap,{}),'processing')
  self.assertEqual(capture_presentation('processing','interrupted',cap,{'provisional':True,'retry_attempt':'attempt'}),'processing')
  self.assertEqual(capture_presentation('processing','active',None,live),'processing')
  self.assertEqual(capture_presentation('processing','active',dict(cap,state='waiting'),live),'processing')
  self.assertEqual(capture_presentation('processing','active',dict(cap,state='stopped'),live),'processing')
  self.assertEqual(capture_presentation('processing','active',dict(cap,state='error'),live),'processing')
  self.assertEqual(capture_presentation('processing','unknown',cap,live),'capture_unknown')
  self.assertEqual(capture_presentation('processing','interrupted',cap,live),'pending_finalization')
  self.assertEqual(capture_presentation('processing','interrupted',{'sources':{}},live),'not_started')
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
 def test_signal_probe_is_opt_in_and_sources_keep_numeric_coverage(self):
  from unittest.mock import patch
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);(root/'capture-native.jsonl').write_text(json.dumps({'event':'chunk','source':'system','path':str(root/'system.wav'),'start':0,'duration':12}))
   with patch('meeting_os.source_signal.inspect_signal',return_value={'state':'digital_silence'}) as probe:
    legacy=capture_state({'capture_dir':tmp});probe.assert_not_called()
    measured=capture_state({'capture_dir':tmp},include_signal=True)
    self.assertEqual(legacy['sources'],measured['sources'])
    self.assertEqual(measured['signals']['system']['state'],'digital_silence')
    self.assertEqual(measured['signals']['mic']['state'],'unavailable')
    probe.assert_called_once()
 def test_snapshot_only_probes_live_owner_not_retries_or_completed_history(self):
  from unittest.mock import patch
  from meeting_os.desktop import dispatch
  from meeting_os.store import Store
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);db=root/'db'
   store=Store(db)
   try:
    store.create_meeting('live',{'capture_dir':tmp,'provisional':True})
    store.create_meeting('retry',{'capture_dir':tmp,'provisional':True,'retry_attempt':'retry'})
    store.create_meeting('import',{'capture_dir':tmp})
   finally:store.close()
   with patch('meeting_os.recovery.classify',return_value='active'),patch('meeting_os.desktop.capture_state',return_value={'state':'capturing','sources':{}}) as probe:
    dispatch({'action':'snapshot'},db)
   self.assertEqual(sum(c.kwargs['include_signal'] for c in probe.call_args_list),1)
