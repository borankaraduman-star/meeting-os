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
