import json
from pathlib import Path
import runpy
import tempfile
import unittest
from unittest.mock import patch
from meeting_os import resources, supervisor

run_soak = runpy.run_path(str(Path(__file__).resolve().parents[1]/'scripts/capture-soak.py'))['run_soak']

class FailureReasonTests(unittest.TestCase):
    def test_pressure_admission_reports_reason_without_spawning(self):
        with tempfile.TemporaryDirectory() as tmp, patch('meeting_os.resources.subprocess.check_output',return_value='2'),patch('meeting_os.resources.sys.platform','darwin'),patch('meeting_os.supervisor.subprocess.Popen') as spawn:
            report=run_soak(Path(tmp)/'run',5,'/unused')
            self.assertEqual(report['error_code'],'memory_pressure')
            spawn.assert_not_called()

    def test_unknown_failure_does_not_export_private_text(self):
        with tempfile.TemporaryDirectory() as tmp,patch.dict(run_soak.__globals__,{'run_guarded':lambda *a,**kw: (_ for _ in ()).throw(RuntimeError('private transcript /Users/person'))}):
            report=run_soak(Path(tmp)/'run',5,'/unused')
            self.assertNotIn('private',json.dumps(report))
            self.assertEqual(report['error_code'],'supervision_failed')

    def test_running_failures_keep_cleanup_and_exact_categories(self):
        class Child:
            pid=12345
            returncode=None
            waited=0
            def poll(self):return self.returncode
            def kill(self):self.returncode=-9
            def wait(self):self.waited+=1;return self.returncode
        cases=[('pressure',resources.MemoryPressureError),('probe',resources.ResourceProbeError),
               ('limit',supervisor.JobMemoryLimitError),('timeout',supervisor.JobTimeoutError),
               ('cancel',supervisor.JobCancelledError)]
        for mode,expected in cases:
            with self.subTest(mode=mode):
                child=Child()
                pressure=[None,resources.MemoryPressureError('private')] if mode=='pressure' else None
                with patch.object(supervisor,'check_pressure',side_effect=pressure),patch.object(supervisor,'physical_memory',return_value=16*resources.GIB),patch.object(supervisor.subprocess,'Popen',return_value=child),patch.object(supervisor,'footprint',side_effect=resources.ResourceProbeError('private') if mode=='probe' else None,return_value=3*resources.GIB if mode=='limit' else 1),patch.object(supervisor.time,'monotonic',side_effect=[0.,1.]),patch.object(supervisor,'close_lifeline'):
                    with self.assertRaises(expected):
                        supervisor.run_guarded(['/unused'],timeout=0 if mode=='timeout' else 100,cancel_requested=lambda:mode=='cancel')
                self.assertEqual(child.returncode,-9)
                self.assertGreaterEqual(child.waited,1)

    def test_report_allowlist_for_known_exceptions(self):
        cases=[(resources.MemoryPressureError,'memory_pressure'),(resources.ResourceProbeError,'resource_probe_failed'),
               (supervisor.JobMemoryLimitError,'memory_limit'),(supervisor.JobTimeoutError,'timeout'),
               (supervisor.JobCancelledError,'canceled'),(KeyboardInterrupt,'canceled')]
        for kind,code in cases:
            with self.subTest(kind=kind),tempfile.TemporaryDirectory() as tmp:
                def fail(*args,**kwargs):raise kind('secret content')
                with patch.dict(run_soak.__globals__,{'run_guarded':fail}):
                    report=run_soak(Path(tmp)/'run',5,'/unused')
                self.assertEqual(report['error_code'],code)
                self.assertNotIn('secret',json.dumps(report))

    def test_successful_worker_with_bad_journal_is_validation_failure(self):
        def bad_journal(*args,**kwargs):
            kwargs['output_stream'].write('not json\n')
            return {'samples':1}
        with tempfile.TemporaryDirectory() as tmp,patch.dict(run_soak.__globals__,{'run_guarded':bad_journal}):
            report=run_soak(Path(tmp)/'run',5,'/unused')
        self.assertEqual(report['error_code'],'validation_failed')

    def test_unreadable_pressure_is_not_reported_as_observed_pressure(self):
        with patch.object(resources.sys,'platform','darwin'),patch.object(resources.subprocess,'check_output',side_effect=OSError('private path')):
            with self.assertRaises(resources.ResourceProbeError):resources.check_pressure()
