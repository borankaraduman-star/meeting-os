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
    # Reviewed behaviour changed: audio that reached disk is never withheld. A capture error still winds the
    # helper down at once, but the meeting now ends provisional with a receipt that carries the error, so the
    # app can finalize it instead of showing "Kayıt tamamlanamadı" over a folder full of chunks.
    def test_capture_error_stops_helper_and_hands_over_the_audio_it_saved(self):
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
                    record('/fake',root/'capture',60,12,store=db,pipeline_factory=warmed,result_path=receipt)
                self.assertLess(time.monotonic()-started,.6)
                self.assertEqual(helper.signals,[signal.SIGINT])
                self.assertEqual(helper.killed,not graceful)
                self.assertTrue(helper.closed);close.assert_called_once_with(None,None)
                self.assertEqual(handler.call_args.args,(signal.SIGINT,old_handler))
                journal=(root/'capture/events.jsonl').read_text()
                self.assertIn('saved.wav',journal);self.assertIn('tail.wav',journal)
                self.assertIn('device gone',journal)
                result=json.loads(receipt.read_text())
                self.assertEqual(result['status'],'provisional');self.assertIn('device gone',result['errors'])
                self.assertEqual(db.meetings()[0]['status'],'provisional');db.close()
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


# One fake helper covers every supervisor case: what it does is decided by the flag file the test writes
# and by whether the supervisor handed it --start-offset. It never touches ScreenCaptureKit.
FAKE_HELPER = '''#!/usr/bin/env python3
import json,os,signal,sys,time
from pathlib import Path
args=sys.argv
def opt(key,default=None): return args[args.index(key)+1] if key in args else default
out=Path(opt('--output'));out.mkdir(parents=True,exist_ok=True)
offset=float(opt('--start-offset','0') or 0)
plan=json.loads(Path(os.environ['FAKE_PLAN']).read_text())
runs=out/'runs';runs.write_text(str(int(runs.read_text() if runs.exists() else 0)+1))
run=int(runs.read_text())
journal=out/'capture-native.jsonl'
(out/('argv-%d.json'%run)).write_text(json.dumps(args[1:]))
# Same rule as the real helper: an existing journal may only be continued when the supervisor hands the
# folder back with --start-offset. Its value is irrelevant; 0.000 is a helper that died before its first chunk.
if journal.exists() and '--start-offset' not in args:
    sys.stderr.write('Choose a new recording folder\\n');sys.exit(1)
def emit(event):
    line=json.dumps(event)
    print(line,flush=True)
    with journal.open('a') as f: f.write(line+'\\n')
emit({'event':'started','start_offset':offset})
for n in range(plan['chunks'] if run==1 else plan.get('chunks_after',plan['chunks'])):
    start=offset+12.0*n
    path=out/('mic-%06d.wav'%(int(start)//12))
    path.write_bytes(b'audio')
    emit({'event':'chunk','source':'mic','path':str(path),'start':start,'duration':12.0})
if run>1: (out/'relaunched').write_text(str(offset))
if plan.get('error') and run<=plan.get('error_runs',99): emit({'event':'error','message':'device gone'})
if plan.get('exit') is not None and run<=plan.get('exit_runs',99): sys.exit(plan['exit'])
signal.signal(signal.SIGINT,lambda *a: sys.exit(0))
time.sleep(plan.get('sleep',30))
'''


