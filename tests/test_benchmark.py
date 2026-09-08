import unittest
from meeting_os.benchmark import validate_manifest,identity_metrics
class BenchmarkTests(unittest.TestCase):
    def test_leakage_rejected(self):
        with self.assertRaisesRegex(ValueError,'leakage'):
            validate_manifest({'kind':'real','cases':[{'session':'a','reference':'a.json'}],'enrollment':[{'session':'a'}]})
    def test_identity_false_accept(self):
        m=identity_metrics([(0,2,'stranger')],[{'start':0,'end':2,'speaker_name':'Boran'}],{'Boran'})
        self.assertEqual(m['unknown_false_accept_rate'],1)
    def test_missing_identity_not_zero(self):
        self.assertIsNone(identity_metrics([],[],set())['false_reject_rate'])

class ResourceStopTests(unittest.TestCase):
    def test_resource_exit_defers_later_cases_and_configs_without_creating_jobs(self):
        import json,tempfile
        from pathlib import Path
        from unittest.mock import patch
        from subprocess import CompletedProcess
        from meeting_os.benchmark import benchmark
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); (root/'ref.json').write_text('{"text":"test","entity_universe":["test","Boran"]}')
            manifest={'kind':'real','cases':[{'id':str(i),'session':str(i),'audio':'unused.wav','reference':'ref.json'} for i in range(2)],'configs':[{'name':'a'},{'name':'b'}]}
            (root/'manifest.json').write_text(json.dumps(manifest))
            def worker(cmd, **kwargs):
                target=Path(cmd[cmd.index('--output')+1])
                if target.parent.name=='00-00':
                    target.write_text(json.dumps({'segments':[{'text':'test'}],'duration':1,'peak_rss_bytes':100,'embedding_model':'fixture'}))
                    return CompletedProcess(cmd,0)
                return CompletedProcess(cmd,75)
            with patch('meeting_os.benchmark.subprocess.run',side_effect=worker):
                result=benchmark(root/'manifest.json',root/'out')
            report=json.loads((root/'out/report.json').read_text())
            self.assertEqual(result['runs'],2)
            self.assertEqual(result['failed'],1)
            self.assertEqual(result['deferred'],2)
            self.assertEqual([r['status'] for r in report['results']],['ok','failed','deferred','deferred'])
            self.assertFalse((root/'out/01-00').exists())
            self.assertIsNone(report['results'][2]['exit_code'])
            self.assertNotIn('wer',report['results'][2])
            self.assertEqual(report['results'][0]['wer'],0)
            self.assertEqual(report['results'][0]['entity_precision'],1)
            self.assertEqual(report['results'][0]['entity_universe_size'],2)
            self.assertIn('Entity precision (closed set)',(root/'out/REPORT.md').read_text())
            self.assertTrue((root/'out/00-00/result.json').exists())

    def test_cli_resource_failure_has_distinct_exit_code(self):
        from unittest.mock import patch
        from meeting_os.cli import main
        from meeting_os.resources import MemoryPressureError, ResourceProbeError
        from meeting_os.supervisor import JobMemoryLimitError
        for kind in (MemoryPressureError,ResourceProbeError,JobMemoryLimitError):
            with self.subTest(kind=kind.__name__), patch('sys.argv',['meeting-os','transcribe','unused.wav']), patch('meeting_os.supervisor.run_guarded',side_effect=kind('resource guard')):
                with self.assertRaises(SystemExit) as exc:main()
                self.assertEqual(exc.exception.code,75)

    def test_ordinary_case_failure_does_not_defer_other_cases(self):
        import json,tempfile
        from pathlib import Path
        from unittest.mock import patch
        from subprocess import CompletedProcess
        from meeting_os.benchmark import benchmark
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); (root/'ref.json').write_text('{"text":"test"}')
            (root/'manifest.json').write_text(json.dumps({'kind':'real','cases':[{'id':str(i),'session':str(i),'audio':'unused.wav','reference':'ref.json'} for i in range(2)],'configs':[{'name':'a'}]}))
            with patch('meeting_os.benchmark.subprocess.run',return_value=CompletedProcess([],1)):
                result=benchmark(root/'manifest.json',root/'out')
            self.assertEqual((result['runs'],result['failed'],result['deferred']),(2,2,0))
            self.assertTrue((root/'out/00-01/meeting.sqlite').exists())
