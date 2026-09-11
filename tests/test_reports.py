import json,os,subprocess,sys,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from meeting_os import reports
from meeting_os.store import Store
from meeting_os.types import Segment

THERM='Note: No thermal warning level has been recorded\nCPU_Speed_Limit \t= 70\n'

def fake_run(cmd,**kwargs):
    """scutil answers the host name, pmset the thermal state; everything else stays untouched."""
    if cmd[0].endswith('pmset'): return SimpleNamespace(returncode=0,stdout=THERM,stderr='')
    return SimpleNamespace(returncode=0,stdout='Test-Mac\n',stderr='')

def capture_folder(root):
    d=Path(root)/'rec';d.mkdir()
    for i in range(3): (d/f'mic-{i:06d}.wav').write_bytes(b'0'*100)
    for i in range(2): (d/f'system-{i:06d}.wav').write_bytes(b'0'*100)
    (d/'mic-000003.partial.wav').write_bytes(b'0'*100)   # still being written: not a chunk yet
    (d/'mic-full.wav').write_bytes(b'0'*4096);(d/'system-full.wav').write_bytes(b'0'*2048)
    events=[{'event':'started'},{'event':'chunk','source':'mic','start':0,'duration':12},
            {'event':'gap','source':'mic','start':12.0,'end':13.5},{'event':'error','message':'gizli'},
            {'event':'gap','source':'system','start':4.0,'end':4.25},{'event':'stopped'}]
    (d/'capture-native.jsonl').write_text('\n'.join(json.dumps(e) for e in events)+'\nbozuk satır\n')
    return d

class CaptureBlockTests(unittest.TestCase):
    def test_chunk_files_gaps_and_assembled_bytes_are_counted(self):
        with tempfile.TemporaryDirectory() as tmp:
            d=capture_folder(tmp)
            block=reports.capture_block(str(d),36.0)
            self.assertEqual(block['chunk_files'],{'mic':3,'system':2})
            self.assertEqual(block['announced_chunks'],{'mic':1})
            self.assertEqual((block['expected_chunks'],block['chunk_seconds']),(3,12.0))
            self.assertEqual((block['gaps'],block['gap_seconds'],block['capture_errors']),(2,1.75,1))
            self.assertEqual(block['full_bytes'],{'mic':4096,'system':2048})
            self.assertEqual(block['journal'],'capture-native.jsonl')
    def test_the_flac_archive_audio_archive_writes_is_measured(self):
        with tempfile.TemporaryDirectory() as tmp:
            d=Path(tmp)/'arsiv';d.mkdir()
            (d/'system-full.flac').write_bytes(b'0'*9000);(d/'mic-full.wav').write_bytes(b'0'*3000)
            (d/'mic-000000.wav').write_bytes(b'0'*100)
            block=reports.capture_block(str(d))
            self.assertEqual(block['full_bytes'],{'system':9000,'mic':3000})
            self.assertEqual(block['chunk_files'],{'mic':1})
    def test_the_journal_is_read_from_its_end(self):
        with tempfile.TemporaryDirectory() as tmp:
            d=Path(tmp)/'uzun';d.mkdir()
            old=[json.dumps({'event':'chunk','source':'mic','start':0,'duration':12,'pad':'x'*400}) for _ in range(400)]
            (d/'capture-native.jsonl').write_text('\n'.join(old+[json.dumps({'event':'error','message':'son'})])+'\n')
            self.assertEqual(reports.capture_block(str(d))['capture_errors'],1)   # the tail is what is read
            self.assertLess(reports.capture_block(str(d))['announced_chunks']['mic'],400)
    def test_legacy_journal_and_missing_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            d=Path(tmp)/'eski';d.mkdir()
            (d/'events.jsonl').write_text(json.dumps({'event':'gap','source':'mic','start':1,'end':2})+'\n')
            self.assertEqual(reports.capture_block(str(d))['journal'],'events.jsonl')
            self.assertEqual(reports.capture_block(str(d))['gap_seconds'],1.0)
            self.assertIsNone(reports.capture_block(str(d/'yok')));self.assertIsNone(reports.capture_block(None))
            self.assertIsNone(reports.capture_block(123))
    def test_meeting_report_carries_the_capture_block(self):
        with tempfile.TemporaryDirectory() as tmp:
            data=Path(tmp);d=capture_folder(tmp);s=Store(data/'meeting-os.sqlite')
            mid=s.create_meeting('Kayıt',{'capture_dir':str(d)})
            s.add_segment(mid,Segment(0,36,'Merhaba','system','Konuşmacı 1',flags=['cloud_transcript']));s.status(mid,'complete')
            report=reports.build_meeting_report(s,mid,data)
            self.assertEqual(report['capture']['chunk_files'],{'mic':3,'system':2})
            self.assertEqual(report['capture']['expected_chunks'],3);self.assertEqual(report['capture']['gaps'],2)
            other=s.create_meeting('Metin',{});s.status(other,'complete')
            self.assertIsNone(reports.build_meeting_report(s,other,data)['capture'])
            s.close()

    def test_the_report_says_how_the_spelling_hint_budget_was_spent_and_never_which_words(self):
        with tempfile.TemporaryDirectory() as tmp:
            data=Path(tmp);s=Store(data/'meeting-os.sqlite')
            mid=s.create_meeting('Kelime',{'hint_included':['Splendo','Trendyol'],'hint_excluded':7})
            s.add_segment(mid,Segment(0,5,'Merhaba','system','Konuşmacı 1'));s.status(mid,'complete')
            report=reports.build_meeting_report(s,mid,data)
            self.assertEqual((report['hint_included'],report['hint_excluded']),(2,7))
            self.assertNotIn('Splendo',json.dumps(report,ensure_ascii=False))   # counts travel, words do not
            s.close()