class SupervisedHelperTests(unittest.TestCase):
    """The recording has to outlive the capture helper: it dies, it hangs, it runs out of chances."""
    def helper(self,root,plan):
        import json,os
        (root/'plan.json').write_text(json.dumps(plan))
        p=root/'fake-helper';p.write_text(FAKE_HELPER);p.chmod(0o700)
        os.environ['FAKE_PLAN']=str(root/'plan.json')
        return p
    def stopper(self,marker,timeout=10):
        """Deliver the recorder's own SIGINT handler once the fake helper says it is where the test wants it."""
        import signal,threading,time
        def wait():
            deadline=time.monotonic()+timeout
            while not marker.exists():
                if time.monotonic()>deadline: return
                time.sleep(.01)
            time.sleep(.05)
            handler=signal.getsignal(signal.SIGINT)
            if callable(handler): handler(signal.SIGINT,None)
        def factory():
            threading.Thread(target=wait,daemon=True).start()
        return factory
    def journal(self,root):
        import json
        out=[]
        for line in (root/'capture/events.jsonl').read_text().splitlines():
            try: out.append(json.loads(line))
            except ValueError: pass
        return out
    def test_dead_helper_is_relaunched_on_the_same_timeline(self):
        import json
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);binary=self.helper(root,{'chunks':2,'exit':3,'exit_runs':1,'chunks_after':1,'sleep':30})
            db=Store(root/'db');receipt=root/'receipt.json'
            with patch('meeting_os.live.RELAUNCH_MIN_UPTIME_SECONDS',0),patch('meeting_os.live.RELAUNCH_WAIT_SECONDS',.01):
                mid=record(binary,root/'capture',600,12,store=db,result_path=receipt,
                           pipeline_factory=self.stopper(root/'capture/relaunched'))
            events=self.journal(root)
            relaunch=[e for e in events if e.get('event')=='relaunch']
            self.assertEqual(len(relaunch),1)
            self.assertEqual(relaunch[0]['start_offset'],24.0)   # two 12 s chunks are already on disk
            self.assertEqual(relaunch[0]['reason'],'exit')
            self.assertEqual([e['start'] for e in events if e.get('event')=='chunk'],[0.0,12.0,24.0])
            self.assertEqual((root/'capture/relaunched').read_text(),'24.0')
            self.assertEqual(db.meetings()[0]['status'],'provisional')   # it recovered: not incomplete
            self.assertEqual(json.loads(receipt.read_text())['relaunches'],1)
            self.assertEqual(json.loads(receipt.read_text())['finalized_chunks'],3)
            self.assertEqual(db.meetings()[0]['id'],mid);db.close()
    def test_silent_but_alive_helper_is_killed_and_relaunched(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);binary=self.helper(root,{'chunks':0,'chunks_after':1,'sleep':30})
            db=Store(root/'db')
            with patch('meeting_os.live.RELAUNCH_MIN_UPTIME_SECONDS',0),patch('meeting_os.live.RELAUNCH_WAIT_SECONDS',.01),\
                 patch('meeting_os.live.STALL_MARGIN_SECONDS',.1),patch('meeting_os.live.CAPTURE_STOP_GRACE_SECONDS',.5):
                record(binary,root/'capture',600,.1,store=db,pipeline_factory=self.stopper(root/'capture/relaunched'))
            relaunch=[e for e in self.journal(root) if e.get('event')=='relaunch']
            self.assertEqual([e['reason'] for e in relaunch],['stall'])
            self.assertEqual(relaunch[0]['start_offset'],0.0)   # nothing was captured, so nothing is skipped
            # The regression: `if offset:` is false at 0.0, so no --start-offset was passed and the helper
            # refused the folder it had already written a journal into — the meeting could never be relaunched.
            import json as _json
            self.assertIn('--start-offset',_json.loads((root/'capture/argv-2.json').read_text()))
            argv=_json.loads((root/'capture/argv-2.json').read_text())
            self.assertEqual(argv[argv.index('--start-offset')+1],'0.000')
            self.assertNotIn('--start-offset',_json.loads((root/'capture/argv-1.json').read_text()))   # first launch is not a continuation
            self.assertTrue((root/'capture/relaunched').exists())
            self.assertEqual(db.meetings()[0]['status'],'provisional');db.close()
    # Reviewed behaviour changed: an exhausted relaunch budget with audio on disk used to raise, so no receipt
    # was written and nothing ever picked the meeting up again. The complaint now rides the receipt instead.
    def test_exhausted_relaunch_budget_keeps_the_audio_and_hands_it_over(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);binary=self.helper(root,{'chunks':1,'chunks_after':0,'exit':4})
            db=Store(root/'db');receipt=root/'receipt.json'
            with patch('meeting_os.live.RELAUNCH_MIN_UPTIME_SECONDS',0),patch('meeting_os.live.RELAUNCH_WAIT_SECONDS',.01),\
                 patch('meeting_os.live.RELAUNCH_LIMIT',2):
                record(binary,root/'capture',600,12,store=db,result_path=receipt)
            self.assertEqual(len([e for e in self.journal(root) if e.get('event')=='relaunch']),2)
            self.assertEqual(db.meetings()[0]['status'],'provisional')
            import json as _json;result=_json.loads(receipt.read_text())
            self.assertEqual(result['status'],'provisional');self.assertEqual(result['finalized_chunks'],1)
            self.assertTrue(any('2 kez yeniden başlatıldı' in e for e in result['errors']))
            self.assertEqual((root/'capture/mic-000000.wav').read_bytes(),b'audio')   # captured audio is never touched
            self.assertEqual(len([e for e in self.journal(root) if e.get('event')=='chunk']),1);db.close()
    def test_startup_failure_is_reported_instead_of_relaunched(self):
        # A helper that dies in its first seconds is failing at startup; five silent retries would only bury
        # the permission message the owner has to read.
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);binary=self.helper(root,{'chunks':0,'error':True,'exit':1})
            db=Store(root/'db')
            with self.assertRaisesRegex(RuntimeError,'device gone'):
                record(binary,root/'capture',600,12,store=db)
            self.assertEqual([e for e in self.journal(root) if e.get('event')=='relaunch'],[])
            self.assertEqual(db.meetings()[0]['status'],'incomplete');db.close()
