import json,os,tempfile,unittest
from datetime import datetime,timedelta,timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from meeting_os import errors as E

NOW=datetime(2026,9,10,12,0,tzinfo=timezone.utc)


def ips(root,name,*,process='MeetingOS',incident='INC-1',exception='EXC_BAD_ACCESS',signal='SIGSEGV',stamp='2026-09-10 11:59:00.00 +0300'):
    """A minimal report in the real `.ips` shape: one JSON header line, then a JSON body. Structure only —
    the fields this parser reads and nothing copied from a real crash."""
    header={'app_name':process,'app_version':'1.2.63','build_version':'1.2.63','bug_type':'309',
            'incident_id':incident,'name':process,'os_version':'macOS 26.5.2 (25F84)','timestamp':stamp}
    body={'procName':process,'incident':incident,'captureTime':stamp,'faultingThread':0,
          'exception':{'type':exception,'signal':signal,'codes':'0x1, 0x2'},
          'termination':{'namespace':'SIGNAL','indicator':'Segmentation fault: 11','byProc':'exc handler','byPid':1},
          'threads':[{'id':1,'triggered':True,'frames':[
              {'imageOffset':7896,'symbol':'MeetingOS.Model.refresh()','symbolLocation':4,'imageIndex':0},
              {'imageOffset':111,'symbol':'closure #1 in Model.launch(_:)','symbolLocation':1,'imageIndex':0},
              {'imageOffset':222,'symbol':'objc_msgSend','symbolLocation':2,'imageIndex':1},
              {'imageOffset':333,'imageIndex':0}]},
              {'id':2,'frames':[{'imageOffset':1,'symbol':'never','imageIndex':0}]}],
          'usedImages':[{'name':process,'path':f'/Users/gizli/build/{process}','base':1,'size':2,'uuid':'u','arch':'arm64'},
                        {'name':'libobjc.A.dylib','path':'/usr/lib/libobjc.A.dylib','base':3,'size':4,'uuid':'v','arch':'arm64e'}]}
    path=Path(root)/name
    path.write_text(json.dumps(header)+'\n'+json.dumps(body,indent=1),encoding='utf-8')
    return path