class ReportPrivacyTests(unittest.TestCase):
    """The Settings caption promises numbers only. The report is written into iCloud Drive or a team folder, so
    the meeting title and the people in it stay out of it unless the user turns transcript sharing on."""
    def _meeting(self,data):
        s=Store(data/'meeting-os.sqlite');mid=s.create_meeting('Yatırımcı görüşmesi',{})
        s.add_segment(mid,Segment(0,10,'Merhaba','system','Konuşmacı 1',metrics={'cluster':0,'identity':{'similarity':0.91,'suggested':'Ayşe Yılmaz','name':None}}))
        s.add_segment(mid,Segment(10,20,'Evet','system','Konuşmacı 2',metrics={'cluster':1}))
        s.correct(mid,'Konuşmacı 1','Ayşe Yılmaz');s.status(mid,'complete')
        return s,mid
    def test_the_title_and_the_names_are_left_out_unless_transcript_sharing_is_on(self):
        with tempfile.TemporaryDirectory() as tmp:
            data=Path(tmp);s,mid=self._meeting(data)
            report=reports.build_meeting_report(s,mid,data)
            blob=json.dumps(report,ensure_ascii=False)
            self.assertIsNone(report['title'])
            self.assertNotIn('Yatırımcı görüşmesi',blob);self.assertNotIn('Ayşe Yılmaz',blob)
            self.assertEqual(sorted(report['speakers']),['S1','S2'])
            first=report['speakers']['S1']
            self.assertEqual((first['segments'],first['seconds'],first['clusters']),(1,10.0,1))
            self.assertEqual((first['similarity'],first['named'],first['name'],first['suggested']),(0.91,True,None,None))
            self.assertFalse(report['speakers']['S2']['named'])
            s.close()
    def test_transcript_sharing_brings_the_title_and_the_real_labels_back(self):
        with tempfile.TemporaryDirectory() as tmp:
            data=Path(tmp);s,mid=self._meeting(data)
            report=reports.build_meeting_report(s,mid,data,include_text=True)
            self.assertEqual(report['title'],'Yatırımcı görüşmesi')
            self.assertEqual(report['speakers']['Konuşmacı 1']['name'],'Ayşe Yılmaz')
            self.assertEqual(report['transcript'][0]['speaker'],'Ayşe Yılmaz')
            s.close()
    def test_the_written_report_carries_the_same_redaction_and_the_digest_still_counts_named_people(self):
        with tempfile.TemporaryDirectory() as tmp:
            data=Path(tmp);s,mid=self._meeting(data)
            reports.save_settings(data,{'report_dir':str(data/'shared')})
            with patch('meeting_os.reports.subprocess.run',side_effect=fake_run): path=reports.write_meeting_report(s,mid,data)
            self.assertNotIn('Ayşe Yılmaz',Path(path).read_text(encoding='utf-8'))
            self.assertEqual(reports.summarize(str(data/'shared'))['reports'][0]['named'],1)
            s.close()

class HeartbeatTests(unittest.TestCase):
    def test_heartbeat_is_one_file_per_host_with_sizes_disk_and_thermal(self):
        with tempfile.TemporaryDirectory() as tmp:
            data=Path(tmp);s=Store(data/'meeting-os.sqlite')
            reports.save_settings(data,{'report_dir':str(data/'shared')})
            done=s.create_meeting('Biten',{});s.status(done,'complete');s.create_meeting('Süren',{})
            (data/'recordings'/'a').mkdir(parents=True);(data/'recordings'/'a'/'x.wav').write_bytes(b'0'*2048)
            (data/'imports').mkdir();(data/'imports'/'y.wav').write_bytes(b'0'*512)
            (data/'last-job.log').write_text('ok\nMeeting OS: OpenRouter HTTP 500 /Users/boran/gizli\n')
            with patch('meeting_os.reports.subprocess.run',side_effect=fake_run):
                path=reports.write_heartbeat(s,data,app={'version':'9.9.9','commit':'abc123'})
            self.assertTrue(path.endswith('/Test-Mac/heartbeat.json'),path)
            beat=json.loads(Path(path).read_text())
            self.assertEqual((beat['app_version'],beat['commit'],beat['meetings']),('9.9.9','abc123',2))
            self.assertEqual(beat['statuses'],{'complete':1,'processing':1})
            self.assertTrue(beat['last_complete'] and beat['written'])
            self.assertEqual((beat['sizes']['recordings'],beat['sizes']['imports']),(2048,512))
            self.assertGreater(beat['sizes']['database'],0);self.assertGreater(beat['sizes']['free_disk'],0)
            self.assertEqual(beat['thermal'],70);self.assertEqual(len(beat['load_average']),3)
            self.assertIn('/Users/…',beat['errors'][0]);self.assertIn(beat['memory_pressure'],('normal','pressure',None))
            with patch('meeting_os.reports.subprocess.run',side_effect=fake_run):
                again=reports.write_heartbeat(s,data)
            self.assertEqual(again,path)
            self.assertEqual(len(list(Path(path).parent.glob('*.json'))),1)   # overwritten, never one file per day
            self.assertIsNone(json.loads(Path(path).read_text())['app_version'])
            s.close()
    def test_heartbeat_is_gated_by_the_setting_and_never_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            data=Path(tmp);s=Store(data/'meeting-os.sqlite')
            reports.save_settings(data,{'report_dir':str(data/'shared'),'share_reports':False})
            self.assertIsNone(reports.write_heartbeat(s,data))
            self.assertFalse((data/'shared').exists())
            reports.save_settings(data,{'share_reports':True})
            self.assertIsNone(reports.write_heartbeat(object(),data))   # a broken store must not reach the caller
            s.close()
    def test_thermal_is_none_when_pmset_is_unavailable_and_the_probe_is_bounded(self):
        with patch('meeting_os.reports.subprocess.run',side_effect=OSError('yok')): self.assertIsNone(reports._thermal())
        with patch('meeting_os.reports.subprocess.run',return_value=SimpleNamespace(returncode=0,stdout='',stderr='')) as run:
            self.assertIsNone(reports._thermal())
            self.assertEqual(run.call_args.kwargs['timeout'],3)
    def test_summary_surfaces_each_host_heartbeat_and_never_lists_it_as_a_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            shared=Path(tmp)/'shared';host=shared/'Mac-Kayit';host.mkdir(parents=True)
            (host/'2026-09-09_abc.json').write_text(json.dumps({'host':'Mac-Kayit','title':'Sprint','status':'complete','cost_usd':0.01,'speakers':{'K1':{'name':'Ayşe'}},'errors':[]}))
            (host/reports.HEARTBEAT_FILE).write_text(json.dumps({'host':'Mac-Kayit','written':'2026-09-09T10:00:00+00:00','meetings':7,'app_version':'1.2.15',
                                                                 'sizes':{'free_disk':1234},'thermal':70,'memory_pressure':'normal'}))
            (shared/'Mac-Sessiz').mkdir()
            (shared/'Mac-Sessiz'/reports.HEARTBEAT_FILE).write_text(json.dumps({'host':'Mac-Sessiz','written':'2026-09-08T10:00:00+00:00','sizes':{},'thermal':None}))
            summary=reports.summarize(str(shared))
            self.assertEqual([r['file'] for r in summary['reports']],['2026-09-09_abc.json'])
            beat=summary['hosts']['Mac-Kayit']['heartbeat']
            self.assertEqual((beat['last_seen'],beat['free_disk'],beat['thermal'],beat['meetings']),('2026-09-09T10:00:00+00:00',1234,70,7))
            self.assertEqual(summary['hosts']['Mac-Kayit']['reports'],1)
            self.assertEqual(summary['hosts']['Mac-Sessiz']['reports'],0)   # alive but has written no meeting report
            self.assertIsNone(summary['hosts']['Mac-Sessiz']['heartbeat']['free_disk'])

