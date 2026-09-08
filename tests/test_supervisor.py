import os,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch

class SupervisorTests(unittest.TestCase):
    def test_timeout_reaps_owned_child(self):
        from meeting_os.supervisor import run_guarded
        with tempfile.TemporaryDirectory() as t:
            pidfile=Path(t)/'pid'
            with self.assertRaisesRegex(RuntimeError,'süre'):
                run_guarded([sys.executable,'-c',f'import os,time;open({str(pidfile)!r},"w").write(str(os.getpid()));time.sleep(10)'],timeout=.4)
            with self.assertRaises(ProcessLookupError):os.kill(int(pidfile.read_text()),0)
    def test_pressure_prevents_launch(self):
        from meeting_os.supervisor import run_guarded
        with patch('meeting_os.supervisor.check_pressure',side_effect=RuntimeError('pressure')),patch('meeting_os.supervisor.subprocess.Popen') as launch:
            with self.assertRaisesRegex(RuntimeError,'pressure'):run_guarded(['unused'])
            launch.assert_not_called()
    def test_success_and_nonzero_exit(self):
        from meeting_os.supervisor import run_guarded
        run_guarded([sys.executable,'-c','print("ok")'])
        with self.assertRaisesRegex(RuntimeError,'exit=3'):run_guarded([sys.executable,'-c','import sys;sys.exit(3)'])
    def test_isolated_timeout_stops_descendant(self):
        import time
        from meeting_os.supervisor import run_guarded
        with tempfile.TemporaryDirectory() as t:
            pidfile=Path(t)/'child'
            script='import subprocess,sys,time; p=subprocess.Popen([sys.executable,"-c","import time;time.sleep(10)"]);open('+repr(str(pidfile))+',"w").write(str(p.pid));time.sleep(10)'
            with self.assertRaisesRegex(RuntimeError,'süre'):run_guarded([sys.executable,'-c',script],timeout=.5,isolated=True)
            pid=int(pidfile.read_text());time.sleep(.1)
            state=__import__('subprocess').run(['/bin/ps','-o','stat=','-p',str(pid)],capture_output=True,text=True).stdout.strip()
            self.assertTrue(not state or state.startswith('Z'),state)
    def test_cancellation_stops_worker_without_replacing_signal_handlers(self):
        import signal
        from meeting_os.supervisor import run_guarded
        previous=signal.getsignal(signal.SIGINT)
        with self.assertRaisesRegex(RuntimeError,'durduruldu'):
            run_guarded([sys.executable,'-c','import time;time.sleep(10)'],isolated=True,handle_signals=False,cancel_requested=lambda:True)
        self.assertIs(signal.getsignal(signal.SIGINT),previous)
    def test_killed_supervisor_does_not_leave_worker_running(self):
        import subprocess,time,signal
        with tempfile.TemporaryDirectory() as t:
            pidfile=Path(t)/'pid'
            worker='import os,time;open('+repr(str(pidfile))+',"w").write(str(os.getpid()));time.sleep(30)'
            script='from meeting_os.supervisor import run_guarded;import sys;run_guarded([sys.executable,"-c",'+repr(worker)+'],isolated=True)'
            parent=subprocess.Popen([sys.executable,'-c',script])
            try:
                deadline=time.monotonic()+5
                while not pidfile.exists():
                    if time.monotonic()>deadline:self.fail('worker startup timeout')
                    time.sleep(.02)
                pid=int(pidfile.read_text());parent.kill();parent.wait()
                deadline=time.monotonic()+3
                while True:
                    state=subprocess.run(['/bin/ps','-o','stat=','-p',str(pid)],capture_output=True,text=True).stdout.strip()
                    if not state or state.startswith('Z'):break
                    if time.monotonic()>deadline:self.fail('orphan worker still running')
                    time.sleep(.05)
            finally:
                if parent.poll() is None:parent.kill();parent.wait()

    def test_output_stream_separates_stdout_and_failure_stderr(self):
        from meeting_os.supervisor import run_guarded
        with tempfile.TemporaryFile() as output:
            run_guarded([sys.executable,'-c','import sys;print("result");print("diagnostic",file=sys.stderr)'],output_stream=output)
            output.seek(0)
            self.assertEqual(output.read(),b'result\n')
        with tempfile.TemporaryFile() as output:
            with self.assertRaisesRegex(RuntimeError,'diagnostic'):
                run_guarded([sys.executable,'-c','import sys;print("partial");print("diagnostic",file=sys.stderr);sys.exit(3)'],output_stream=output)
            output.seek(0)
            self.assertEqual(output.read(),b'partial\n')

    def test_native_failure_details_can_be_excluded(self):
        from meeting_os.supervisor import run_guarded, ChildFailure
        with self.assertRaises(ChildFailure) as caught:
            run_guarded([sys.executable,'-c','import sys;print("PRIVATE_TRANSCRIPT",file=sys.stderr);sys.exit(3)'],failure_details=False)
        self.assertNotIn('PRIVATE_TRANSCRIPT',str(caught.exception))
        self.assertEqual(caught.exception.code,3)
    def test_failure_callback_runs_after_reaping(self):
        from meeting_os.supervisor import run_guarded
        called=[]
        def on_failure(pid):
            with self.assertRaises(ProcessLookupError):os.kill(pid,0)
            called.append(pid)
        with self.assertRaisesRegex(RuntimeError,'süre'):
            run_guarded([sys.executable,'-c','import time;time.sleep(10)'],timeout=.2,isolated=True,on_failure=on_failure)
        self.assertEqual(len(called),1)
    def test_success_returns_sampled_footprint_and_elapsed(self):
        from meeting_os.supervisor import run_guarded
        with patch('meeting_os.supervisor.footprint',return_value=64*1024**2):
            result=run_guarded([sys.executable,'-c','import time;time.sleep(.2)'])
        self.assertEqual(result['peak_footprint_bytes'],128*1024**2)
        self.assertGreater(result['samples'],0);self.assertGreater(result['elapsed_seconds'],0)

    @unittest.skipUnless(sys.platform == 'darwin', 'Darwin protected diagnostic helpers')
    def test_nested_monitoring_does_not_fail_on_protected_helpers(self):
        from meeting_os.supervisor import run_guarded
        # A real isolated worker repeatedly probes resources while its parent
        # accounts the tree. Protected ps/sysctl helpers must not look like
        # unmeasurable inference processes (the observed EPERM failure).
        code="from meeting_os.resources import check_pressure,physical_memory; import time;\nfor _ in range(20): check_pressure(); physical_memory(); time.sleep(.02)"
        result=run_guarded([sys.executable,'-c',code],timeout=10,isolated=True)
        self.assertGreater(result['samples'],0)

    def test_failure_telemetry_is_numeric_and_does_not_expose_command(self):
        import contextlib,io,json
        from meeting_os.supervisor import run_guarded
        stderr=io.StringIO()
        with contextlib.redirect_stderr(stderr),self.assertRaises(RuntimeError):
            run_guarded([sys.executable,'-c','import time; secret="PRIVATE_COMMAND"; time.sleep(10)'],timeout=.15)
        rows=[json.loads(line) for line in stderr.getvalue().splitlines() if line.startswith('{')]
        event=rows[-1]['supervisor_failure']
        self.assertEqual(event['kind'],'JobTimeoutError')
        self.assertGreaterEqual(event['elapsed_seconds'],.15)
        self.assertNotIn('PRIVATE_COMMAND',stderr.getvalue())