class JournalTests(unittest.TestCase):
    def test_a_line_is_private_redacted_bounded_and_carries_the_version(self):
        with tempfile.TemporaryDirectory() as tmp:
            data=Path(tmp)
            entry=E.record('job','Çöktü /Users/ayse/Library/gizli\nikinci satır '+'x'*500,
                           context={'command':'finalize','meeting':E.meeting_key('m-1'),'exit':9},data_dir=data,now=NOW)
            self.assertEqual(entry['kind'],'job')
            self.assertNotIn('/Users/ayse',entry['message']);self.assertIn('/Users/…',entry['message'])
            self.assertNotIn('\n',entry['message']);self.assertEqual(len(entry['message']),E.MESSAGE_LIMIT)
            self.assertEqual(entry['context']['command'],'finalize');self.assertEqual(entry['context']['exit'],9)
            self.assertEqual(len(entry['context']['meeting']),8)
            self.assertTrue(entry['version'])
            journal=E.journal_path(data)
            self.assertEqual(journal.stat().st_mode&0o777,0o600)
            self.assertEqual(len(journal.read_text(encoding='utf-8').splitlines()),1)
    def test_an_unknown_kind_and_a_content_shaped_context_are_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            entry=E.record('transcript','bir hata',data_dir=tmp,
                           context={'transcript':{'text':'İpek yarın rollout dedi'},'frames':['a','b'],'ok':True,'n':1.5})
            self.assertEqual(entry['kind'],'ui')   # not in KINDS: never a new bucket, never a crash
            self.assertNotIn('transcript',entry['context'])   # a dict is dropped whole, not trimmed
            self.assertEqual(entry['context'],{'frames':['a','b'],'ok':True,'n':1.5})
    def test_the_same_event_twice_in_ten_minutes_is_one_line(self):
        with tempfile.TemporaryDirectory() as tmp:
            data=Path(tmp)
            self.assertIsNotNone(E.record('ui','Aynı hata',data_dir=data,now=NOW))
            self.assertIsNone(E.record('ui','Aynı hata',data_dir=data,now=NOW+timedelta(minutes=9)))
            self.assertIsNotNone(E.record('ui','Aynı hata',data_dir=data,now=NOW+timedelta(minutes=11)))
            self.assertIsNotNone(E.record('cloud','Aynı hata',data_dir=data,now=NOW+timedelta(minutes=11)))   # a different kind is a different event
            self.assertEqual(len(E.entries(data)),3)
    def test_the_journal_rotates_at_a_megabyte_and_keeps_one_generation(self):
        with tempfile.TemporaryDirectory() as tmp:
            data=Path(tmp);journal=E.journal_path(data)
            journal.write_text('x'*(E.MAX_BYTES+1),encoding='utf-8')
            E.record('ui','döndükten sonra',data_dir=data,now=NOW)
            self.assertTrue((data/E.ROTATED_FILE).is_file())
            self.assertEqual(len(E.entries(data)),1)
            self.assertLess(journal.stat().st_size,E.MAX_BYTES)
    def test_summary_counts_a_day_and_clear_leaves_no_journal(self):
        with tempfile.TemporaryDirectory() as tmp:
            data=Path(tmp)
            E.record('cloud','eski',data_dir=data,now=NOW-timedelta(hours=30))
            for i in range(3): E.record('ui',f'yeni {i}',data_dir=data,now=NOW-timedelta(minutes=i))
            E.record('crash','MeetingOS çöktü · EXC_BAD_ACCESS',data_dir=data,now=NOW-timedelta(minutes=5))
            summary=E.summary(data,now=NOW)
            self.assertEqual(summary['last_24h'],{'ui':3,'crash':1})   # the 30-hour-old cloud line is outside the window
            self.assertEqual(summary['crashes_24h'],1)
            self.assertEqual(len(summary['last']),5)
            self.assertEqual(summary['last'][0]['kind'],'crash')       # newest first
            self.assertEqual(set(summary['last'][0]),{'time','kind','message'})
            self.assertEqual(sorted(E.clear(data)),[E.JOURNAL_FILE])
            self.assertEqual(E.entries(data),[]);self.assertEqual(E.summary(data,now=NOW)['last_24h'],{})
    def test_a_broken_journal_and_an_unwritable_folder_never_raise(self):
        with tempfile.TemporaryDirectory() as tmp:
            data=Path(tmp);E.journal_path(data).write_text('bozuk satır\n{"kind":"nope"}\n',encoding='utf-8')
            self.assertEqual(E.entries(data),[])
            self.assertEqual(E.summary(data,now=NOW)['last_24h'],{})
            self.assertIsNone(E.record('ui','',data_dir=data))
        self.assertIsNone(E.record('ui','bir yere yazılamaz',data_dir='/dev/null/yok'))