class RecordingHeartbeatTests(unittest.TestCase):
    """While a meeting is being taped, both Macs should be able to see that it still is."""
    STATE={'meeting':'m1','elapsed_seconds':2460.0,'last_chunk_age_seconds':4.0,'chunks':{'mic':205,'system':205},
           'restarts':1,'relaunches':1,'gap_seconds':2.5,'wake_gap_seconds':180.0,'free_disk':1234}
    def test_it_is_written_read_and_cleared_and_answers_in_one_line(self):
        with tempfile.TemporaryDirectory() as tmp:
            data=Path(tmp);reports.save_settings(data,{'report_dir':str(data/'shared')})
            with patch('meeting_os.reports.subprocess.run',side_effect=fake_run):
                path=reports.write_recording_heartbeat(data,self.STATE)
                self.assertTrue(path.endswith('/Test-Mac/recording-heartbeat.json'),path)
                beat=reports.read_recording_heartbeat(Path(path).parent)
                self.assertEqual(beat['line'],'kayıt sürüyor · 41 dk · son parça 4 sn önce · 1 kez yeniden başlatıldı · 182 sn boşluk')
                self.assertEqual(beat['meeting'],'m1');self.assertLess(beat['age_seconds'],5)
                reports.clear_recording_heartbeat(data)
                self.assertIsNone(reports.read_recording_heartbeat(Path(path).parent))
                reports.clear_recording_heartbeat(data)   # clearing twice must not raise
    def test_a_stale_file_is_not_reported_as_a_live_recording(self):
        with tempfile.TemporaryDirectory() as tmp:
            host=Path(tmp)/'Mac';host.mkdir()
            (host/reports.RECORDING_HEARTBEAT_FILE).write_text(json.dumps({'host':'Mac','written':'2020-01-01T00:00:00+00:00','elapsed_seconds':60}))
            self.assertIsNone(reports.read_recording_heartbeat(host))
            (host/reports.RECORDING_HEARTBEAT_FILE).write_text('bozuk')
            self.assertIsNone(reports.read_recording_heartbeat(host))
    def test_sharing_off_writes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            data=Path(tmp);reports.save_settings(data,{'report_dir':str(data/'shared'),'share_reports':False})
            self.assertIsNone(reports.write_recording_heartbeat(data,self.STATE))
            self.assertFalse((data/'shared').exists())
    def test_heartbeat_and_summary_carry_it_without_listing_it_as_a_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            data=Path(tmp);s=Store(data/'meeting-os.sqlite')
            reports.save_settings(data,{'report_dir':str(data/'shared')})
            with patch('meeting_os.reports.subprocess.run',side_effect=fake_run):
                reports.write_recording_heartbeat(data,self.STATE)
                beat=json.loads(Path(reports.write_heartbeat(s,data)).read_text())
                self.assertEqual(beat['recording']['meeting'],'m1')
                self.assertIn('kayıt sürüyor',beat['recording']['line'])
                summary=reports.summarize(str(data/'shared'))
            self.assertEqual(summary['reports'],[])   # it is state, not a meeting report
            live=summary['hosts']['Test-Mac']['recording']
            self.assertEqual((live['relaunches'],live['last_chunk_age_seconds']),(1,4.0))
            self.assertIn('41 dk',live['line'])
            s.close()

class HeartbeatBridgeTests(unittest.TestCase):
    def test_bridge_action_writes_the_file_and_returns_its_path(self):
        from meeting_os.desktop import dispatch
        with tempfile.TemporaryDirectory() as tmp:
            data=Path(tmp);db=data/'meeting-os.sqlite';Store(db).close()
            reports.save_settings(data,{'report_dir':str(data/'shared')})
            with patch('meeting_os.reports.subprocess.run',side_effect=fake_run):
                path=dispatch({'action':'heartbeat'},db)['path']
            beat=json.loads(Path(path).read_text())
            from meeting_os import __version__
            self.assertEqual((beat['app_version'],beat['meetings']),(__version__,0))
    def test_the_bundle_version_the_app_sends_wins_over_the_repo_version(self):
        """ModelActions.swift sends CFBundleShortVersionString. When it differs from the repo's, an update
        merged and never finished building — the heartbeat has to carry both, not the repo's twice."""
        from meeting_os.desktop import dispatch
        from meeting_os import __version__
        with tempfile.TemporaryDirectory() as tmp:
            data=Path(tmp);db=data/'meeting-os.sqlite';Store(db).close()
            reports.save_settings(data,{'report_dir':str(data/'shared')})
            with patch('meeting_os.reports.subprocess.run',side_effect=fake_run):
                path=dispatch({'action':'heartbeat','app':{'version':'1.2.41','bridge':{}}},db)['path']
            beat=json.loads(Path(path).read_text())
            self.assertEqual(beat['app_version'],'1.2.41')
            self.assertEqual(beat['repo_version'],__version__)
            with patch('meeting_os.reports.subprocess.run',side_effect=fake_run):
                path=dispatch({'action':'heartbeat','app':{'version':''}},db)['path']   # plain `swift build`: no bundle version
            self.assertEqual(json.loads(Path(path).read_text())['app_version'],__version__)

