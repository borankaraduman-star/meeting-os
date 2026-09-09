import json,tempfile,unittest
from pathlib import Path
class PreviewFailureTests(unittest.TestCase):
 def test_legacy_errors_are_scoped_deduplicated_and_never_expose_text(self):
  from meeting_os.preview_failures import summarize
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);capture=root/'capture';capture.mkdir();log=root/'legacy.log'
   error={'error':'private details','chunk':str(capture/'mic-000001.wav')}
   log.write_text('\n'.join([json.dumps(error),json.dumps(error),json.dumps({'error':'other','chunk':str(root/'other.wav')}),'private transcript','{"partial']))
   result=summarize(capture,log)
   self.assertEqual(result['failed_chunks_at_least'],1);self.assertTrue(result['has_known_failures'])
   self.assertNotIn('private',str(result));self.assertNotIn('mic-',str(result))
 def test_durable_and_legacy_events_merge_without_double_counting(self):
  from meeting_os.preview_failures import summarize,record_failure
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);event={'path':str(root/'mic.wav'),'source':'mic','start':0,'duration':12}
   record_failure(root,event)
   log=root/'legacy.log';log.write_text(json.dumps({'error':'pressure','chunk':event['path']}))
   self.assertEqual(summarize(root,log)['failed_chunks_at_least'],1)
 def test_missing_log_never_claims_transcript_completeness(self):
  from meeting_os.preview_failures import summarize
  with tempfile.TemporaryDirectory() as tmp:
   result=summarize(Path(tmp))
   self.assertFalse(result['has_known_failures']);self.assertNotIn('complete',result)

 def test_failed_diagnostic_write_does_not_raise(self):
  from meeting_os.preview_failures import record_failure
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp)/'not-directory';root.write_text('keep')
   self.assertFalse(record_failure(root,{'path':str(root/'mic.wav')}))
   self.assertEqual(root.read_text(),'keep')
 def test_large_log_is_explicitly_a_lower_bound(self):
  from meeting_os.preview_failures import summarize
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);log=root/'old.log'
   log.write_text('x'*100000+'\n'+json.dumps({'error':'pressure','chunk':str(root/'mic.wav')}))
   result=summarize(root,log)
   self.assertTrue(result['log_tail_truncated']);self.assertEqual(result['failed_chunks_at_least'],1)
 def test_recorder_failure_records_deferred_chunk_without_changing_raw_audio(self):
  import io
  from unittest.mock import Mock,patch
  from meeting_os.live import record
  from meeting_os.store import Store
  from meeting_os.preview_failures import summarize
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp)/'capture';root.mkdir();raw=root/'mic.wav';raw.write_bytes(b'raw fixture')
   event={'event':'chunk','path':str(raw),'source':'mic','start':0,'duration':12}
   helper=Mock();helper.stdout=io.StringIO(json.dumps(event)+'\n');helper.poll.return_value=0;helper.wait.return_value=0
   pipeline=Mock();pipeline.process.side_effect=RuntimeError('fake inference failure')
   store=Store(Path(tmp)/'db');receipt=Path(tmp)/'receipt.json'
   try:
    with patch('meeting_os.recovery.current_job_metadata',return_value={}),patch('meeting_os.live.subprocess.Popen',return_value=helper),patch('meeting_os.live.open_lifeline',return_value=(None,None)),patch('meeting_os.live.close_lifeline'),patch('meeting_os.live.signal.signal'):
     mid=record('/fake',root,60,12,pipeline=pipeline,store=store,result_path=receipt)
    self.assertEqual(json.loads(receipt.read_text())['meeting'],mid)
    self.assertEqual(json.loads(receipt.read_text())['status'],'provisional')
    self.assertEqual(json.loads(receipt.read_text())['preview_failed_chunks'],1)
    self.assertEqual(store.meetings()[0]['status'],'provisional')
   finally:store.close()
   self.assertEqual(raw.read_bytes(),b'raw fixture')
   self.assertEqual(summarize(root)['failed_chunks_at_least'],1)
 # Reviewed behaviour changed: captured audio is never withheld. A live-preview diagnostic that could not be
 # written is still not a reason to hide a finished recording — the complaint rides the receipt instead, the
 # meeting stays provisional (never "complete"), and the full final pass regenerates the text anyway.
 def test_missing_failure_journal_is_carried_on_the_receipt_not_raised(self):
  import io
  from unittest.mock import Mock,patch
  from meeting_os.live import record
  from meeting_os.store import Store
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp)/'capture';root.mkdir();receipt=Path(tmp)/'receipt.json'
   event={'event':'chunk','path':str(root/'mic.wav'),'source':'mic','start':0,'duration':12}
   helper=Mock();helper.stdout=io.StringIO(json.dumps(event)+'\n');helper.poll.return_value=0;helper.wait.return_value=0
   pipeline=Mock();pipeline.process.side_effect=RuntimeError('fake failure');store=Store(Path(tmp)/'db')
   try:
    with patch('meeting_os.recovery.current_job_metadata',return_value={}),patch('meeting_os.live.subprocess.Popen',return_value=helper),patch('meeting_os.live.open_lifeline',return_value=(None,None)),patch('meeting_os.live.close_lifeline'),patch('meeting_os.live.signal.signal'),patch('meeting_os.preview_failures.record_failure',return_value=False):
     record('/fake',root,60,12,pipeline=pipeline,store=store,result_path=receipt)
    result=json.loads(receipt.read_text())
    self.assertEqual(result['status'],'provisional');self.assertEqual(result['preview_failed_chunks'],1)
    self.assertTrue(any('hata günlüğü' in e for e in result['errors']))
    self.assertEqual(store.meetings()[0]['status'],'provisional')
   finally:store.close()
