import json,tempfile,unittest,wave
from pathlib import Path
from meeting_os.store import Store
from meeting_os.types import Segment
from meeting_os.retry import RetryStore

class RetryCaptureTests(unittest.TestCase):
    owner={'pid':123,'started_us':1,'boot':'a'}
    def setup_capture(self,root):
        capture=root/'capture';capture.mkdir();path=capture/'system-0.wav'
        with wave.open(str(path),'wb') as out:
            out.setnchannels(1);out.setsampwidth(2);out.setframerate(16000);out.writeframes(b'\0\0'*160)
        (capture/'events.jsonl').write_text(json.dumps({'event':'chunk','source':'system','path':str(path),'start':0})+'\n')
        db=Store(root/'db');mid=db.create_meeting('fictional',{'capture_dir':str(capture)});db.status(mid,'incomplete')
        db.add_segment(mid,Segment(0,.01,'old','system',flags=['provisional']))
        return db,mid,capture,RetryStore(db,inspect=lambda pid:self.owner)
    def test_success_same_meeting_uses_private_copy_and_keeps_raw_bytes(self):
        from meeting_os.retry_capture import retry_capture
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);db,mid,capture,retry=self.setup_capture(root);before={p.name:p.read_bytes() for p in capture.iterdir()}
            def process(directory):
                self.assertNotEqual(directory,capture)
                self.assertEqual(db.segments(mid)[0]['text'],'old')
                return [Segment(0,.01,'new','system')]
            retry_capture(retry,mid,self.owner,process)
            self.assertEqual(len(db.meetings()),1);self.assertEqual(db.segments(mid)[0]['text'],'new')
            self.assertEqual(before,{p.name:p.read_bytes() for p in capture.iterdir()});db.close()
    def test_changed_source_or_cancellation_preserves_original(self):
        from meeting_os.retry_capture import retry_capture
        for change in ('source','cancel'):
            with self.subTest(change=change),tempfile.TemporaryDirectory() as t:
                root=Path(t);db,mid,capture,retry=self.setup_capture(root);cancel=[False]
                def process(directory):
                    if change=='source':
                        with (capture/'system-0.wav').open('r+b') as f:f.seek(-1,2);f.write(b'X')
                    else:cancel[0]=True
                    return [Segment(0,.01,'new','system')]
                with self.assertRaises((ValueError,RuntimeError)):retry_capture(retry,mid,self.owner,process,cancel_requested=lambda:cancel[0])
                self.assertEqual(db.segments(mid)[0]['text'],'old');self.assertEqual(db.meetings()[0]['status'],'incomplete');db.close()
    def test_processor_failure_does_not_commit_partial_results(self):
        from meeting_os.retry_capture import retry_capture
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);db,mid,capture,retry=self.setup_capture(root)
            def process(directory):
                yield Segment(0,.01,'partial','system')
                raise RuntimeError('synthetic failure')
            with self.assertRaises(RuntimeError):retry_capture(retry,mid,self.owner,process)
            self.assertEqual(db.segments(mid)[0]['text'],'old');db.close()
    def test_cli_retry_is_supervised_and_fake_pipeline_assembles_only_copy(self):
        import contextlib,io,sys
        from unittest.mock import patch
        from meeting_os.cli import main
        from meeting_os.recovery import current_job_metadata
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);db,mid,capture,retry=self.setup_capture(root);db.close()
            args=['meeting_os','--db',str(root/'db'),'retry',mid]
            with patch('sys.argv',args),patch('meeting_os.supervisor.run_guarded') as guarded:
                main();guarded.assert_called_once();self.assertTrue(guarded.call_args.kwargs['isolated'])
            class Pipe:
                def process(self,path,source):
                    if Path(path).parent==capture:raise AssertionError('raw directory modified')
                    return [Segment(0,.01,'CLI result',source)],[],.01
            stream=io.StringIO()
            with patch('sys.argv',args),patch('meeting_os.cli.make_pipeline',return_value=Pipe()),contextlib.redirect_stdout(stream):main(supervised=True)
            result=json.loads(stream.getvalue());self.assertEqual(result['meeting'],mid)
            db=Store(root/'db');self.assertEqual(db.segments(mid)[0]['text'],'CLI result')
            self.assertEqual(len(json.loads(db.meetings()[0]['metadata'])['retry_source_digest']),64)
            self.assertFalse((capture/'system-full.wav').exists());db.close()
    def test_modified_snapshot_is_rejected(self):
        from meeting_os.retry_capture import retry_capture
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);db,mid,capture,retry=self.setup_capture(root)
            def process(work):
                (work/'000000.wav').write_bytes(b'corrupted')
                return [Segment(0,.01,'wrong','system')]
            with self.assertRaises(ValueError):retry_capture(retry,mid,self.owner,process)
            self.assertEqual(db.segments(mid)[0]['text'],'old');db.close()
    def test_guarded_worker_timeout_can_retry_same_meeting(self):
        import sys
        if sys.platform!='darwin':self.skipTest('Native owner identity')
        from meeting_os.supervisor import run_guarded
        from meeting_os.recovery import current_job_metadata
        from meeting_os.retry_capture import retry_capture
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);db,mid,capture,retry=self.setup_capture(root);db.close()
            code='''import sys,time,tempfile
from pathlib import Path
from meeting_os.store import Store
from meeting_os.retry import RetryStore
from meeting_os.retry_capture import retry_capture
from meeting_os.recovery import current_job_metadata
from meeting_os.types import Segment
root=Path(sys.argv[1]);tempfile.tempdir=str(root)
db=Store(root/'db')
def process(work):
 yield Segment(0,.01,'partial','system')
 (root/'ready').write_text('ready')
 time.sleep(10)
retry_capture(RetryStore(db),sys.argv[2],current_job_metadata()['worker_identity'],process)
'''
            with self.assertRaisesRegex(RuntimeError,'süre'):
                run_guarded([sys.executable,'-c',code,str(root),mid],timeout=1,isolated=True)
            self.assertTrue((root/'ready').exists())
            db=Store(root/'db');self.assertEqual(db.segments(mid)[0]['text'],'old')
            retry_capture(RetryStore(db),mid,current_job_metadata()['worker_identity'],lambda work:[Segment(0,.01,'recovered','system')])
            self.assertEqual(len(db.meetings()),1);self.assertEqual(db.segments(mid)[0]['text'],'recovered');db.close()
    def test_capture_directory_replacement_is_detected_against_pinned_handle(self):
        from meeting_os.retry_capture import retry_capture
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);db,mid,capture,retry=self.setup_capture(root)
            def process(work):
                capture.rename(root/'original-capture');capture.mkdir()
                return [Segment(0,.01,'new','system')]
            with self.assertRaisesRegex(ValueError,'directory changed'):retry_capture(retry,mid,self.owner,process)
            self.assertEqual(db.segments(mid)[0]['text'],'old');db.close()
    def test_record_receipt_then_cli_retry_keeps_one_meeting(self):
        import contextlib,io
        from unittest.mock import patch
        from meeting_os.cli import main
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);helper=root/'capture-helper';capture=root/'capture';receipt=root/'record.json';dbpath=root/'db'
            helper.write_text('''#!/usr/bin/env python3
import sys,json,wave
from pathlib import Path
root=Path(sys.argv[2]);path=root/'system-0.wav'
with wave.open(str(path),'wb') as out:
 out.setnchannels(1);out.setsampwidth(2);out.setframerate(16000);out.writeframes(b'\\0\\0'*160)
print(json.dumps({'event':'chunk','source':'system','path':str(path),'start':0,'duration':.01}),flush=True)
''');helper.chmod(0o700)
            with patch('sys.argv',['meeting_os','--db',str(dbpath),'record',str(capture),'--seconds','1','--capture-bin',str(helper),'--output',str(receipt)]),contextlib.redirect_stdout(io.StringIO()):main(supervised=True)
            mid=json.loads(receipt.read_text())['meeting']
            class Pipe:
                def process(self,path,source):return [Segment(0,.01,'final fixture',source)],[],.01
            with patch('sys.argv',['meeting_os','--db',str(dbpath),'retry',mid]),patch('meeting_os.cli.make_pipeline',return_value=Pipe()),contextlib.redirect_stdout(io.StringIO()):main(supervised=True)
            db=Store(dbpath);self.assertEqual(len(db.meetings()),1);self.assertEqual(db.meetings()[0]['id'],mid)
            self.assertEqual(db.meetings()[0]['status'],'complete');self.assertEqual(db.segments(mid)[0]['text'],'final fixture');db.close()
