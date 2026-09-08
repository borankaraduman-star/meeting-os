import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch

class DiagnosticsTests(unittest.TestCase):
    def test_allowlist_excludes_private_values_and_invalid_numbers(self):
        from meeting_os.diagnostics import sanitize
        secret='PRIVATE name transcript /Users/private/token https://signed.example/?token=SECRET'
        report=sanitize({'app_version':secret,'python_version':'3.12.14','macos_version':'26.5','architecture':secret,
            'memory':{'physical_gib':16,'pressure':'normal','collector_footprint_mib':True},'disk':{'free_gib':float('nan')},
            'progress':{'stage':secret,'source':secret,'current':secret,'total':10,'updated_at':secret},
            'error':secret,'metadata':{'secret':secret},'transcript':secret})
        encoded=json.dumps(report,allow_nan=False)
        self.assertNotIn('PRIVATE',encoded);self.assertNotIn('SECRET',encoded);self.assertNotIn('/Users',encoded)
        self.assertIsNone(report['memory']['collector_footprint_mib']);self.assertIsNone(report['disk']['free_gib'])
        self.assertEqual(report['progress']['stage'],'unknown');self.assertEqual(report['python_version'],'3.12.14')
    def test_progress_is_bounded_and_does_not_follow_symlinks_or_fifo(self):
        import os
        from meeting_os.diagnostics import read_progress
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);path=root/'progress';path.write_text(json.dumps({'stage':'vad','text':'PRIVATE'}))
            self.assertEqual(read_progress(path)['stage'],'vad')
            link=root/'link';link.symlink_to(path);self.assertEqual(read_progress(link),{})
            fifo=root/'fifo';os.mkfifo(fifo);self.assertEqual(read_progress(fifo),{})
            path.write_text('x'*20000);self.assertEqual(read_progress(path),{})
    def test_export_is_private_and_never_overwrites(self):
        from meeting_os.diagnostics import export_report
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);path=root/'report.json'
            export_report(path,{'progress':{'stage':'vad'},'secret':'PRIVATE'})
            self.assertEqual(path.stat().st_mode&0o777,0o600)
            self.assertNotIn('PRIVATE',path.read_text());before=path.read_bytes()
            with self.assertRaises(FileExistsError):export_report(path,{})
            self.assertEqual(before,path.read_bytes())
    def test_collect_does_not_open_meeting_database(self):
        from meeting_os.diagnostics import collect
        with tempfile.TemporaryDirectory() as t,patch('meeting_os.store.Store') as store:
            report=collect(Path(t))
            store.assert_not_called();self.assertEqual(report['schema_version'],1)
            self.assertNotIn(str(t),json.dumps(report))
    def test_export_refuses_symlink_and_sanitization_is_idempotent(self):
        from meeting_os.diagnostics import sanitize,export_report
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);target=root/'keep';target.write_text('KEEP');link=root/'report';link.symlink_to(target)
            with self.assertRaises(FileExistsError):export_report(link,{})
            self.assertEqual(target.read_text(),'KEEP')
            report=sanitize({'memory':{'physical_gib':16,'pressure':'normal'},'progress':{'stage':'vad','current':2,'total':5}})
            self.assertEqual(sanitize(report),report)
            self.assertEqual(list(root.glob('.meeting-os-diagnostics-*')),[])
    def test_cli_export_never_opens_database_or_sends_data(self):
        import contextlib,io
        from meeting_os.cli import main
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);path=root/'report.json';progress=root/'progress.json'
            progress.write_text(json.dumps({'stage':'transcribing','current':1,'total':2,'source':'mic','text':'PRIVATE','token':'SECRET'}))
            with patch('sys.argv',['meeting_os','--db',str(root/'must-not-exist.sqlite'),'diagnostics','--output',str(path),'--progress',str(progress)]),patch('meeting_os.store.Store') as store,contextlib.redirect_stdout(io.StringIO()) as output:
                main();store.assert_not_called()
            self.assertEqual(json.loads(output.getvalue()),{'diagnostics_saved':True})
            self.assertFalse((root/'must-not-exist.sqlite').exists())
            report=json.loads(path.read_text());self.assertEqual(report['progress']['stage'],'transcribing')
            self.assertNotIn('PRIVATE',path.read_text());self.assertNotIn('SECRET',path.read_text())
    def test_probe_failures_are_codes_without_raw_errors(self):
        from meeting_os.diagnostics import collect
        with patch('meeting_os.diagnostics.subprocess.check_output',side_effect=OSError('PRIVATE')),patch('meeting_os.supervisor.footprint',side_effect=RuntimeError('SECRET')),patch('meeting_os.diagnostics.shutil.disk_usage',side_effect=OSError('/private/path')):
            report=collect('/unused')
        encoded=json.dumps(report)
        for value in ('PRIVATE','SECRET','/private/path','/unused'):self.assertNotIn(value,encoded)
        self.assertIn('disk_unavailable',report['error_codes'])
    def test_stale_progress_is_labelled_without_exporting_timestamp(self):
        import os
        from meeting_os.diagnostics import collect
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);path=root/'progress';path.write_text(json.dumps({'stage':'transcribing','updated_at':1}))
            os.utime(path,(1,1))
            report=collect(root,path)
            self.assertEqual(report['progress']['freshness'],'stale')
            self.assertNotIn('updated_at',json.dumps(report))
    def test_cli_existing_destination_reports_error_without_traceback(self):
        import contextlib,io
        from meeting_os.cli import main
        with tempfile.TemporaryDirectory() as t:
            path=Path(t)/'keep.json';path.write_text('KEEP');errors=io.StringIO()
            with patch('sys.argv',['meeting_os','diagnostics','--output',str(path)]),contextlib.redirect_stderr(errors):
                with self.assertRaises(SystemExit) as caught:main()
            self.assertEqual(caught.exception.code,1);self.assertNotIn('Traceback',errors.getvalue())
            self.assertEqual(path.read_text(),'KEEP')
