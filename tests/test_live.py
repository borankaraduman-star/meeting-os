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