class CrashTests(unittest.TestCase):
    def test_a_report_becomes_one_line_with_our_frames_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            reports=Path(tmp)/'DiagnosticReports';reports.mkdir()
            data=Path(tmp)/'data';data.mkdir()
            ips(reports,'MeetingOS-2026-09-10-115900.ips')
            ips(reports,'MeetingCapture-2026-09-10-120000.ips',process='MeetingCapture',incident='INC-2',
                exception='EXC_CRASH',signal='SIGABRT',stamp='2026-09-10 12:00:30.00 +0300')
            ips(reports,'Safari-2026-09-10-120100.ips',process='Safari',incident='INC-3')   # not ours
            recorded=E.collect_crashes(data,directory=reports)
            self.assertEqual(len(recorded),2)
            kinds={e['context']['process'] for e in recorded}
            self.assertEqual(kinds,{'MeetingOS','MeetingCapture'})
            crash=next(e for e in recorded if e['context']['process']=='MeetingOS')
            self.assertEqual(crash['kind'],'crash')
            self.assertIn('EXC_BAD_ACCESS/SIGSEGV',crash['message'])
            self.assertEqual(crash['context']['termination'],'Segmentation fault: 11')
            self.assertEqual(crash['context']['bundle_version'],'1.2.63')
            frames=crash['context']['frames']
            self.assertEqual(frames,['MeetingOS: MeetingOS.Model.refresh()','MeetingOS: closure #1 in Model.launch(_:)','MeetingOS'])
            self.assertFalse(any('objc_msgSend' in f for f in frames))   # not our module
            self.assertFalse(any('0x' in f or 'imageOffset' in f for f in frames))   # function names only, no addresses
            body=json.dumps(recorded,ensure_ascii=False)
            self.assertNotIn('/Users/gizli',body);self.assertNotIn('instructionByteStream',body)
    def test_a_second_sweep_records_nothing_and_the_watermark_survives_a_clear(self):
        with tempfile.TemporaryDirectory() as tmp:
            reports=Path(tmp)/'DiagnosticReports';reports.mkdir();data=Path(tmp)/'data';data.mkdir()
            ips(reports,'MeetingOS-1.ips')
            self.assertEqual(len(E.collect_crashes(data,directory=reports)),1)
            self.assertEqual(E.collect_crashes(data,directory=reports),[])
            E.clear(data)
            self.assertEqual(E.collect_crashes(data,directory=reports),[])   # cleared crashes must not come back
            self.assertTrue(E.state_path(data).is_file())
            self.assertEqual(E.state_path(data).stat().st_mode&0o777,0o600)
    def test_a_damaged_report_and_a_missing_folder_are_survivable(self):
        with tempfile.TemporaryDirectory() as tmp:
            reports=Path(tmp)/'DiagnosticReports';reports.mkdir();data=Path(tmp)/'data';data.mkdir()
            (reports/'MeetingOS-bozuk.ips').write_text('not json at all\n{}',encoding='utf-8')
            (reports/'MeetingOS-yarim.ips').write_text('{"app_name":"MeetingOS"}',encoding='utf-8')
            self.assertEqual(E.collect_crashes(data,directory=reports),[])
            self.assertIsNone(E.parse_crash(reports/'MeetingOS-bozuk.ips'))
            self.assertEqual(E.collect_crashes(data,directory=Path(tmp)/'yok'),[])
    def test_an_update_failure_is_imported_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            data=Path(tmp)
            (data/'update-status.json').write_text(json.dumps({'state':'failed','message':'Derleme başarısız','time':'2026-09-10T10:00:00+00:00'}))
            self.assertIsNotNone(E.note_update_failure(data))
            self.assertIsNone(E.note_update_failure(data))
            (data/'update-status.json').write_text(json.dumps({'state':'done','message':'tamam','time':'2026-09-10T11:00:00+00:00'}))
            self.assertIsNone(E.note_update_failure(data))
            self.assertEqual([e['kind'] for e in E.entries(data)],['update'])
            self.assertIn('Derleme başarısız',E.entries(data)[0]['message'])


