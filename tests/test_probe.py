import contextlib, tempfile, unittest
from unittest import mock
from pathlib import Path
from meeting_os import probe


class SandboxedProbe(unittest.TestCase):
    """No test may look at the real Mac or shell out. `SIGNING_MARKER` points at a temp path (the real one
    belongs to whoever runs the suite) and `subprocess.run` is stubbed, so `keychain_item_exists` can never
    reach `/usr/bin/security` and no probe can start the recorder helper."""
    def setUp(self):
        self.stack = contextlib.ExitStack(); self.addCleanup(self.stack.close)
        self.home = Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        self.marker = self.home/'signing-partition.ok'
        self.stack.enter_context(mock.patch.object(probe,'SIGNING_MARKER',self.marker))
        self.subprocess_run = self.stack.enter_context(
            mock.patch.object(probe.subprocess,'run',side_effect=AssertionError('a test must never shell out')))


class ProbeTests(SandboxedProbe):
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


class SigningPartitionTests(SandboxedProbe):
    """The marker scripts/fix-signing-prompts.sh leaves behind. Missing marker = update.sh refuses before it even
    merges, so this Mac can take no new version at all; nothing here may ever shell out to `security`."""
    def _with_marker(self, exists):
        """The marker itself; the temp path and the subprocess stub come from SandboxedProbe."""
        if exists: self.marker.write_text('ABCDEF0123 granted 2026-09-10 10:00:00\n')
        elif self.marker.exists(): self.marker.unlink()
        return contextlib.nullcontext()
    def test_missing_marker_is_an_error_with_an_absolute_command(self):
        with self._with_marker(False):
            item = probe.signing_partition_item('/Users/x/meeting-os')
            self.assertFalse(item['ok']); self.assertEqual(item['level'],'error')
            self.assertEqual(item['fix'],'sh /Users/x/meeting-os/scripts/fix-signing-prompts.sh')
            self.assertIn('güncelleme başlamadan durur',item['detail'])
            self.assertIn('1.2.41',item['detail'])   # running it back then wrote no file; it has to be run again
    def test_the_command_is_absolute_even_without_a_root(self):
        with self._with_marker(False):
            self.assertTrue(probe.signing_partition_item()['fix'].startswith('sh /'))
    def test_present_marker_passes(self):
        with self._with_marker(True):
            item = probe.signing_partition_item()
            self.assertTrue(item['ok']); self.assertNotIn('fix',item)
    def test_probe_run_fails_on_it_and_names_the_checkout(self):
        with self._with_marker(False), tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'root'; data=Path(tmp)/'data'; root.mkdir()
            r=probe.run(root,data)
            self.assertIn('signing_partition',r['failed'])
            self.assertNotIn('signing_partition',r['warnings'])
            self.assertIn('imzalama izni',probe.summary_line(r))
            by={i['key']:i for i in r['items']}
            self.assertEqual(by['signing_partition']['fix'],f'sh {root}/scripts/fix-signing-prompts.sh')
        with self._with_marker(True), tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'root'; data=Path(tmp)/'data'; root.mkdir()
            r=probe.run(root,data)
            self.assertNotIn('signing_partition',r['warnings']+r['failed'])
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
    def test_a_key_that_is_only_in_the_keychain_is_a_warning_not_a_missing_key(self):
        """Macs installed before 1.2.30 never got an openrouter.key file. Nothing is missing and nothing has to be
        typed again: the app copies the key across the first time it is opened."""
        import unittest.mock
        from meeting_os import openrouter
        class Found: returncode=0; stdout=''; stderr=''
        class Absent: returncode=44; stdout=''; stderr=''
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'root'; data=Path(tmp)/'data'; root.mkdir()
            missing=Path(tmp)/'openrouter.key'
            with unittest.mock.patch.object(openrouter,'KEY_CACHE',missing):
                with unittest.mock.patch.object(probe.subprocess,'run',return_value=Found()) as run:
                    by={i['key']:i for i in probe.run(root,data)['items']}
                self.assertFalse(by['api_key']['ok']); self.assertEqual(by['api_key']['level'],'warning')
                self.assertEqual(by['api_key']['fix'],probe.KEYCHAIN_HINT)
                query=[c.args[0] for c in run.call_args_list if 'find-generic-password' in c.args[0]][0]
                self.assertNotIn('-w',query)          # metadata only: macOS must never be given a reason to prompt
                self.assertIn(openrouter.KEYCHAIN_SERVICE,query)
                with unittest.mock.patch.object(probe.subprocess,'run',return_value=Absent()):
                    by={i['key']:i for i in probe.run(root,data)['items']}
                self.assertEqual(by['api_key']['level'],'error')
                self.assertIn('yok',by['api_key']['detail'])
    def test_the_keychain_query_never_raises_into_the_probe(self):
        import unittest.mock
        with unittest.mock.patch.object(probe.subprocess,'run',side_effect=OSError('yok')):
            self.assertFalse(probe.keychain_item_exists())
        with unittest.mock.patch.object(probe.subprocess,'run',side_effect=probe.subprocess.TimeoutExpired('security',5)):
            self.assertFalse(probe.keychain_item_exists())


class NightlyCheckTests(unittest.TestCase):
    def test_daily_probe_is_cached_for_a_day(self):
        import json
        from datetime import datetime, timezone, timedelta
        from meeting_os import reports
        # `daily_probe` runs the real `probe.run` against the real checkout, which starts the recorder helper's
        # self-test if it happens to be built. What is under test here is the cache, not the probe.
        fake={'ok':True,'failed':[],'warnings':[],'at':datetime.now(timezone.utc).isoformat()}
        with mock.patch.object(probe,'run',return_value=fake) as ran, tempfile.TemporaryDirectory() as tmp:
            data=Path(tmp); (data/'settings.json').write_text('{"share_reports": false}')
            first=reports.daily_probe(data, now=datetime.now(timezone.utc))
            self.assertIn('summary',first); self.assertTrue((data/reports.PROBE_CACHE).exists())
            stamped=json.loads((data/reports.PROBE_CACHE).read_text()); stamped['summary']='cached'; (data/reports.PROBE_CACHE).write_text(json.dumps(stamped))
            self.assertEqual(reports.daily_probe(data)['summary'],'cached')
            later=reports.daily_probe(data, now=datetime.now(timezone.utc)+timedelta(hours=25))
            self.assertNotEqual(later['summary'],'cached')
            self.assertEqual(ran.call_count,2)   # once for the first run, once when the cache expired
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