class UpdateTruthTests(unittest.TestCase):
    """What the fleet needs in order to see a half-finished update: the version of the bundle that is actually
    running, the version and commit of the checkout it would be built from, what update.sh last said, and whether
    the signing grant is in place. Before this, a Mac that merged and failed to build looked healthy."""
    def _beat(self,data,app):
        with patch('meeting_os.reports.subprocess.run',side_effect=fake_run):
            s=Store(data/'meeting-os.sqlite')
            try: return json.loads(Path(reports.write_heartbeat(s,data,app=app)).read_text())
            finally: s.close()
    def test_the_heartbeat_separates_the_installed_app_from_the_checkout(self):
        from meeting_os import __version__
        with tempfile.TemporaryDirectory() as tmp:
            data=Path(tmp);reports.save_settings(data,{'report_dir':str(data/'shared')})
            (data/'update-status.json').write_text(json.dumps({'state':'failed','from':'aaa','to':'bbb',
                                                               'message':'Derleme başarısız','time':'2026-09-10 04:00:00'}))
            marker=data/'signing-partition.ok'
            with patch.object(reports,'_REPO_COMMIT',...),patch('meeting_os.probe.SIGNING_MARKER',marker):
                beat=self._beat(data,{'version':'1.2.41'})
            self.assertEqual(beat['app_version'],'1.2.41')          # what the bundle reports
            self.assertEqual(beat['repo_version'],__version__)      # what the checkout would build
            self.assertEqual(beat['update_status'],{'state':'failed','message':'Derleme başarısız','time':'2026-09-10 04:00:00'})
            self.assertFalse(beat['signing_partition'])
            marker.write_text('granted\n')
            with patch.object(reports,'_REPO_COMMIT',...),patch('meeting_os.probe.SIGNING_MARKER',marker):
                beat=self._beat(data,{'version':'1.2.41'})
            self.assertTrue(beat['signing_partition'])
    def test_the_commit_falls_back_to_the_checkout_and_never_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            data=Path(tmp);reports.save_settings(data,{'report_dir':str(data/'shared')})
            with patch.object(reports,'_REPO_COMMIT','deadbee'):
                beat=self._beat(data,{'version':'1.2.44'})
            self.assertEqual(beat['commit'],'deadbee')
            with patch.object(reports,'_REPO_COMMIT',...),patch('meeting_os.reports.subprocess.run',side_effect=OSError('git yok')):
                self.assertIsNone(reports.repo_commit())
    def test_no_update_status_file_is_none_not_a_crash(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(reports.update_status(Path(tmp)))
            (Path(tmp)/'update-status.json').write_text('bozuk')
            self.assertIsNone(reports.update_status(Path(tmp)))
    def test_summary_carries_the_new_fields_and_alerts_on_them(self):
        from meeting_os.reports import alerts
        from datetime import datetime, timezone
        now=datetime.now(timezone.utc)
        with tempfile.TemporaryDirectory() as tmp:
            shared=Path(tmp)/'shared';host=shared/'Mac-Yarim';host.mkdir(parents=True)
            (host/reports.HEARTBEAT_FILE).write_text(json.dumps({'host':'Mac-Yarim','written':now.isoformat(),
                'app_version':'1.2.41','repo_version':'1.2.44','commit':'abc1234','signing_partition':False,
                'update_status':{'state':'failed','message':'Derleme başarısız','time':'2026-09-10 04:00:00'},
                'sizes':{'free_disk':50*1024**3}}))
            summary=reports.summarize(str(shared))
            beat=summary['hosts']['Mac-Yarim']['heartbeat']
            self.assertEqual((beat['repo_version'],beat['commit']),('1.2.44','abc1234'))
            keys={a['key']:a for a in summary['alerts']}
            self.assertIn('version_mismatch',keys); self.assertEqual(keys['version_mismatch']['level'],'error')
            self.assertIn('1.2.41',keys['version_mismatch']['line']); self.assertIn('sh scripts/update.sh',keys['version_mismatch']['line'])
            self.assertEqual(keys['update_failed']['level'],'error')
            self.assertIn('Derleme başarısız',keys['update_failed']['line'])
            self.assertEqual(keys['signing_partition']['level'],'warning')
            healthy={'Mac-Iyi':{'reports':0,'errors':0,'heartbeat':{'last_seen':now.isoformat(),'free_disk':50*1024**3,
                     'app_version':'1.2.44','repo_version':'1.2.44','signing_partition':True,'update_status':{'state':'done'}}}}
            self.assertEqual(alerts(healthy,now=now),[])
    def test_a_heartbeat_from_an_older_version_raises_no_alert(self):
        from meeting_os.reports import alerts
        from datetime import datetime, timezone
        now=datetime.now(timezone.utc)
        hosts={'Eski':{'reports':0,'errors':0,'heartbeat':{'last_seen':now.isoformat(),'free_disk':50*1024**3,'app_version':'1.2.15'}}}
        self.assertEqual(alerts(hosts,now=now),[])   # no repo_version, no signing_partition: nothing to compare


class UserNameTests(unittest.TestCase):
    def test_the_name_is_validated_and_nobody_is_the_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            data=Path(tmp)
            self.assertEqual(reports.load_settings(data)['user_name'],'')   # the value, not the constant: DEFAULT_USER_NAME==DEFAULT_USER_NAME proved nothing
            self.assertEqual(reports.settings_owner(data),'')   # no settings file: this Mac belongs to nobody yet
            self.assertNotIn('Boran',(reports.DEFAULT_USER_NAME,reports.settings_owner(data)))
            self.assertEqual(reports.save_settings(data,{'user_name':'  Ayşe Yılmaz  '})['user_name'],'Ayşe Yılmaz')
            self.assertEqual(reports.settings_owner(data),'Ayşe Yılmaz')
            for junk in ('x'*(reports.NAME_LIMIT+1),None,5,True,['Ayşe']):
                self.assertEqual(reports.save_settings(data,{'user_name':junk})['user_name'],'Ayşe Yılmaz')
            self.assertEqual(reports.save_settings(data,{'user_name':'   '})['user_name'],'Ayşe Yılmaz')   # an empty value alone never wipes a name
            self.assertEqual(reports.save_settings(data,{'user_name':'','user_name_clear':True})['user_name'],'')   # clearing is explicit and means nobody
            self.assertEqual(reports.save_settings(data,{'user_name':'x'*reports.NAME_LIMIT})['user_name'],'x'*reports.NAME_LIMIT)
            reports.settings_path(data).write_text(json.dumps({'user_name':'   '}),encoding='utf-8')
            self.assertEqual(reports.settings_owner(data),'')   # a blank value in the file is not a name
    def test_the_bridge_reads_and_writes_the_name(self):
        from meeting_os.desktop import dispatch
        with tempfile.TemporaryDirectory() as tmp:
            data=Path(tmp);db=data/'meeting-os.sqlite';Store(db).close()
            self.assertEqual(dispatch({'action':'report_settings'},db)['user_name'],'')
            self.assertEqual(dispatch({'action':'report_settings_set','changes':{'user_name':'Deniz'}},db)['user_name'],'Deniz')
            self.assertEqual(reports.settings_owner(data),'Deniz')
    def test_the_microphone_speaker_label_follows_the_setting(self):
        from meeting_os.cloud_finalize import source_labels, speaker_label
        self.assertEqual(source_labels('Deniz'),{'mic':'Deniz','system':'Karşı taraf'})
        self.assertEqual(source_labels(None),source_labels('   '))
        self.assertEqual(source_labels(None)['mic'],'Ben')   # nobody's name, not the author's
        self.assertEqual(speaker_label('mic','2',0,False,'Deniz'),'Deniz')
        self.assertEqual(speaker_label('system',None,0,False,'Deniz'),'Karşı taraf')
        self.assertEqual(speaker_label('system','1',2,True,'Deniz'),'Konuşmacı 3-2')   # the setting never touches diarized labels

class MicOwnerRenameTests(unittest.TestCase):
    """A teammate's first meeting is recorded before they reach Settings, so its mic rows carry a label that is
    not their name. Typing the name has to reach those rows, in every meeting, or they stay somebody else's."""
    def seed(self,db,label='Ben'):
        from meeting_os.types import Segment
        s=Store(db)
        first=s.create_meeting('Sprint');second=s.create_meeting('Retro')
        for mid in (first,second):
            s.add_segment(mid,Segment(0,8,'Ben raporu yarın çıkaracağım.','mic',label))
            s.add_segment(mid,Segment(8,16,'Tamam.','system','S0'))
            s.status(mid,'complete')
        return s,first,second
    def test_rename_touches_every_meeting_and_the_stored_payload(self):
        with tempfile.TemporaryDirectory() as tmp:
            db=Path(tmp)/'meeting-os.sqlite';s,first,second=self.seed(db)
            r=s.rename_mic_owner('Ben','Deniz'); self.assertEqual((r['meetings'],r['segments'],len(r['meeting_ids'])),(2,2,2))
            for mid in (first,second):
                rows=s.segments(mid)
                self.assertEqual([r['speaker'] for r in rows],['Deniz','S0'])   # payload follows the column
                self.assertEqual([r['speaker'] for r in s.display_segments(mid)],['Deniz','S0'])
            self.assertEqual(s.rename_mic_owner('Ben','Deniz')['segments'],0)   # idempotent
            self.assertEqual(s.rename_mic_owner('Deniz','Deniz')['segments'],0)
            with self.assertRaises(ValueError): s.rename_mic_owner('Deniz','  ')
            s.close()
    def test_rename_marks_the_analysis_of_a_touched_meeting_stale(self):
        from meeting_os.memory import Memory
        with tempfile.TemporaryDirectory() as tmp:
            db=Path(tmp)/'meeting-os.sqlite';s,first,_=self.seed(db)
            mem=Memory(s);rows=s.display_segments(first)
            mem.save_analysis(first,mem.current_hash(first),'fixture',
                {'summary':[],'decisions':[],'risks':[],'questions':[],
                 'actions':[{'title':'Raporu çıkarmak','owner':'Ben','due_text':'yarın','evidence':[{'segment_id':rows[0]['id'],'quote':'raporu yarın çıkaracağım','start':0,'source':'mic','speaker':'Ben'}],'needs_review':False}]})
            self.assertFalse(Memory(s).latest(first)['stale'])
            s.rename_mic_owner('Ben','Deniz')
            self.assertTrue(Memory(s).latest(first)['stale'])   # owner attribution changed: the analysis is not current
            s.close()
    def test_the_settings_write_relabels_earlier_meetings(self):
        """The settings write is the only way a rename reaches the store; the bare `rename_mic_owner` bridge
        action was removed because nothing in the app ever called it."""
        from meeting_os.desktop import dispatch
        with tempfile.TemporaryDirectory() as tmp:
            data=Path(tmp);db=data/'meeting-os.sqlite';s,first,_=self.seed(db)
            r=s.rename_mic_owner('Ben','Deniz'); self.assertEqual((r['meetings'],r['segments']),(2,2)); s.close()
            reports.save_settings(data,{'user_name':'Deniz'})
            saved=dispatch({'action':'report_settings_set','changes':{'user_name':'Deniz Yılmaz'}},db)   # correcting the name later
            self.assertEqual((saved['user_name'],saved['renamed_meetings'],saved['renamed_segments']),('Deniz Yılmaz',2,2))
            s=Store(db);self.assertEqual(s.segments(first)[0]['speaker'],'Deniz Yılmaz');s.close()
    def test_the_historical_boran_default_is_relabelled_too(self):
        from meeting_os.desktop import dispatch
        with tempfile.TemporaryDirectory() as tmp:
            data=Path(tmp);db=data/'meeting-os.sqlite';s,first,_=self.seed(db,label='Boran');s.close()
            saved=dispatch({'action':'report_settings_set','changes':{'user_name':'Ece'}},db)
            self.assertEqual((saved['renamed_meetings'],saved['renamed_segments']),(2,2))
            s=Store(db);self.assertEqual(s.segments(first)[0]['speaker'],'Ece');s.close()
    def test_a_settings_write_that_does_not_change_the_name_renames_nothing(self):
        from meeting_os.desktop import dispatch
        with tempfile.TemporaryDirectory() as tmp:
            data=Path(tmp);db=data/'meeting-os.sqlite';s,first,_=self.seed(db);s.close()
            saved=dispatch({'action':'report_settings_set','changes':{'share_text':True}},db)
            self.assertEqual((saved['renamed_meetings'],saved['renamed_segments']),(0,0))
            s=Store(db);self.assertEqual(s.segments(first)[0]['speaker'],'Ben');s.close()
    def test_the_cli_writes_text_settings_as_text(self):
        """scripts/install.sh sets the name through this command; a string must not be coerced to a bool."""
        with tempfile.TemporaryDirectory() as tmp:
            data=Path(tmp)/'Library/Application Support/MeetingOS'
            run=lambda *a: subprocess.run([sys.executable,'-m','meeting_os','reports','settings',*a],capture_output=True,text=True,env={**os.environ,'HOME':tmp})
            p=run('--set','user_name=Ayşe Yılmaz','--set','share_text=true','--set','audio_retention_days=60')
            self.assertEqual(p.returncode,0,p.stderr)
            written=json.loads((data/reports.SETTINGS_FILE).read_text(encoding='utf-8'))
            self.assertEqual((written['user_name'],written['share_text'],written['audio_retention_days']),('Ayşe Yılmaz',True,60))
            self.assertEqual(json.loads(run().stdout)['user_name'],'Ayşe Yılmaz')

class TeamFolderTests(unittest.TestCase):
    def test_an_unreachable_folder_is_refused_and_a_real_one_replaces_the_report_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            data=Path(tmp)/'data';data.mkdir();team=Path(tmp)/'ekip';team.mkdir()
            self.assertEqual(reports.load_settings(data)['team_dir'],'')
            self.assertEqual(reports.save_settings(data,{'team_dir':str(team/'yok')})['team_dir'],'')      # never mounted: not stored
            self.assertEqual(reports.save_settings(data,{'team_dir':str(team/'glossary.jsonl')})['team_dir'],'')
            settings=reports.save_settings(data,{'team_dir':' '+str(team)+' '})
            self.assertEqual(settings['team_dir'],str(team))
            self.assertEqual(reports.report_root(settings),team/'reports')
            self.assertEqual(reports.report_root({'report_dir':'/x','team_dir':''}),Path('/x'))            # off: the personal folder
            self.assertEqual(reports.save_settings(data,{'team_dir':'  '})['team_dir'],'')                 # cleared
    def test_reports_are_written_into_the_team_folder_per_host(self):
        with tempfile.TemporaryDirectory() as tmp:
            data=Path(tmp)/'data';data.mkdir();team=Path(tmp)/'ekip';team.mkdir()
            s=Store(data/'meeting-os.sqlite');mid=s.create_meeting('Ekip toplantısı',{})
            s.add_segment(mid,Segment(0,5,'Merhaba','system','Konuşmacı 1'));s.status(mid,'complete')
            reports.save_settings(data,{'report_dir':str(data/'kisisel'),'team_dir':str(team)})
            with patch('meeting_os.reports.subprocess.run',side_effect=fake_run):
                path=reports.write_meeting_report(s,mid,data)
                self.assertTrue(path.startswith(str(team/'reports'/'Test-Mac')),path)
                self.assertFalse((data/'kisisel').exists())                                                # one destination, not two
                self.assertEqual(reports.summarize(reports.report_root(reports.load_settings(data)))['hosts']['Test-Mac']['reports'],1)
                self.assertEqual(len(reports.remove_meeting_report(mid,data)),1)
            s.close()

class TeamGlossaryTests(unittest.TestCase):
    def setUp(self):
        from meeting_os import glossary as G
        self.G=G
    def team_terms(self,path):
        return [e['term'] for e in (self.G.parse_line(l) for l in Path(path).read_text(encoding='utf-8').splitlines()) if e]
    def test_local_wins_the_team_file_fills_gaps_and_import_merges_instead_of_overwriting(self):
        G=self.G
        with tempfile.TemporaryDirectory() as tmp:
            data=Path(tmp)/'data';data.mkdir();team=Path(tmp)/'ekip';team.mkdir()
            reports.save_settings(data,{'team_dir':str(team)})
            (data/G.FILENAME).write_text(json.dumps({'term':'PMD','expansion':'yerel'},ensure_ascii=False)+'\n',encoding='utf-8')
            (team/G.FILENAME).write_text('\n'.join(json.dumps(e,ensure_ascii=False) for e in
                ({'term':'PMD','expansion':'ekip'},{'term':'ARR','expansion':'yıllık yinelenen gelir'}))+'\n',encoding='utf-8')
            loaded={e['term']:e for e in G.load(data)}
            self.assertEqual(loaded['PMD']['expansion'],'yerel')                       # the Mac's own file wins
            self.assertEqual(loaded['ARR']['expansion'],'yıllık yinelenen gelir')      # the team file only fills gaps
            source=Path(tmp)/'yeni.jsonl'
            source.write_text('\n'.join(json.dumps(e,ensure_ascii=False) for e in ({'term':'PMD','expansion':'yerel'},{'term':'NPS'}))+'\n',encoding='utf-8')
            result=G.import_file(source,data)
            self.assertEqual((result['team']['added'],result['team']['total']),(1,3))
            self.assertEqual(self.team_terms(team/G.FILENAME),['PMD','ARR','NPS'])     # ARR survives, PMD is not rewritten
            self.assertEqual(json.loads(Path(team/G.FILENAME).read_text(encoding='utf-8').splitlines()[0])['expansion'],'ekip')
    def test_the_merge_re_reads_so_a_teammates_term_is_not_lost_and_sharing_can_be_off(self):
        G=self.G
        with tempfile.TemporaryDirectory() as tmp:
            data=Path(tmp)/'data';data.mkdir();team=Path(tmp)/'ekip';team.mkdir()
            reports.save_settings(data,{'team_dir':str(team)})
            (team/G.FILENAME).write_text(json.dumps({'term':'PMD'})+'\n',encoding='utf-8')
            entries=G.load(data)                                                        # loaded before the teammate wrote
            (team/G.FILENAME).write_text('\n'.join(json.dumps(e) for e in ({'term':'PMD'},{'term':'OKR'}))+'\n',encoding='utf-8')
            G.merge_into(team/G.FILENAME,entries+[G.parse_line(json.dumps({'term':'CAC'}))])
            self.assertEqual(self.team_terms(team/G.FILENAME),['PMD','OKR','CAC'])
            self.assertFalse(list(team.glob('*.tmp')))                                  # temp file renamed, never left behind
            reports.save_settings(data,{'share_glossary':False})
            source=Path(tmp)/'yeni.jsonl';source.write_text(json.dumps({'term':'LTV'})+'\n',encoding='utf-8')
            self.assertNotIn('team',G.import_file(source,data))
            self.assertEqual(self.team_terms(team/G.FILENAME),['PMD','OKR','CAC'])
            self.assertIn('LTV',[e['term'] for e in G.load(data)])                       # the local copy is still written


class FileModeTests(unittest.TestCase):
    """Path.write_text keeps whatever mode a file already had, so one file created before umask 077 (or by an
    older build) stayed group- and world-readable for the life of the Mac. A team folder is the deliberate
    exception: teammates cannot read a 0700 folder."""
    def mode(self,path): return Path(path).stat().st_mode & 0o777
    def test_the_personal_files_are_published_at_0600_over_a_wider_predecessor(self):
        with tempfile.TemporaryDirectory() as tmp:
            data=Path(tmp)/'data';data.mkdir()
            reports.settings_path(data).write_text('{}',encoding='utf-8');reports.settings_path(data).chmod(0o644)
            reports.save_settings(data,{'report_dir':str(data/'shared')})
            self.assertEqual(self.mode(reports.settings_path(data)),0o600)
            s=Store(data/'meeting-os.sqlite');s.create_meeting('x',{})
            with patch('meeting_os.reports.subprocess.run',side_effect=fake_run),patch('meeting_os.reports.daily_probe',return_value=None):
                beat=reports.write_heartbeat(s,data)
                report_dir=Path(beat).parent
                (report_dir/'eski.json').write_text('{}');(report_dir/'eski.json').chmod(0o644)
                self.assertEqual(self.mode(beat),0o600);self.assertEqual(self.mode(report_dir),0o700)
                reports.write_recording_heartbeat(data,{'meeting':'x','elapsed_seconds':60})
                self.assertEqual(self.mode(report_dir/reports.RECORDING_HEARTBEAT_FILE),0o600)
            self.assertFalse(list(report_dir.glob('.*.json.*')))   # no temp file left behind
            s.close()
    def test_a_team_folder_stays_readable_for_teammates(self):
        with tempfile.TemporaryDirectory() as tmp:
            data=Path(tmp)/'data';data.mkdir();team=Path(tmp)/'ekip';team.mkdir()
            s=Store(data/'meeting-os.sqlite');mid=s.create_meeting('Ekip',{})
            s.add_segment(mid,Segment(0,5,'Merhaba','system','Konuşmacı 1'));s.status(mid,'complete')
            reports.save_settings(data,{'report_dir':str(data/'kisisel'),'team_dir':str(team)})
            (team/'reports').mkdir();(team/'reports').chmod(0o700)   # what mkdir under umask 077 leaves behind
            with patch('meeting_os.reports.subprocess.run',side_effect=fake_run):
                path=reports.write_meeting_report(s,mid,data)
            self.assertEqual(self.mode(path),0o644)
            self.assertEqual(self.mode(Path(path).parent),0o755);self.assertEqual(self.mode(team/'reports'),0o755)
            s.close()
    def test_tighten_modes_pulls_the_old_files_back(self):
        with tempfile.TemporaryDirectory() as tmp:
            data=Path(tmp)/'data';data.mkdir()
            reports.save_settings(data,{'report_dir':str(data/'shared')})
            personal=data/'shared'/'Test-Mac';personal.mkdir(parents=True)
            paths=[reports.settings_path(data),data/reports.PROBE_CACHE,data/'last-job.log',personal/reports.HEARTBEAT_FILE]
            for path in paths[1:]: path.write_text('{}',encoding='utf-8')
            for path in paths: path.chmod(0o644)   # what an older build (or a copied folder) leaves behind
            data.chmod(0o755)
            with patch('meeting_os.reports.subprocess.run',side_effect=fake_run):
                fixed=reports.tighten_modes(data)
            self.assertEqual(self.mode(data),0o700)
            for path in paths: self.assertEqual(self.mode(path),0o600,path)
            self.assertEqual(len(fixed),5)
            with patch('meeting_os.reports.subprocess.run',side_effect=fake_run):
                self.assertEqual(reports.tighten_modes(data),[str(data)])   # nothing left to fix
    def test_the_bridge_tightens_once_per_run(self):
        from unittest.mock import MagicMock
        from meeting_os import desktop
        from meeting_os.desktop import dispatch
        with tempfile.TemporaryDirectory() as tmp:
            data=Path(tmp);db=data/'meeting-os.sqlite';Store(db).close()
            reports.save_settings(data,{'report_dir':str(data/'shared')})
            desktop._TIGHTENED=False
            with patch('meeting_os.reports.tighten_modes',MagicMock()) as tighten,patch('meeting_os.reports.write_heartbeat',return_value=None):
                dispatch({'action':'heartbeat'},db);dispatch({'action':'heartbeat'},db)
            self.assertEqual(tighten.call_count,1)


class HomePathRedactionTests(unittest.TestCase):
    """A report folder is iCloud Drive or a shared team drive. '/Users/ayse/...' inside it is a person's name,
    and the Settings caption promises numbers, scores, costs, model names and error lines — not paths."""
    def test_the_helper_replaces_only_the_account_name(self):
        self.assertEqual(reports.redact_home('/Users/ayse/Library/x'),'/Users/…/Library/x')
        self.assertEqual(reports.redact_home('bak /Users/ayse ve /Users/mehmet/rec'),'bak /Users/… ve /Users/…/rec')
        self.assertEqual(reports.redact_home('/opt/data/x'),'/opt/data/x')
        for junk in (None,5,True): self.assertEqual(reports.redact_home(junk),junk)
        self.assertEqual(reports.redact_paths({'/Users/ayse/k':['/Users/ayse/a',{'b':'/Users/ayse'}]}),{'/Users/…/k':['/Users/…/a',{'b':'/Users/…'}]})
    def test_the_recording_heartbeat_never_carries_a_home_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            data=Path(tmp);reports.save_settings(data,{'report_dir':str(data/'shared')})
            with patch('meeting_os.reports.subprocess.run',side_effect=fake_run):
                path=reports.write_recording_heartbeat(data,{'meeting':'abc','capture_dir':'/Users/ayse/Library/Application Support/MeetingOS/recordings/abc','elapsed_seconds':61})
            text=Path(path).read_text(encoding='utf-8')
            self.assertNotIn('/Users/ayse',text);self.assertIn('/Users/…/Library/Application Support/MeetingOS/recordings/abc',text)
            self.assertEqual(json.loads(text)['line'],'kayıt sürüyor · 1 dk · henüz parça yok')
    def test_the_hourly_heartbeat_and_the_meeting_report_are_redacted_too(self):
        with tempfile.TemporaryDirectory() as tmp:
            data=Path(tmp);db=data/'meeting-os.sqlite';s=Store(db)
            mid=s.create_meeting('Sprint',{'capture_dir':'/Users/ayse/rec/abc'})
            s.add_segment(mid,Segment(0,5,'Merhaba','system','S0'));s.status(mid,'complete');s.close()
            (data/'last-job.log').write_text('Meeting OS: /Users/ayse/rec/abc açılamadı\n',encoding='utf-8')
            reports.save_settings(data,{'report_dir':str(data/'shared')})
            s=Store(db)
            with patch('meeting_os.reports.subprocess.run',side_effect=fake_run):
                beat=Path(reports.write_heartbeat(s,data,app={'version':'t','commit':None})).read_text(encoding='utf-8')
                report=Path(reports.write_meeting_report(s,mid,data,version='t')).read_text(encoding='utf-8')
            s.close()
            for text in (beat,report):
                self.assertNotIn('/Users/ayse',text);self.assertIn('/Users/…',text)


class LegacyDefaultNameTests(unittest.TestCase):
    """1.2.42 persisted the old default 'Boran' on every settings save; only a typed name counts (10 Sep 2026)."""
    def test_persisted_legacy_default_is_not_a_name(self):
        import tempfile, json
        from pathlib import Path
        from meeting_os import reports
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp,'settings.json').write_text(json.dumps({'user_name':'Boran'}))
            self.assertEqual(reports.settings_owner(tmp),'')
            self.assertEqual(reports.owner_rename_targets('', 'Ayşe'),['Ben','Boran'])
            saved=reports.save_settings(tmp,{'user_name':'Boran'})   # the real Boran types his own name
            self.assertTrue(saved['user_name_confirmed']); self.assertEqual(reports.settings_owner(tmp),'Boran')
    def test_empty_value_never_wipes_a_stored_name(self):
        import tempfile
        from meeting_os import reports
        with tempfile.TemporaryDirectory() as tmp:
            reports.save_settings(tmp,{'user_name':'Ayşe'})
            reports.save_settings(tmp,{'user_name':'','share_text':True})
            self.assertEqual(reports.settings_owner(tmp),'Ayşe')
            reports.save_settings(tmp,{'user_name':'','user_name_clear':True})
            self.assertEqual(reports.settings_owner(tmp),'')


