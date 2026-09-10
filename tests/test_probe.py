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


class SigningPartitionTests(unittest.TestCase):
    """The marker scripts/fix-signing-prompts.sh leaves behind. Missing marker = a codesign password dialog on
    the next update, so the probe warns; nothing here may ever shell out to `security`."""
    def _with_marker(self, exists):
        import contextlib, unittest.mock
        tmp = tempfile.TemporaryDirectory()
        marker = Path(tmp.name)/'signing-partition.ok'
        if exists: marker.write_text('ABCDEF0123 granted 2026-09-10 10:00:00\n')
        patch = unittest.mock.patch.object(probe,'SIGNING_MARKER',marker)
        stack = contextlib.ExitStack(); stack.enter_context(tmp); stack.enter_context(patch)
        return stack
    def test_missing_marker_is_a_warning_not_an_error(self):
        with self._with_marker(False):
            item = probe.signing_partition_item()
            self.assertFalse(item['ok']); self.assertEqual(item['level'],'warning')
            self.assertEqual(item['fix'],'sh scripts/fix-signing-prompts.sh')
            self.assertIn('fix-signing-prompts.sh',item['detail'])
            self.assertIn('parola',item['detail'])
    def test_present_marker_passes(self):
        with self._with_marker(True):
            item = probe.signing_partition_item()
            self.assertTrue(item['ok']); self.assertNotIn('fix',item)
    def test_probe_run_lists_the_check_and_only_warns(self):
        with self._with_marker(False), tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'root'; data=Path(tmp)/'data'; root.mkdir()
            r=probe.run(root,data)
            self.assertIn('signing_partition',r['warnings'])
            self.assertNotIn('signing_partition',r['failed'])
            self.assertIn('imzalama izni (uyarı)',probe.summary_line(r))
        with self._with_marker(True), tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'root'; data=Path(tmp)/'data'; root.mkdir()
            r=probe.run(root,data)
            self.assertNotIn('signing_partition',r['warnings'])
    def test_api_key_detail_names_the_key_file_not_the_keychain(self):
        import unittest.mock
        from meeting_os import openrouter
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'root'; data=Path(tmp)/'data'; root.mkdir()
            cache=Path(tmp)/'openrouter.key'; cache.write_text('sk-test\n')
            with unittest.mock.patch.object(openrouter,'KEY_CACHE',cache):
                by={i['key']:i for i in probe.run(root,data)['items']}
            self.assertTrue(by['api_key']['ok'])
            self.assertIn('openrouter.key',by['api_key']['detail'])
            self.assertNotIn('Keychain',by['api_key']['detail'])


class NightlyCheckTests(unittest.TestCase):
    def test_daily_probe_is_cached_for_a_day(self):
        import json
        from datetime import datetime, timezone, timedelta
        from meeting_os import reports
        with tempfile.TemporaryDirectory() as tmp:
            data=Path(tmp); (data/'settings.json').write_text('{"share_reports": false}')
            first=reports.daily_probe(data, now=datetime.now(timezone.utc))
            self.assertIn('summary',first); self.assertTrue((data/reports.PROBE_CACHE).exists())
            stamped=json.loads((data/reports.PROBE_CACHE).read_text()); stamped['summary']='cached'; (data/reports.PROBE_CACHE).write_text(json.dumps(stamped))
            self.assertEqual(reports.daily_probe(data)['summary'],'cached')
            later=reports.daily_probe(data, now=datetime.now(timezone.utc)+timedelta(hours=25))
            self.assertNotEqual(later['summary'],'cached')
    def test_alerts_from_heartbeats(self):
        from datetime import datetime, timezone, timedelta
        from meeting_os.reports import alerts
        now=datetime.now(timezone.utc)
        hosts={'eski':{'reports':2,'errors':0,'heartbeat':{'last_seen':(now-timedelta(days=5)).isoformat(),'free_disk':50*1024**3}},
               'dolu':{'reports':0,'errors':0,'heartbeat':{'last_seen':now.isoformat(),'free_disk':1*1024**3,'probe':{'ok':False,'summary':'Öz-test: kayıt yardımcısı'},'cloud_blocked':2}},
               'kayitta':{'reports':0,'errors':0,'heartbeat':{'last_seen':now.isoformat(),'free_disk':50*1024**3},'recording':{'last_chunk_age_seconds':120}},
               'temiz':{'reports':1,'errors':0,'heartbeat':{'last_seen':now.isoformat(),'free_disk':50*1024**3,'probe':{'ok':True,'warnings':[]},'cloud_blocked':0}},
               'nabizsiz':{'reports':3,'errors':1}}
        keys={(a['host'],a['key']) for a in alerts(hosts,now=now)}
        self.assertEqual(keys,{('eski','stale'),('dolu','disk'),('dolu','probe'),('dolu','cloud'),('kayitta','recording'),('nabizsiz','no_heartbeat'),('nabizsiz','errors')})
