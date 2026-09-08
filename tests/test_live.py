import tempfile
import unittest
from pathlib import Path
from meeting_os.live import record
from meeting_os.store import Store

class LiveTests(unittest.TestCase):
    def recorder(self,root,event):
        p=root/'recorder'
        p.write_text('#!/usr/bin/env python3\nprint('+repr(event)+',flush=True)\n')
        p.chmod(0o700)
        return p
    def test_no_overwrite(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t); (root/'events.jsonl').write_text('keep')
            with self.assertRaises(ValueError): record('/missing',root,1,1)
            self.assertEqual((root/'events.jsonl').read_text(),'keep')
    def test_capture_error_marks_incomplete(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t); binary=self.recorder(root,'{"event":"error","message":"device gone"}')
            db=Store(root/'db')
            with self.assertRaisesRegex(RuntimeError,'device gone'): record(binary,root/'capture',1,1,store=db)
            self.assertEqual(db.meetings()[0]['status'],'incomplete')
            db.close()
    def test_capture_error_stops_helper_and_preserves_audio_without_receipt(self):
        import json,signal,threading,time
        from unittest.mock import patch
        # Removing error-triggered shutdown must fail before the fallback EOF.
        # The fake owns no child process; signals and lifeline calls are mocked.
        for graceful in (False,True):
            with self.subTest(graceful=graceful),tempfile.TemporaryDirectory() as t:
                root=Path(t);done=threading.Event();ready=threading.Event()
                class Helper:
                    code=None
                    closed=False
                    signals=[]
                    killed=False
                    def __init__(self):self.stdout=self
                    def __iter__(self):
                        yield json.dumps({'event':'chunk','path':'saved.wav','source':'system','start':0})+'\n'
                        yield json.dumps({'event':'error','message':'device gone'})+'\n'
                        ready.set()
                        done.wait(.8)  # Bound the regression even without the fix.
                        self.code=self.code if self.code is not None else 0
                        yield json.dumps({'event':'chunk','path':'tail.wav','source':'mic','start':1})+'\n'
                    def poll(self):return self.code
                    def send_signal(self,sig):
                        self.signals.append(sig)
                        if graceful:self.code=0;done.set()
                    def kill(self):self.killed=True;self.code=-9;done.set()
                    def wait(self,timeout=None):return self.code
                    def close(self):self.closed=True
                helper=Helper();db=Store(root/'db');receipt=root/'completion.json'
                def warmed():
                    if not ready.wait(1):raise AssertionError('fake reader did not start')
                old_handler=signal.getsignal(signal.SIGINT)
                started=time.monotonic()
                with patch('meeting_os.recovery.current_job_metadata',return_value={}),patch('meeting_os.live.subprocess.Popen',return_value=helper),patch('meeting_os.live.open_lifeline',return_value=(None,None)),patch('meeting_os.live.close_lifeline') as close,patch('meeting_os.live.signal.signal') as handler,patch('meeting_os.live.CAPTURE_STOP_GRACE_SECONDS',.05):
                    with self.assertRaisesRegex(RuntimeError,'device gone'):
                        record('/fake',root/'capture',60,12,store=db,pipeline_factory=warmed,result_path=receipt)
                self.assertLess(time.monotonic()-started,.6)
                self.assertEqual(helper.signals,[signal.SIGINT])
                self.assertEqual(helper.killed,not graceful)
                self.assertTrue(helper.closed);close.assert_called_once_with(None,None)
                self.assertEqual(handler.call_args.args,(signal.SIGINT,old_handler))
                journal=(root/'capture/events.jsonl').read_text()
                self.assertIn('saved.wav',journal);self.assertIn('tail.wav',journal)
                self.assertIn('device gone',journal)
                self.assertFalse(receipt.exists())
                self.assertEqual(db.meetings()[0]['status'],'incomplete');db.close()
    def test_model_warmup_failure_leaves_recoverable_meeting(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t); binary=self.recorder(root,'{"event":"started"}')
            db=Store(root/'db')
            def broken(): raise RuntimeError('model unavailable')
            with self.assertRaisesRegex(RuntimeError,'model unavailable'):
                record(binary,root/'capture',1,1,store=db,pipeline_factory=broken)
            self.assertEqual(db.meetings()[0]['status'],'incomplete')
            self.assertIn('capture_dir',db.meetings()[0]['metadata'])
            self.assertIn('worker_identity',db.meetings()[0]['metadata'])
            db.close()
    def test_stop_skips_queued_live_inference_but_keeps_capture_journal(self):
        import signal,time,json,sys
        with tempfile.TemporaryDirectory() as t:
            root=Path(t); ready=root/'ready'; binary=root/'recorder'
            binary.write_text('#!/usr/bin/env python3\nimport signal,time,json\nfrom pathlib import Path\nsignal.signal(signal.SIGINT,lambda *a:exit(0))\nprint(json.dumps({"event":"chunk","path":"saved.wav","source":"system","start":0}),flush=True)\nPath('+repr(str(ready))+').write_text("ready")\ntime.sleep(20)\n')
            binary.chmod(0o700);db=Store(root/'db');calls=[]
            class Pipe:
                def process(self,*a):calls.append(a);return [],[],1
            def factory():
                deadline=time.monotonic()+5
                while not ready.exists():
                    if time.monotonic()>deadline:raise RuntimeError('recorder did not start')
                    time.sleep(.01)
                signal.getsignal(signal.SIGINT)(signal.SIGINT,None)
                return Pipe()
            record(binary,root/'capture',20,12,store=db,pipeline_factory=factory)
            self.assertEqual(calls,[])
            self.assertIn('saved.wav',(root/'capture/events.jsonl').read_text())
            self.assertEqual(db.meetings()[0]['status'],'provisional');db.close()
    def test_stop_times_out_when_capture_ignores_interrupt_and_keeps_stdout_open(self):
        import signal,time
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as t:
            root=Path(t); ready=root/'ready'; binary=root/'recorder'
            binary.write_text('#!/usr/bin/env python3\nimport signal,time\nfrom pathlib import Path\nsignal.signal(signal.SIGINT,signal.SIG_IGN)\nPath('+repr(str(ready))+').write_text("ready")\ntime.sleep(1.5)\n')
            binary.chmod(0o700);db=Store(root/'db')
            def factory():
                deadline=time.monotonic()+3
                while not ready.exists():
                    if time.monotonic()>deadline:raise RuntimeError('recorder did not start')
                    time.sleep(.01)
                signal.getsignal(signal.SIGINT)(signal.SIGINT,None)
            started=time.monotonic()
            with patch('meeting_os.live.CAPTURE_STOP_GRACE_SECONDS',.2,create=True):
                with self.assertRaisesRegex(RuntimeError,'Capture did not exit'):
                    record(binary,root/'capture',10,1,store=db,pipeline_factory=factory)
            self.assertLess(time.monotonic()-started,1.2)
            self.assertEqual(db.meetings()[0]['status'],'incomplete')
            self.assertTrue((root/'capture/events.jsonl').exists());db.close()
    def test_completed_capture_receipt_uses_original_meeting_id(self):
        import json
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);binary=self.recorder(root,json.dumps({'event':'chunk','path':'fictional.wav','source':'system','start':0}))
            db=Store(root/'db');receipt=root/'completion.json'
            mid=record(binary,root/'capture',1,1,store=db,result_path=receipt)
            result=json.loads(receipt.read_text())
            self.assertEqual(result['meeting'],mid);self.assertEqual(result['finalized_chunks'],1)
            self.assertEqual(result['status'],'provisional');self.assertEqual(len(db.meetings()),1)
            self.assertEqual(receipt.stat().st_mode&0o777,0o600);db.close()
    def test_capture_failure_does_not_publish_completion_receipt(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);binary=self.recorder(root,'{"event":"error","message":"synthetic"}')
            db=Store(root/'db');receipt=root/'completion.json'
            with self.assertRaises(RuntimeError):record(binary,root/'capture',1,1,store=db,result_path=receipt)
            self.assertFalse(receipt.exists());self.assertEqual(db.meetings()[0]['status'],'incomplete');db.close()
    def test_receipt_write_failure_keeps_capture_and_single_meeting(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);binary=self.recorder(root,'{"event":"chunk","path":"fixture.wav","source":"system","start":0}')
            db=Store(root/'db')
            with self.assertRaises(OSError):record(binary,root/'capture',1,1,store=db,result_path=root/'missing-parent/receipt.json')
            self.assertTrue((root/'capture/events.jsonl').exists());self.assertEqual(len(db.meetings()),1)
            self.assertEqual(db.meetings()[0]['status'],'provisional');db.close()
