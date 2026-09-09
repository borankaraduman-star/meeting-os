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

class UserNameTests(unittest.TestCase):
    def test_the_name_is_validated_and_falls_back_to_the_label_older_recordings_carry(self):
        with tempfile.TemporaryDirectory() as tmp:
            data=Path(tmp)
            self.assertEqual(reports.load_settings(data)['user_name'],reports.DEFAULT_USER_NAME)
            self.assertEqual(reports.settings_owner(data),'Boran')   # no settings file: segments already labelled “Boran” keep matching
            self.assertEqual(reports.save_settings(data,{'user_name':'  Ayşe Yılmaz  '})['user_name'],'Ayşe Yılmaz')
            self.assertEqual(reports.settings_owner(data),'Ayşe Yılmaz')
            for junk in ('','   ','x'*(reports.NAME_LIMIT+1),None,5,True,['Ayşe']):
                self.assertEqual(reports.save_settings(data,{'user_name':junk})['user_name'],'Ayşe Yılmaz')
            self.assertEqual(reports.save_settings(data,{'user_name':'x'*reports.NAME_LIMIT})['user_name'],'x'*reports.NAME_LIMIT)
            reports.settings_path(data).write_text(json.dumps({'user_name':'   '}),encoding='utf-8')
            self.assertEqual(reports.settings_owner(data),'Boran')   # a blank value in the file is not a name
    def test_the_bridge_reads_and_writes_the_name(self):
        from meeting_os.desktop import dispatch
        with tempfile.TemporaryDirectory() as tmp:
            data=Path(tmp);db=data/'meeting-os.sqlite';Store(db).close()
            self.assertEqual(dispatch({'action':'report_settings'},db)['user_name'],'Boran')
            self.assertEqual(dispatch({'action':'report_settings_set','changes':{'user_name':'Deniz'}},db)['user_name'],'Deniz')
            self.assertEqual(reports.settings_owner(data),'Deniz')
    def test_the_microphone_speaker_label_follows_the_setting(self):
        from meeting_os.cloud_finalize import source_labels, speaker_label
        self.assertEqual(source_labels('Deniz'),{'mic':'Deniz','system':'Karşı taraf'})
        self.assertEqual(source_labels(None),source_labels('   '))
        self.assertEqual(speaker_label('mic','2',0,False,'Deniz'),'Deniz')
        self.assertEqual(speaker_label('system',None,0,False,'Deniz'),'Karşı taraf')
        self.assertEqual(speaker_label('system','1',2,True,'Deniz'),'Konuşmacı 3-2')   # the setting never touches diarized labels
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
