import json
from pathlib import Path
import runpy
import tempfile
import unittest

run_soak = runpy.run_path(str(Path(__file__).resolve().parents[1]/'scripts/capture-soak.py'))['run_soak']


class CaptureSoakTests(unittest.TestCase):
    def test_owned_fake_capture_metrics_and_preserved_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            worker = root/'worker'
            worker.write_text('#!/bin/sh\nprintf \'{"event":"chunk","source":"mic","start":0,"duration":1}\\n\'\n')
            worker.chmod(0o700)
            report = run_soak(root/'ok', 5, worker)
            self.assertEqual(report['status'], 'captured_pending_acceptance')
            self.assertEqual(report['timeline']['sources']['mic']['covered_seconds'], 1)
            self.assertEqual(report['timeline']['sources']['system']['chunks'], 0)
            worker.write_text('#!/bin/sh\nprintf \'{"event":"error","message":"private detail"}\\n\'\nexit 1\n')
            failed = run_soak(root/'bad', 5, worker)
            self.assertEqual(failed['status'], 'failed')
            self.assertEqual(failed['error_code'], 'capture_failed')
            self.assertNotIn('private detail', json.dumps(failed))
            self.assertIn('private detail', (root/'bad/worker.jsonl').read_text())
            with self.assertRaises(FileExistsError): run_soak(root/'bad', 5, worker)