class HeartbeatTests(unittest.TestCase):
    def test_the_heartbeat_carries_the_journal_and_summarize_shows_it(self):
        from meeting_os import reports as R
        from meeting_os.store import Store
        def fake_run(cmd,**kwargs):
            if cmd[0].endswith('pmset'): return SimpleNamespace(returncode=0,stdout='CPU_Speed_Limit \t= 100\n',stderr='')
            return SimpleNamespace(returncode=0,stdout='Test-Mac\n',stderr='')
        with tempfile.TemporaryDirectory() as tmp:
            data=Path(tmp);store=Store(data/'meeting-os.sqlite')
            R.save_settings(data,{'report_dir':str(data/'shared')})
            E.record('crash','MeetingOS çöktü · EXC_BAD_ACCESS/SIGSEGV',data_dir=data,context={'process':'MeetingOS'})
            E.record('cloud','auth: anahtar reddedildi /Users/ayse/x',data_dir=data)
            with patch('meeting_os.reports.subprocess.run',side_effect=fake_run):
                path=R.write_heartbeat(store,data,app={'version':'1.2.63'})
            beat=json.loads(Path(path).read_text(encoding='utf-8'))
            journal=beat['error_journal']
            self.assertEqual(journal['last_24h'],{'crash':1,'cloud':1})
            self.assertEqual(journal['crashes_24h'],1)
            self.assertEqual(len(journal['last']),2)
            self.assertNotIn('/Users/ayse',json.dumps(beat,ensure_ascii=False))
            self.assertIsInstance(beat['errors'],list)   # the last-job.log lines keep their own key
            hosts=R.summarize(str(data/'shared'))['hosts']
            self.assertEqual(hosts['Test-Mac']['heartbeat']['error_journal']['crashes_24h'],1)
            store.close()
    def test_alerts_report_a_crash_and_a_noisy_day(self):
        from meeting_os.reports import alerts
        now=datetime.now(timezone.utc)
        def host(journal): return {'Mac-Kayit':{'reports':0,'errors':0,'heartbeat':{'last_seen':now.isoformat(),'free_disk':50*1024**3,'error_journal':journal}}}
        keys={a['key']:a for a in alerts(host({'last_24h':{'crash':1,'job':1},'crashes_24h':1,'last':[{'message':'MeetingOS çöktü · EXC_BAD_ACCESS'}]}),now=now)}
        self.assertEqual(keys['crash']['level'],'error');self.assertIn('EXC_BAD_ACCESS',keys['crash']['line'])
        self.assertNotIn('error_journal',keys)   # two entries is a Tuesday, not an alert
        noisy={a['key']:a for a in alerts(host({'last_24h':{'job':3,'cloud':2},'crashes_24h':0,'last':[{'message':'İş 1 koduyla çıktı'}]}),now=now)}
        self.assertEqual(noisy['error_journal']['level'],'warning')
        self.assertIn('5 hata kaydı',noisy['error_journal']['line']);self.assertIn('İş 1 koduyla çıktı',noisy['error_journal']['line'])
        self.assertEqual(alerts(host({'last_24h':{},'crashes_24h':0,'last':[]}),now=now),[])
        self.assertEqual(alerts(host(None),now=now),[])   # a heartbeat from before 1.2.63
        # A malformed block written by some other version must not take the whole fleet view down.
        self.assertEqual(alerts(host('bozuk'),now=now),[])
        self.assertEqual(alerts(host({'last_24h':['job'],'crashes_24h':'çok','last':'yok'}),now=now),[])
        self.assertEqual([a['key'] for a in alerts(host({'crashes_24h':2,'last':[None,'x']}),now=now)],['crash'])


class BridgeTests(unittest.TestCase):
    def test_the_three_actions_write_read_and_empty_the_journal(self):
        from meeting_os.desktop import dispatch
        with tempfile.TemporaryDirectory() as tmp,patch.object(E,'DIAGNOSTIC_REPORTS',Path(tmp)/'no-crashes'):
            data=Path(tmp);db=data/'meeting-os.sqlite'
            self.assertTrue(dispatch({'action':'error_report','kind':'ui','message':'Bir şey oldu /Users/ayse/g',
                                      'context':{'command':'refresh','app_version':'1.2.63'}},db)['recorded'])
            self.assertFalse(dispatch({'action':'error_report','kind':'ui','message':'Bir şey oldu /Users/ayse/g'},db)['recorded'])
            listed=dispatch({'action':'errors_list'},db)
            self.assertEqual(len(listed['errors']),1)
            self.assertIn('/Users/…',listed['errors'][0]['message'])
            self.assertEqual(listed['summary']['last_24h'],{'ui':1})
            self.assertEqual(listed['errors'][0]['context']['command'],'refresh')
            self.assertEqual(dispatch({'action':'errors_clear'},db)['cleared'],[E.JOURNAL_FILE])
            self.assertEqual(dispatch({'action':'errors_list'},db)['errors'],[])
            self.assertFalse(db.exists())   # the journal answers without ever opening the database
    def test_a_report_with_nothing_in_it_is_refused_not_raised(self):
        from meeting_os.desktop import dispatch
        with tempfile.TemporaryDirectory() as tmp:
            self.assertFalse(dispatch({'action':'error_report'},Path(tmp)/'db')['recorded'])


