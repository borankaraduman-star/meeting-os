import tempfile, unittest
from pathlib import Path
from meeting_os import probe

class ProbeTests(unittest.TestCase):
    def test_empty_data_dir_reports_only_environment_gaps(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'root'; data=Path(tmp)/'data'; root.mkdir()
            r=probe.run(root,data)
            keys={i['key'] for i in r['items']}
            self.assertTrue({'python','ffmpeg','capture_helper','database','data_writable','disk','api_key','glossary','reports'}<=keys)
            by={i['key']:i for i in r['items']}
            self.assertFalse(by['capture_helper']['ok']); self.assertEqual(by['capture_helper']['fix'],'sh scripts/build-capture.sh')
            self.assertTrue(by['database']['ok']); self.assertTrue(by['data_writable']['ok'])
            self.assertIn('capture_helper',r['failed']); self.assertFalse(r['ok'])
            self.assertTrue(probe.summary_line(r).startswith('Öz-test: '))
    def test_corrupt_database_is_reported_not_raised(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'root'; data=Path(tmp)/'data'; root.mkdir(); data.mkdir()
            (data/'meeting-os.sqlite').write_bytes(b'not a database at all'*100)
            r=probe.run(root,data); by={i['key']:i for i in r['items']}
            self.assertFalse(by['database']['ok']); self.assertIn('database',r['failed'])
    def test_summary_line_clean(self):
        self.assertEqual(probe.summary_line({'ok':True,'warnings':[],'failed':[]}),'Öz-test temiz')