class AudioRetentionWarningTests(unittest.TestCase):
    """One retention setting deletes a whole week of recordings on the same day; the first warning must not be
    the empty player."""
    def meeting(self, store, title, age_days, **meta):
        from datetime import datetime, timedelta, timezone
        mid = store.create_meeting(title, {'paths': {'system': '/tmp/a.wav'}, **meta})
        store.add_segment(mid, Segment(0, 5, 'Merhaba', 'system', 'S0')); store.status(mid, 'complete')
        with store.db: store.db.execute('UPDATE meetings SET created=? WHERE id=?', ((datetime.now(timezone.utc) - timedelta(days=age_days)).isoformat(), mid))
        return mid

    def test_it_warns_three_days_before_the_oldest_recording_goes(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / 'meeting-os.sqlite'; s = Store(db)
            self.meeting(s, 'Eski', 28); self.meeting(s, 'Daha eski ama korunuyor', 29, keep=True); self.meeting(s, 'Yeni', 2)
            self.assertIsNone(reports.audio_retention_warning(s, 0))          # retention off
            self.assertIsNone(reports.audio_retention_warning(s, 90))         # nothing is close
            warning = reports.audio_retention_warning(s, 30)
            self.assertEqual((warning['meetings'], warning['retention_days'], warning['days_left']), (1, 30, 1))
            self.assertIn('1 kaydın sesi yarın silinecek (30 gün)', warning['line'])   # the countdown, not the trigger window
            self.assertIn('Sesi koru', warning['line']); s.close()

    def test_a_recording_whose_audio_is_already_gone_is_not_counted(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / 'meeting-os.sqlite'; s = Store(db)
            self.meeting(s, 'Sesi silinmiş', 29, audio_removed='2026-01-01T00:00:00+00:00')
            self.assertIsNone(reports.audio_retention_warning(s, 30)); s.close()

    def test_the_housekeeping_answer_carries_it(self):
        from meeting_os.desktop import dispatch
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp); db = data / 'meeting-os.sqlite'; s = Store(db); self.meeting(s, 'Eski', 28); s.close()
            reports.save_settings(data, {'audio_retention_days': 30})
            self.assertEqual(dispatch({'action': 'storage_housekeeping'}, db)['retention_warning']['meetings'], 1)
            reports.save_settings(data, {'audio_retention_days': 0})
            self.assertIsNone(dispatch({'action': 'storage_housekeeping'}, db)['retention_warning'])


class TextRetentionTests(unittest.TestCase):
    """`text_retention_days` deletes the meeting itself, not just its audio, so both halves of it are tested:
    what the setting will accept, and who the pass would take."""
    def meeting(self, store, title, age_days, status='complete', **meta):
        from datetime import datetime, timedelta, timezone
        mid = store.create_meeting(title, meta)
        store.add_segment(mid, Segment(0, 5, 'Merhaba', 'system', 'S0'))
        with store.db: store.db.execute('UPDATE meetings SET created=?,status=? WHERE id=?', ((datetime.now(timezone.utc) - timedelta(days=age_days)).isoformat(), status, mid))
        return mid

    def test_the_setting_is_off_by_default_and_only_accepts_a_day_count(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp)
            self.assertEqual(reports.load_settings(data)['text_retention_days'], 0)
            self.assertEqual(reports.save_settings(data, {'text_retention_days': 365})['text_retention_days'], 365)
            self.assertEqual(reports.save_settings(data, {'text_retention_days': 0})['text_retention_days'], 0)
            self.assertEqual(reports.save_settings(data, {'text_retention_days': 3650})['text_retention_days'], 3650)
            for bad in (3651, -1, True, '30', 30.0, None):
                self.assertEqual(reports.save_settings(data, {'text_retention_days': bad})['text_retention_days'], 3650)   # refused, the stored value stands
            self.assertEqual(json.loads((data / 'settings.json').read_text(encoding='utf-8'))['text_retention_days'], 3650)

    def test_it_counts_only_the_meetings_the_next_pass_would_really_take(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / 'meeting-os.sqlite'; s = Store(db)
            self.meeting(s, 'Eski', 28); self.meeting(s, 'Korunan', 40, keep=True); self.meeting(s, 'Yeni', 2)
            self.meeting(s, 'Yarım', 60, status='incomplete'); self.meeting(s, 'Bulut bekliyor', 60, cloud_error={'kind': 'credit'})
            self.assertIsNone(reports.text_retention_warning(s, 0))     # off
            self.assertIsNone(reports.text_retention_warning(s, 90))    # nothing is close
            warning = reports.text_retention_warning(s, 30)
            self.assertEqual((warning['meetings'], warning['retention_days'], warning['days_left']), (1, 30, 1))
            self.assertIn('1 toplantının yazısı yarın tümüyle silinecek (30 gün)', warning['line'])
            self.assertIn('transkript, özet ve görevler', warning['line'])
            self.assertEqual([row['title'] for row, _ in reports.text_retention_candidates(s, 30)], [])   # not due yet without the lookahead
            self.assertEqual([row['title'] for row, _ in reports.text_retention_candidates(s, 20)], ['Eski'])
            s.close()

    def test_a_meeting_a_job_is_running_on_is_never_a_candidate(self):
        from meeting_os.recovery import current_job_metadata
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / 'meeting-os.sqlite'; s = Store(db)
            self.meeting(s, 'İş sürüyor', 60, status='complete', **current_job_metadata())
            self.assertEqual(reports.text_retention_candidates(s, 30), [])
            self.assertIsNone(reports.text_retention_warning(s, 30)); s.close()

    def test_the_storage_card_and_the_housekeeping_answer_both_carry_it(self):
        from meeting_os.desktop import dispatch
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp); db = data / 'meeting-os.sqlite'; s = Store(db); self.meeting(s, 'Eski', 28); s.close()
            reports.save_settings(data, {'text_retention_days': 30, 'audio_retention_days': 0})
            self.assertEqual(dispatch({'action': 'storage_report'}, db)['text_retention_warning']['meetings'], 1)
            self.assertEqual(dispatch({'action': 'storage_housekeeping'}, db)['text_retention_warning']['meetings'], 1)
            reports.save_settings(data, {'text_retention_days': 0})
            self.assertIsNone(dispatch({'action': 'storage_report'}, db)['text_retention_warning'])