class DiagnosticsTests(unittest.TestCase):
    def test_the_export_carries_the_journal_and_the_crash_summary(self):
        from meeting_os.diagnostics import collect,export_report,sanitize
        with tempfile.TemporaryDirectory() as tmp:
            data=Path(tmp)/'data';data.mkdir()
            E.record('crash','MeetingOS çöktü · EXC_BAD_ACCESS/SIGSEGV',data_dir=data,
                     context={'process':'MeetingOS','frames':['MeetingOS: Model.refresh()'],'termination':'Segmentation fault: 11'})
            E.record('job','finalize 1 koduyla çıktı /Users/ayse/gizli',data_dir=data,context={'command':'finalize'})
            report=collect(data,None,data)
            self.assertEqual(report['errors']['crashes_24h'],1)
            self.assertEqual(report['errors']['last_24h'],{'crash':1,'job':1})
            self.assertEqual(len(report['errors']['entries']),2)
            self.assertEqual(sanitize(report),report)   # sanitize runs again at export time; it must be idempotent
            crash=next(e for e in report['errors']['entries'] if e['kind']=='crash')
            self.assertEqual(crash['context']['frames'],['MeetingOS: Model.refresh()'])
            path=Path(tmp)/'export.json';export_report(path,report)
            text=path.read_text(encoding='utf-8')
            self.assertNotIn('/Users/ayse',text);self.assertIn('Segmentation fault',text)
            self.assertEqual(path.stat().st_mode&0o777,0o600)
    def test_a_machine_with_no_journal_still_exports(self):
        from meeting_os.diagnostics import collect
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(collect(Path(tmp),None,Path(tmp))['errors'],{'last_24h':{},'crashes_24h':0,'entries':[]})
            self.assertEqual(collect(Path(tmp))['errors']['entries'],[])   # no data folder given at all


class CommandLineTests(unittest.TestCase):
    def test_errors_list_and_clear_from_the_command_line(self):
        import contextlib,io,sys
        from meeting_os.cli import main
        with tempfile.TemporaryDirectory() as tmp,patch.object(E,'DIAGNOSTIC_REPORTS',Path(tmp)/'no-crashes'):
            data=Path(tmp);db=data/'meeting-os.sqlite'
            E.record('capture','Kayıt yardımcısı 1 koduyla çıktı',data_dir=data)
            out=io.StringIO()
            with patch.object(sys,'argv',['meeting_os','--db',str(db),'errors','list']),contextlib.redirect_stdout(out): main()
            listed=json.loads(out.getvalue())
            self.assertEqual(len(listed['errors']),1);self.assertEqual(listed['summary']['last_24h'],{'capture':1})
            out=io.StringIO()
            with patch.object(sys,'argv',['meeting_os','--db',str(db),'errors','clear']),contextlib.redirect_stdout(out): main()
            self.assertEqual(json.loads(out.getvalue())['cleared'],[E.JOURNAL_FILE])
    def test_a_failed_job_leaves_a_line_behind_it(self):
        import contextlib,io,sys
        from meeting_os.cli import main
        with tempfile.TemporaryDirectory() as tmp:
            data=Path(tmp);db=data/'meeting-os.sqlite'
            with patch.object(sys,'argv',['meeting_os','--db',str(db),'reports','write']), \
                 contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit): main()
            entries=E.entries(data)
            self.assertEqual(len(entries),1)
            self.assertEqual(entries[0]['kind'],'job');self.assertEqual(entries[0]['context']['command'],'reports')
            self.assertIn('ValueError',entries[0]['message'])


class HookTests(unittest.TestCase):
    def test_a_cloud_failure_writes_to_the_store_s_own_data_folder(self):
        from meeting_os.cloud_finalize import note_cloud_failure
        from meeting_os.store import Store
        with tempfile.TemporaryDirectory() as tmp:
            data=Path(tmp);store=Store(data/'meeting-os.sqlite')
            mid=store.create_meeting('Toplantı',{})
            note_cloud_failure(store,mid,RuntimeError('OpenRouter 402 kredi bitti'))
            entries=E.entries(data)
            self.assertEqual(len(entries),1);self.assertEqual(entries[0]['kind'],'cloud')
            self.assertIn('402',entries[0]['message'])
            self.assertEqual(entries[0]['context']['meeting'],E.meeting_key(mid))
            self.assertNotIn('Toplantı',json.dumps(entries,ensure_ascii=False))   # no title, no id: a hash only
            store.close()


if __name__=='__main__': unittest.main()
