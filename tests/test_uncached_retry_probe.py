import importlib.util,json,unittest
from pathlib import Path
from unittest.mock import Mock,patch

class UncachedRetryProbeTests(unittest.TestCase):
 def test_failed_worker_marks_only_requested_meeting_and_propagates_failure(self):
  path=Path(__file__).resolve().parents[1]/'scripts/probe-uncached-retry.py'
  spec=importlib.util.spec_from_file_location('uncached_retry_probe_test',path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
  db=Mock();db.meetings.return_value=[{'id':mid,'metadata':json.dumps({'worker_pid':42})} for mid in ('target','unrelated')]
  def fail(*args,**kwargs):kwargs['on_failure'](42);raise RuntimeError('worker failed')
  with patch('sys.platform','darwin'),patch('sys.argv',['probe','--meeting','target']),patch('meeting_os.resources.check_pressure'),patch.object(module.subprocess,'check_output',return_value=''),patch('meeting_os.supervisor.run_guarded',side_effect=fail),patch('meeting_os.store.Store',return_value=db),patch('meeting_os.recovery.mark_interrupted') as mark:
   with self.assertRaisesRegex(RuntimeError,'worker failed'):module.main()
  mark.assert_called_once_with(db,'target');db.close.assert_called_once()
