import unittest,tempfile,json
from pathlib import Path
from meeting_os.desktop import dispatch,export_text,timestamp
from meeting_os.store import Store
from meeting_os.types import Segment

class DesktopTests(unittest.TestCase):
 def test_snapshot_labels_and_export_do_not_leak_embeddings(self):
  with tempfile.TemporaryDirectory() as tmp:
   db=Path(tmp)/'db'; s=Store(db); mid=s.create_meeting('Türkçe',{'paths':{'system':'/tmp/a.wav'}})
   sid=s.add_segment(mid,Segment(1,5,'İpek, rollout yarın.','system','S0',embedding=[1.,0.],embedding_model='test'))
   s.status(mid,'complete');s.close()
   request={'action':'label','meeting':mid,'segment':sid,'name':'İpek'}
   dispatch(request,db)
   snap=dispatch({'action':'snapshot','meeting':mid},db)
   self.assertEqual(snap['segments'][0]['speaker_name'],'İpek');self.assertEqual(snap['profiles'],[])
   dest=Path(tmp)/'export.json';dispatch({'action':'export','meeting':mid,'path':str(dest),'format':'json'},db)
   self.assertNotIn('embedding',json.loads(dest.read_text())[0])
   self.assertIn('İpek',export_text(snap['segments'],'srt'))
   with self.assertRaises(ValueError): dispatch({**request,'action':'enroll'},db)
   dispatch({**request,'action':'enroll','confirmed_clean':True},db)
   self.assertEqual(len(dispatch({'action':'snapshot'},db)['profiles']),1)
 def test_delete_meeting_removes_rows_and_owned_folders_only(self):
  from meeting_os.desktop import meeting_files
  with tempfile.TemporaryDirectory() as tmp:
   data=Path(tmp);db=data/'meeting-os.sqlite';s=Store(db)
   own=data/'imports'/'abc';own.mkdir(parents=True);(own/'audio.wav').write_bytes(b'RIFF')
   outside=data/'..'/'elsewhere';outside.mkdir(exist_ok=True);(outside/'keep.wav').write_bytes(b'RIFF')
   mid=s.create_meeting('Sil',{'paths':{'system':str(own/'audio.wav'),'mic':str(outside/'keep.wav')},'capture_dir':str(data)})
   s.add_segment(mid,Segment(0,3,'Merhaba','system','S0'));s.status(mid,'complete')
   other=s.create_meeting('Kalsın');s.add_segment(other,Segment(0,3,'Selam','system','S0'));s.status(other,'complete')
   s.enroll('Boran',[1.,0.],'test',3.0,f'{mid}:1')
   s.db.executescript("CREATE TABLE cloud_sources(meeting TEXT PRIMARY KEY REFERENCES meetings(id),digest TEXT,plan TEXT,model TEXT);CREATE TABLE cloud_chunks(meeting TEXT REFERENCES meetings(id),position INTEGER,usage TEXT,PRIMARY KEY(meeting,position));")
   with s.db:s.db.execute("INSERT INTO cloud_sources VALUES(?,?,?,?)",(mid,'d','[]','m'));s.db.execute("INSERT INTO cloud_chunks VALUES(?,?,?)",(mid,0,'{}'))
   s.close()
   self.assertEqual(meeting_files({'paths':{'system':str(own/'audio.wav'),'mic':str(outside/'keep.wav')},'capture_dir':str(data)},data),[own.resolve()])
   result=dispatch({'action':'delete_meeting','meeting':mid},db)
   self.assertTrue(result['deleted']);self.assertEqual(result['removed_folders'],[str(own.resolve())])
   self.assertFalse(own.exists());self.assertTrue((outside/'keep.wav').exists())
   snap=dispatch({'action':'snapshot'},db)
   self.assertEqual([m['id'] for m in snap['meetings']],[other]);self.assertEqual(len(snap['profiles']),1)
   s=Store(db)
   self.assertEqual(s.db.execute('SELECT COUNT(*) FROM segments WHERE meeting=?',(mid,)).fetchone()[0],0)
   self.assertEqual(s.db.execute('SELECT COUNT(*) FROM cloud_chunks').fetchone()[0],0)
   self.assertEqual(s.db.execute('SELECT COUNT(*) FROM segments').fetchone()[0],1);s.close()
   with self.assertRaises(ValueError):dispatch({'action':'delete_meeting','meeting':mid},db)
 def test_vocabulary_is_saved_next_to_the_data_and_never_dirties_the_checkout(self):
  # Saving the Settings vocabulary box used to write into the git checkout: git went dirty, updater.check
  # reported dirty and update.sh refused, so one saved word disabled updates for good.
  from meeting_os import glossary as G
  from meeting_os.cli import ROOT
  with tempfile.TemporaryDirectory() as tmp:
   db=Path(tmp)/'meeting-os.sqlite';Store(db).close()
   repo=Path(tmp)/'repo';repo.mkdir();seed=repo/'vocabulary.txt';seed.write_text('Tohum\n',encoding='utf-8')
   before=(ROOT/'vocabulary.txt').read_text(encoding='utf-8')
   self.assertEqual(dispatch({'action':'vocabulary'},db)['text'],before)      # first read seeds from the checkout
   self.assertTrue((Path(tmp)/'vocabulary.txt').is_file())
   self.assertEqual(dispatch({'action':'vocabulary','text':'PMD\nOKR\n'},db)['text'],'PMD\nOKR\n')
   self.assertEqual((Path(tmp)/'vocabulary.txt').read_text(encoding='utf-8'),'PMD\nOKR\n')
   self.assertEqual((ROOT/'vocabulary.txt').read_text(encoding='utf-8'),before)   # the tracked seed is untouched
   self.assertIn('PMD',[e['term'] for e in G.load(tmp,ROOT)])
   # the seed is copied once; later reads keep what the user saved
   self.assertEqual(G.vocabulary_path(tmp,repo).read_text(encoding='utf-8'),'PMD\nOKR\n')
   fresh=Path(tmp)/'fresh';fresh.mkdir()
   self.assertEqual(G.vocabulary_path(fresh,repo).read_text(encoding='utf-8'),'Tohum\n')
 def test_setup_status_reports_key_presence_and_glossary(self):
  from unittest.mock import patch
  with tempfile.TemporaryDirectory() as tmp:
   db=Path(tmp)/'meeting-os.sqlite';Store(db).close();(Path(tmp)/'vocabulary.txt').write_text('PMD\n')
   class R:returncode=0;stdout='Test-Mac\n';stderr=''
   with patch('subprocess.run',return_value=R()):r=dispatch({'action':'setup_status'},db)
   self.assertEqual((r['api_key'],r['glossary_terms']>=1,r['glossary_shared'],r['update_behind']),(True,True,False,0))
   self.assertEqual((r['reports_on'],r['reports_writable'],r['reports_written']),(True,True,0))
   class F:returncode=44;stdout='';stderr=''
   with patch('subprocess.run',return_value=F()):self.assertFalse(dispatch({'action':'setup_status'},db)['api_key'])
 def test_archive_converts_full_wav_to_flac_and_housekeeping_respects_retention(self):
  import numpy as np, soundfile as sf
  from meeting_os import reports
  from meeting_os.audio_archive import archive_meeting
  with tempfile.TemporaryDirectory() as tmp:
   data=Path(tmp);db=data/'meeting-os.sqlite';s=Store(db);rec=data/'recordings'/'cap';rec.mkdir(parents=True)
   wav=rec/'system-full.wav';sf.write(wav,(np.random.default_rng(1).standard_normal(16000*3)*0.1).astype('float32'),16000,subtype='FLOAT')
   mid=s.create_meeting('Arşiv',{'paths':{'system':str(wav)},'capture_dir':str(rec),'cloud_mode':'capture'});s.status(mid,'complete')
   saved=archive_meeting(s,mid);self.assertGreater(saved,0);self.assertFalse(wav.exists())
   meta=json.loads(s.db.execute('SELECT metadata FROM meetings WHERE id=?',(mid,)).fetchone()[0]);flac=Path(meta['paths']['system']);self.assertEqual(flac.suffix,'.flac')
   audio,rate=sf.read(flac,dtype='float32');self.assertEqual((len(audio),rate),(16000*3,16000));self.assertEqual(archive_meeting(s,mid),0)   # idempotent
   s.close()
   st=reports.save_settings(data,{'audio_retention_days':0});self.assertEqual(st['audio_retention_days'],0)
   r=dispatch({'action':'storage_housekeeping'},db);self.assertEqual((r['retention_days'],r['removed_meetings']),(0,0));self.assertTrue(flac.exists())
   reports.save_settings(data,{'audio_retention_days':1})
   Store(db).db.execute("UPDATE meetings SET created='2025-01-01T10:00:00+00:00' WHERE id=?",(mid,)).connection.commit()
   r=dispatch({'action':'storage_housekeeping'},db);self.assertEqual(r['removed_meetings'],1);self.assertFalse(rec.exists())
   self.assertEqual(reports.save_settings(data,{'audio_retention_days':True})['audio_retention_days'],1)   # bools are not day counts
 def test_cost_report_sums_real_charges_by_month(self):
  from datetime import datetime,timezone
  with tempfile.TemporaryDirectory() as tmp:
   db=Path(tmp)/'meeting-os.sqlite';s=Store(db);a=s.create_meeting('Bu ay',{});b=s.create_meeting('Eski',{})
   s.db.executescript("CREATE TABLE cloud_chunks(meeting TEXT,position INTEGER,usage TEXT,PRIMARY KEY(meeting,position));INSERT INTO cloud_chunks VALUES('"+a+"',0,'{\"cost\":0.01,\"seconds\":300}');INSERT INTO cloud_chunks VALUES('"+a+"',1,'{\"skipped\":\"echo\"}');INSERT INTO cloud_chunks VALUES('"+b+"',0,'{\"cost\":0.02,\"seconds\":600}');UPDATE meetings SET created='2025-01-05T10:00:00+00:00' WHERE id='"+b+"';")
   s.close()
   r=dispatch({'action':'cost_report'},db)
   self.assertEqual(r['month']['label'],datetime.now(timezone.utc).strftime('%Y-%m'));self.assertEqual((r['month']['usd'],r['month']['meetings'],r['month']['minutes']),(0.01,1,5.0))
   self.assertEqual((r['all']['usd'],r['all']['meetings'],r['all']['minutes']),(0.03,2,15.0));self.assertEqual(r['recent'][0]['title'],'Bu ay')
 def test_meeting_context_stores_calendar_hints(self):
  with tempfile.TemporaryDirectory() as tmp:
   db=Path(tmp)/'meeting-os.sqlite';s=Store(db);mid=s.create_meeting('9 Eyl 2026 14:05',{'engine':'openrouter'});s.close()
   r=dispatch({'action':'meeting_context','meeting':mid,'calendar':{'title':'Sprint planlama','attendees':['Ayşe Yılmaz',' ','Ali'],'start':'2026-09-09T11:00:00Z'}},db)
   self.assertEqual(r,{'attendees':['Ayşe Yılmaz','Ali']})
   meta=[m for m in dispatch({'action':'snapshot'},db)['meetings'] if m['id']==mid][0]['metadata']
   self.assertEqual((meta['calendar']['title'],meta['calendar']['attendees'],meta['engine']),('Sprint planlama',['Ayşe Yılmaz','Ali'],'openrouter'))
   with self.assertRaises(ValueError):dispatch({'action':'meeting_context','meeting':'yok','calendar':{}},db)
 def test_snapshot_skips_segments_when_fingerprint_matches(self):
  with tempfile.TemporaryDirectory() as tmp:
   db=Path(tmp)/'meeting-os.sqlite';s=Store(db);a=s.create_meeting('A',{})
   s.add_segment(a,Segment(0,5,'x','system','Konuşmacı 1'));s.status(a,'complete');s.close()
   r=dispatch({'action':'snapshot','meeting':a},db);self.assertEqual(len(r['segments']),1);h=r['segments_hash']
   r2=dispatch({'action':'snapshot','meeting':a,'segments_hash':h},db);self.assertIsNone(r2['segments']);self.assertEqual(r2['segments_hash'],h)
   Store(db).correct(a,'Konuşmacı 1','Ayşe')
   r3=dispatch({'action':'snapshot','meeting':a,'segments_hash':h},db);self.assertEqual(r3['segments'][0]['speaker_name'],'Ayşe');self.assertNotEqual(r3['segments_hash'],h)
 def test_snapshot_carries_per_meeting_stats(self):
  with tempfile.TemporaryDirectory() as tmp:
   db=Path(tmp)/'meeting-os.sqlite';s=Store(db);a=s.create_meeting('A',{});b=s.create_meeting('B',{})
   s.add_segment(a,Segment(0,70,'x','system','Konuşmacı 1',speaker_name='Ayşe'));s.add_segment(a,Segment(70,90,'y','system','Konuşmacı 2'));s.add_segment(a,Segment(0,60,'echo','mic','mic:S0'))
   s.status(a,'complete');s.status(b,'complete');s.close()
   st={m['id']:m['stats'] for m in dispatch({'action':'snapshot'},db)['meetings']}
   self.assertEqual(st[a],{'segments':2,'seconds':90.0,'speakers':2,'names':['Ayşe']});self.assertEqual(st[b],{'segments':0,'seconds':0.0,'speakers':0})
 def test_delete_meeting_refuses_active_job(self):
  from meeting_os.recovery import current_job_metadata
  with tempfile.TemporaryDirectory() as tmp:
   db=Path(tmp)/'db';s=Store(db);mid=s.create_meeting('Canlı',current_job_metadata());s.close()
   with self.assertRaises(ValueError):dispatch({'action':'delete_meeting','meeting':mid},db)
   self.assertEqual(len(dispatch({'action':'snapshot'},db)['meetings']),1)
 def test_review_queue_lists_reasons_in_priority_order(self):
  with tempfile.TemporaryDirectory() as tmp:
   db=Path(tmp)/'db';s=Store(db);mid=s.create_meeting('R',{})
   flags=['cloud_transcript','cloud_diarization']
   s.add_segment(mid,Segment(0,20,'uzun','system','Konuşmacı 1',metrics={'cluster':'0:0','identity':{'name':None,'candidate':'Ayşe','similarity':0.85,'suggested':'Ayşe'}},flags=flags))
   s.add_segment(mid,Segment(20,25,'devam','system','Konuşmacı 1',metrics={'cluster':'0:0','identity':{'name':None,'candidate':'Ayşe','similarity':0.85,'suggested':'Ayşe'}},flags=flags))
   s.add_segment(mid,Segment(25,40,'isimsiz','system','Konuşmacı 2',metrics={'cluster':'0:1','identity':{'name':None,'candidate':'Mehmet','similarity':0.7,'suggested':None}},flags=flags))
   s.add_segment(mid,Segment(40,43,'kısa','system','Konuşmacı 3',speaker_name='Ali',metrics={'cluster':'0:2','cluster_embedding':3.0,'identity':{'name':'Ali','similarity':0.9}},flags=flags))
   s.add_segment(mid,Segment(43,50,'çakışma','system','unknown',flags=flags+['speaker_ambiguous']))
   s.status(mid,'complete');s.close()
   q=dispatch({'action':'review_queue','meeting':mid},db)
   kinds=[i['kind'] for i in q['items']]
   self.assertEqual(kinds,['suggested_name','ambiguous','unnamed_speaker','short_match']);self.assertEqual(q['count'],4)
   self.assertEqual(q['items'][0]['suggested'],'Ayşe');self.assertIn('Mehmet',q['items'][2]['reason']);self.assertIn('15 sn',q['items'][2]['reason'])
 def test_check_duplicate_matches_registered_digest_or_name_and_size(self):
  from meeting_os.import_registry import digest_path,find_duplicate
  with tempfile.TemporaryDirectory() as tmp:
   data=Path(tmp);db=data/'meeting-os.sqlite';s=Store(db)
   audio=data/'toplanti.m4a';audio.write_bytes(b'audio-bytes-1');other=data/'baska.m4a';other.write_bytes(b'audio-bytes-2')
   mid=s.create_meeting('İlk içe aktarım',{'engine':'openrouter','model':'microsoft/mai-transcribe-2','cloud_mode':'file','original_name':'toplanti.m4a'})
   s.status(mid,'complete');legacy=s.create_meeting('Eski',{'original_name':'baska.m4a'});s.close()
   self.assertIsNone(dispatch({'action':'check_duplicate','path':str(audio)},db)['duplicate'])  # name alone is not enough
   with self.assertRaises(ValueError):dispatch({'action':'register_import_digest','meeting':mid,'digest':'nope'},db)
   with self.assertRaises(ValueError):dispatch({'action':'register_import_digest','meeting':'missing','digest':digest_path(audio)},db)
   self.assertTrue(dispatch({'action':'register_import_digest','meeting':mid,'digest':digest_path(audio),'size':audio.stat().st_size},db)['registered'])
   result=dispatch({'action':'check_duplicate','path':str(audio)},db)
   self.assertEqual(result['duplicate'],{'meeting':mid,'title':'İlk içe aktarım','model':'microsoft/mai-transcribe-2','status':'complete'})
   self.assertEqual(result['digest'],digest_path(audio));self.assertEqual(result['size'],len(b'audio-bytes-1'))
   self.assertIsNone(dispatch({'action':'check_duplicate','path':str(other)},db)['duplicate'])
   audio.write_bytes(b'audio-bytes-X')  # same name and size, different content: content wins
   self.assertIsNone(dispatch({'action':'check_duplicate','path':str(audio)},db)['duplicate'])
   s=Store(db)
   meta=json.loads(s.db.execute('SELECT metadata FROM meetings WHERE id=?',(mid,)).fetchone()[0])
   self.assertEqual(meta['original_name'],'toplanti.m4a');self.assertEqual(meta['engine'],'openrouter')  # merged, not replaced
   with s.db:s.db.execute('UPDATE meetings SET metadata=? WHERE id=?',(json.dumps({'original_name':'baska.m4a','original_size':len(b'audio-bytes-2')}),legacy))
   self.assertEqual(find_duplicate(s,'0'*64,'baska.m4a',len(b'audio-bytes-2'))['meeting'],legacy)  # size without digest falls back to name+size
   self.assertIsNone(find_duplicate(s,'0'*64,'baska.m4a',999));s.close()
   with self.assertRaises(ValueError):dispatch({'action':'check_duplicate','path':str(data/'yok.m4a')},db)
 def test_storage_report_walks_data_dir_without_deleting(self):
  from meeting_os.recovery import current_job_metadata
  with tempfile.TemporaryDirectory() as tmp:
   data=Path(tmp);db=data/'meeting-os.sqlite';s=Store(db)
   rec=data/'recordings'/'r1';rec.mkdir(parents=True);(rec/'mic.wav').write_bytes(b'x'*300);(rec/'system.wav').write_bytes(b'y'*200)
   rec2=data/'recordings'/'r2';rec2.mkdir();(rec2/'mic.wav').write_bytes(b'x'*100)
   imp=data/'imports'/'i1';imp.mkdir(parents=True);(imp/'audio.wav').write_bytes(b'z'*50)
   (data/'imports'/'orphan').mkdir();(data/'imports'/'orphan'/'a.wav').write_bytes(b'q'*25)
   big=s.create_meeting('Kayıt',{'capture_dir':str(rec)});small=s.create_meeting('İçe aktarım',{'paths':{'system':str(imp/'audio.wav')}})
   text=s.create_meeting('Metin',{'text_only':True});live=s.create_meeting('Canlı',{**current_job_metadata(),'capture_dir':str(rec2)});s.close()
   report=dispatch({'action':'storage_report'},db)
   self.assertEqual(report['totals']['recordings'],600);self.assertEqual(report['totals']['imports'],75)
   self.assertGreater(report['totals']['database'],0);self.assertEqual(report['total'],675+report['totals']['database'])
   self.assertEqual([m['meeting'] for m in report['meetings']],[big,live,small]);self.assertNotIn(text,[m['meeting'] for m in report['meetings']])
   self.assertEqual(report['meetings'][0]['bytes'],500);self.assertEqual(report['meetings'][2]['bytes'],50)
   self.assertFalse(report['meetings'][0]['active']);self.assertTrue(report['meetings'][1]['active'])
   self.assertTrue((rec/'mic.wav').exists());self.assertTrue((data/'imports'/'orphan'/'a.wav').exists())
 def test_agenda_collects_open_tasks_questions_and_decisions_with_sources(self):
  from meeting_os.memory import Memory
  with tempfile.TemporaryDirectory() as tmp:
   db=Path(tmp)/'db';s=Store(db);mid=s.create_meeting('Sprint planı',{})
   sid=s.add_segment(mid,Segment(0,5,'Yarın raporu ben çıkaracağım. iOS önce mi gidecek?','system','S0'));s.status(mid,'complete')
   mem=Memory(s);payload={'summary':[],'decisions':[{'text':'Önce iOS','evidence':[{'segment_id':sid,'quote':'iOS önce'}]}],'risks':[],
     'questions':[{'text':'Rapor ne zaman?','evidence':[{'segment_id':sid,'quote':'Yarın raporu'}]}],
     'actions':[{'title':'Raporu çıkarmak','owner':'Boran','due_text':'yarın','evidence':[{'segment_id':sid,'quote':'Yarın raporu ben çıkaracağım'}]}]}
   mem.save_analysis(mid,mem.current_hash(mid),'test-model',payload);s.close()
   out=Path(tmp)/'gundem.md';r=dispatch({'action':'agenda','path':str(out)},db)
   self.assertEqual((r['open_tasks'],r['questions'],r['decisions'],r['meetings']),(1,1,1,1))
   text=out.read_text();self.assertIn('Raporu çıkarmak',text);self.assertIn('Rapor ne zaman?',text);self.assertIn('Önce iOS',text);self.assertIn('Kaynak #',text)
 def test_reports_settings_write_and_summarize(self):
  from meeting_os import reports
  from meeting_os.memory import Memory
  with tempfile.TemporaryDirectory() as tmp:
   data=Path(tmp);db=data/'meeting-os.sqlite';s=Store(db)
   st=reports.save_settings(data,{'report_dir':str(data/'shared'),'share_text':False,'share_reports':True,'auto_update':True,'ignored':1})
   self.assertEqual((st['share_text'],st['auto_update'],st['report_dir']),(False,True,str(data/'shared')))
   mid=s.create_meeting('Sprint',{'engine':'openrouter','model':'microsoft/mai-transcribe-2','cloud_mode':'capture','echo_windows_skipped':3,'identity':{'named':1}})
   s.add_segment(mid,Segment(0,30,'Yarın rapor hazır olur.','system','Konuşmacı 1',speaker_name='Ayşe',metrics={'cluster':'0:0','identity':{'name':'Ayşe','similarity':0.95}},flags=['cloud_transcript','cloud_diarization']))
   s.add_segment(mid,Segment(30,40,'Tamam.','system','Konuşmacı 2',metrics={'cluster':'0:1','identity':{'name':None,'similarity':0.7}},flags=['cloud_transcript','cloud_diarization']))
   s.db.executescript("CREATE TABLE cloud_chunks(meeting TEXT,position INTEGER,usage TEXT,PRIMARY KEY(meeting,position));INSERT INTO cloud_chunks VALUES('"+mid+"',0,'{\"cost\":0.002,\"seconds\":40}');INSERT INTO cloud_chunks VALUES('"+mid+"',1,'{\"skipped\":\"echo\"}');")
   s.status(mid,'complete');(data/'last-job.log').write_text('ok\nMeeting OS: OpenRouter HTTP 500. deneme /Users/boran/x\n');s.close()
   path=dispatch({'action':'report_write','meeting':mid},db)['path'];self.assertTrue(path.endswith(f'_{mid}.json'))
   r=json.loads(Path(path).read_text())
   self.assertEqual((r['cost_usd'],r['pieces_skipped'],r['segments'],r['speakers']['Konuşmacı 1']['name']),(0.002,1,2,'Ayşe'))
   self.assertNotIn('transcript',r);self.assertIn('/Users/…',r['errors'][0]);self.assertEqual(r['review_queue'].get('unnamed_speaker'),1)
   reports.save_settings(data,{'share_text':True});dispatch({'action':'report_write','meeting':mid},db)
   self.assertEqual(json.loads(Path(path).read_text())['transcript'][0]['speaker'],'Ayşe')
   summary=dispatch({'action':'reports_summary'},db);self.assertEqual(summary['reports'][0]['named'],1);self.assertEqual(list(summary['hosts'].values())[0]['reports'],1)
   reports.save_settings(data,{'share_reports':False});self.assertIsNone(reports.write_meeting_report(Store(db),mid,data))
   self.assertTrue(Path(path).exists());self.assertEqual(dispatch({'action':'delete_meeting','meeting':mid},db)['removed_reports'],[path]);self.assertFalse(Path(path).exists())
 def test_update_check_parses_git_state(self):
  from unittest.mock import patch
  from meeting_os import updater
  answers={('fetch',):'',('rev-parse','--short','HEAD'):'aaa1111\n',('rev-parse','--short','origin/v0.1'):'bbb2222\n',('rev-list','--count','HEAD..origin/v0.1'):'3\n',('rev-list','--count','origin/v0.1..HEAD'):'0\n',('log',):'Fix a\nFix b\n',('status','--porcelain'):''}
  def fake(root,*args,timeout=25):
   key=next((k for k in answers if args[:len(k)]==k),None)
   class R: returncode=0; stdout=answers.get(key,'')
   return R()
  with patch.object(updater,'_git',fake):
   r=updater.check('/tmp');self.assertTrue(r['available']);self.assertEqual((r['behind'],r['ahead'],r['local'],r['remote'],r['subjects']),(3,0,'aaa1111','bbb2222',['Fix a','Fix b']))
  answers[('status','--porcelain')]=' M x.py\n'
  with patch.object(updater,'_git',fake):
   self.assertFalse(updater.check('/tmp')['available'])
 def test_profile_maintenance_actions(self):
  with tempfile.TemporaryDirectory() as tmp:
   db=Path(tmp)/'db';s=Store(db);mid=s.create_meeting('Toplantı A',{})
   s.enroll('Ayşe',[1.0,0.0],'m',4.0,f'{mid}:speaker:Konuşmacı 1');s.enroll('Ayşe',[0.9,0.1],'m',12.0,f'auto:{mid}:0:0');s.enroll('Ayse',[0.95,0.05],'m',5.0,'manual')
   sid=s.add_segment(mid,Segment(0,5,'x','system','Konuşmacı 2',speaker_name='Ayse',embedding=[0.8,0.2],embedding_model='m'));s.status(mid,'complete');s.close()
   samples=dispatch({'action':'profile_samples','name':'Ayşe'},db)['samples']
   self.assertEqual([(x['kind'],x['meeting_title']) for x in samples],[('küme','Toplantı A'),('otomatik','Toplantı A')])
   why=dispatch({'action':'explain_identity','meeting':mid,'speaker':'Konuşmacı 2'},db)
   self.assertEqual(why['candidates'][0]['name'],'Ayşe');self.assertEqual(why['threshold'],0.87);self.assertGreater(why['candidates'][0]['score'],0.9)
   r=dispatch({'action':'rename_profile','name':'Ayse','new_name':'Ayşe'},db);self.assertEqual(r,{'renamed':1,'merged':True})
   snap=dispatch({'action':'snapshot','meeting':mid},db);self.assertEqual(snap['segments'][0]['speaker_name'],'Ayşe');self.assertEqual([p['samples'] for p in snap['profiles']],[3])
   dispatch({'action':'delete_sample','sample':samples[1]['id']},db);self.assertEqual([p['samples'] for p in dispatch({'action':'snapshot'},db)['profiles']],[2])
   with self.assertRaises(ValueError):dispatch({'action':'delete_sample','sample':999},db)
 def test_continuity_links_similar_tasks_and_decisions_across_meetings(self):
  from meeting_os.memory import Memory
  with tempfile.TemporaryDirectory() as tmp:
   db=Path(tmp)/'db';s=Store(db);mem=Memory(s)
   def meeting(title,task,decision):
    mid=s.create_meeting(title,{});sid=s.add_segment(mid,Segment(0,5,task+' '+decision,'system','S0'));s.status(mid,'complete')
    payload={'summary':[],'decisions':[{'text':decision,'evidence':[{'segment_id':sid,'quote':decision[:12]}]}],'risks':[],'questions':[],'actions':[{'title':task,'owner':'Boran','due_text':None,'evidence':[{'segment_id':sid,'quote':task[:10]}]}]}
    mem.save_analysis(mid,mem.current_hash(mid),'test',payload);return mid
   a=meeting('Pazartesi','Raporu cuma günü çıkarmak','Önce Android sürümü çıkacak')
   b=meeting('Perşembe','Raporu pazartesiye çıkarmak','Önce iOS sürümü çıkacak, Android sonra')
   s.close()
   c=dispatch({'action':'continuity','meeting':b},db)
   self.assertEqual(len(c['related_tasks']),1);self.assertEqual(c['related_tasks'][0]['related'][0]['meeting_title'],'Pazartesi')
   self.assertEqual(len(c['decision_history']),1);self.assertEqual(c['decision_history'][0]['previous'][0]['text'],'Önce Android sürümü çıkacak')
   old=c['related_tasks'][0]['related'][0]['id'];new=c['related_tasks'][0]['task']
   r=dispatch({'action':'supersede_task','old':old,'new':new},db);self.assertEqual(r['superseded'],old)
   tasks={t['id']:t for t in Memory(Store(db)).actions()}
   self.assertEqual(tasks[old]['state'],'dismissed');self.assertEqual(tasks[old]['payload']['superseded_by'],new);self.assertEqual(tasks[new]['payload']['continues'],old)
   with self.assertRaises(ValueError):dispatch({'action':'supersede_task','old':new,'new':new},db)
 def test_document_builder_validates_headings_and_numbers(self):
  from meeting_os.documents import build_document, KINDS
  with tempfile.TemporaryDirectory() as tmp:
   db=Path(tmp)/'db';s=Store(db);mid=s.create_meeting('Ödeme hatası',{})
   a=s.add_segment(mid,Segment(0,10,'Ödeme adımında 3 kullanıcı hata aldı, dönüşüm düştü.','system','Ayşe'))
   b=s.add_segment(mid,Segment(10,20,'Yarın düzeltmeyi deploy edelim.','system','Mehmet'));s.status(mid,'complete')
   calls=[]
   class LLM:
    model_id='m'
    def count(self,t):return 1
    def complete(self,system,user,max_tokens=0,schema=None):
     calls.append(system)
     heads=KINDS['bug'][1]
     if len(calls)==1: return json.dumps({'sections':[{'heading':h,'content':'12 kullanıcı etkilendi' if i==0 else 'x','sources':[a]} for i,h in enumerate(heads)]})  # invented number → rejected once
     return json.dumps({'sections':[{'heading':h,'content':'3 kullanıcı hata aldı.' if i==0 else 'Bilinmiyor; sorulacak.','sources':[a if i<2 else b]} for i,h in enumerate(heads)]})
   doc=build_document(s,mid,'bug',LLM())
   self.assertEqual(len(calls),2);self.assertIn('Kaynakta olmayan sayılar',calls[1]);self.assertEqual(doc['sections'],5);self.assertEqual(doc['sources'],2)
   self.assertTrue(doc['text'].startswith('# Hata raporu: Ödeme hatası'));self.assertIn('## Yeniden üretme adımları',doc['text']);self.assertIn('Kaynak bölümler',doc['text'])
   with self.assertRaises(ValueError):build_document(s,mid,'poem',LLM())
   s.close()
 def test_storage_cleanup_removes_old_audio_only_when_asked_and_respects_keep(self):
  from datetime import datetime,timedelta,timezone
  with tempfile.TemporaryDirectory() as tmp:
   data=Path(tmp);db=data/'meeting-os.sqlite';s=Store(db)
   def rec(name,days,status='complete',keep=None):
    d=data/'recordings'/name;d.mkdir(parents=True);(d/'system-full.wav').write_bytes(b'x'*1000)
    mid=s.create_meeting(name,{'capture_dir':str(d),'paths':{'system':str(d/'system-full.wav')},**({'keep':keep} if keep is not None else {})})
    with s.db:s.db.execute('UPDATE meetings SET created=?,status=? WHERE id=?',((datetime.now(timezone.utc)-timedelta(days=days)).isoformat(),status,mid))
    return mid,d
   old,dold=rec('eski',45);kept,dkept=rec('tutulan',45,keep=True);fresh,dfresh=rec('yeni',3);inc,dinc=rec('yarım',60,status='incomplete');s.close()
   dry=dispatch({'action':'storage_cleanup','days':30},db)
   self.assertTrue(dry['dry_run']);self.assertEqual([m['meeting'] for m in dry['meetings']],[old]);self.assertEqual(dry['bytes'],1000);self.assertTrue((dold/'system-full.wav').exists())
   dispatch({'action':'keep_meeting','meeting':old,'keep':True},db);self.assertEqual(dispatch({'action':'storage_cleanup','days':30},db)['meetings'],[])
   dispatch({'action':'keep_meeting','meeting':old,'keep':False},db)
   real=dispatch({'action':'storage_cleanup','days':30,'dry_run':False},db)
   self.assertFalse(dold.exists());self.assertTrue(dkept.exists());self.assertTrue(dfresh.exists());self.assertTrue(dinc.exists());self.assertEqual(real['bytes'],1000)
   s=Store(db);meta=json.loads(s.db.execute('SELECT metadata FROM meetings WHERE id=?',(old,)).fetchone()[0]);self.assertIn('audio_removed',meta);self.assertNotIn('paths',meta)
   self.assertEqual(s.db.execute('SELECT status FROM meetings WHERE id=?',(old,)).fetchone()[0],'complete');s.close()
 def test_rename_meeting(self):
  with tempfile.TemporaryDirectory() as tmp:
   db=Path(tmp)/'db';s=Store(db);mid=s.create_meeting('9 Eyl 2026 14:05',{});s.close()
   self.assertEqual(dispatch({'action':'rename_meeting','meeting':mid,'title':'  Sprint planlama  '},db),{'title':'Sprint planlama'})
   self.assertEqual(dispatch({'action':'snapshot'},db)['meetings'][0]['title'],'Sprint planlama')
   with self.assertRaises(ValueError):dispatch({'action':'rename_meeting','meeting':mid,'title':'   '},db)
   with self.assertRaises(ValueError):dispatch({'action':'rename_meeting','meeting':'yok','title':'x'},db)
 def test_auto_title_replaces_only_timestamp_titles(self):
  from meeting_os.assistant import auto_title
  with tempfile.TemporaryDirectory() as tmp:
   s=Store(Path(tmp)/'db')
   a=s.create_meeting('Sep 9, 2026 at 5:14\u202fAM',{});b=s.create_meeting('9 Eyl 2026 14:05',{});c_=s.create_meeting('Sprint planı',{})
   res={'summary':[{'text':'Ödeme adımındaki hata nedeniyle dönüşümün düştüğü ve yarın düzeltme çıkılacağı konuşuldu.'}]}
   self.assertEqual(auto_title(s,a,res),'Ödeme adımındaki hata nedeniyle dönüşümün düştüğü ve yarın')  # ends on a content word
   self.assertTrue(auto_title(s,b,res));self.assertIsNone(auto_title(s,c_,res));self.assertIsNone(auto_title(s,a,{'summary':[]}))
   titles={r['id']:r['title'] for r in s.meetings()};self.assertEqual(titles[c_],'Sprint planı');s.close()
 def test_timestamp_rounding(self):
  self.assertEqual(timestamp(59.9996),'00:01:00,000')
 def test_enrollment_rejects_short_context(self):
  with tempfile.TemporaryDirectory() as tmp:
   db=Path(tmp)/'db';s=Store(db);mid=s.create_meeting('Short')
   sid=s.add_segment(mid,Segment(0,4,'Test','system','S0',flags=['short_context_diarization'],embedding=[1.,0.],embedding_model='test'));s.close()
   with self.assertRaises(ValueError):dispatch({'action':'enroll','meeting':mid,'segment':sid,'name':'Boran','confirmed_clean':True},db)
 def test_text_edits_preserve_original_and_do_not_train(self):
  with tempfile.TemporaryDirectory() as tmp:
   db=Path(tmp)/'db';s=Store(db);mid=s.create_meeting('Text')
   sid=s.add_segment(mid,Segment(0,4,'Meşet','system','S0',embedding=[1.,0.],embedding_model='test'));s.status(mid,'complete');s.close()
   dispatch({'action':'edit_text','meeting':mid,'segment':sid,'text':'Meşhed'},db)
   s=Store(db);row=s.segments(mid)[0]
   self.assertEqual(row['text'],'Meşhed');self.assertEqual(row['original_text'],'Meşet');self.assertEqual(row['embedding'],[1.,0.]);self.assertEqual(s.profiles(),[]);s.close()

 def test_desktop_rejects_edits_to_processing_meeting(self):
  with tempfile.TemporaryDirectory() as tmp:
   db=Path(tmp)/'db';s=Store(db);mid=s.create_meeting('Still working')
   sid=s.add_segment(mid,Segment(0,4,'Test','system','S0'));s.close()
   with self.assertRaises(ValueError):dispatch({'action':'label','meeting':mid,'segment':sid,'name':'Test'},db)

 def test_diagnostics_bridge_bypasses_database_and_filters_content(self):
  from unittest.mock import patch
  with tempfile.TemporaryDirectory() as t:
   path=Path(t)/'report.json'
   with patch('meeting_os.desktop.Store') as store:
    result=dispatch({'action':'diagnostics','path':str(path)},Path(t)/'unused-db')
    store.assert_not_called()
   self.assertTrue(result['diagnostics_saved']);self.assertNotIn('meetings',path.read_text())

 def test_snapshot_classifies_processing_owner_without_mutation(self):
  from unittest.mock import patch
  with tempfile.TemporaryDirectory() as t:
   path=Path(t)/'db';db=Store(path);identity={'pid':123,'started_us':1,'boot':'fictional'};mid=db.create_meeting('fictional',{'worker_identity':identity});db.close()
   with patch('meeting_os.recovery.classify',return_value='unknown') as classify:
    result=dispatch({'action':'snapshot','meeting':mid},path)
    classify.assert_called_once_with(identity)
   self.assertEqual(result['meetings'][0]['recovery_state'],'unknown')
   self.assertEqual(result['meetings'][0]['status'],'processing')

 def test_snapshot_reads_the_capture_journal_only_where_it_changes_the_display(self):
  from unittest.mock import patch
  from meeting_os.desktop import capture_state
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);db=root/'db';s=Store(db)
   done=s.create_meeting('Biten',{'capture_dir':tmp});s.status(done,'complete')
   open_one=s.create_meeting('Seçili',{'capture_dir':tmp});s.status(open_one,'complete')
   broken=s.create_meeting('Yarım',{'capture_dir':tmp});s.status(broken,'incomplete')
   s.close()
   with patch('meeting_os.desktop.capture_state',wraps=capture_state) as probe:
    snap=dispatch({'action':'snapshot','meeting':open_one},db)
   self.assertEqual(probe.call_count,2)   # the selected meeting and the unfinished one; never the finished history
   by={m['id']:m for m in snap['meetings']}
   self.assertIsNone(by[done]['capture'])
   self.assertEqual(by[done]['display_status'],'complete');self.assertEqual(by[done]['recovery_state'],'complete')
   self.assertIsNotNone(by[open_one]['capture']);self.assertIsNotNone(by[broken]['capture'])
   self.assertEqual(by[broken]['display_status'],'not_started')
   self.assertEqual(sorted(by),sorted([done,open_one,broken]))
 def test_snapshot_strips_heavy_metadata_from_unselected_meetings_and_honours_limit(self):
  heavy={'capture_dir':'/tmp/x','engine':'openrouter','model':'deepgram/nova-3','cloud_mode':'capture','keep':True,'text_only':False,'provisional':True,
         'calendar':{'title':'Sprint'},'glossary_suggestions':[{'original':'a','replacement':'b'}],'markers':[{'seconds':4}],
         'job_usage':{'seconds':900},'identity':{'embedded':3},'echo_segments':[1,2,3],'identity_error':'yok'}
  with tempfile.TemporaryDirectory() as tmp:
   db=Path(tmp)/'db';s=Store(db)
   ids=[s.create_meeting('T%02d'%i,dict(heavy)) for i in range(5)]
   for mid in ids: s.status(mid,'complete')
   s.close()
   selected=ids[0]
   meetings={m['id']:m for m in dispatch({'action':'snapshot','meeting':selected},db)['meetings']}
   for key in ('glossary_suggestions','markers','job_usage','identity','echo_segments'):
    self.assertIn(key,meetings[selected]['metadata'])
    self.assertNotIn(key,meetings[ids[1]]['metadata'])
   for key in ('calendar','keep','engine','model','cloud_mode','text_only','capture_dir','provisional','identity_error'):
    self.assertIn(key,meetings[ids[1]]['metadata'])
   limited=dispatch({'action':'snapshot','limit':2},db)['meetings']
   self.assertEqual(len(limited),2);self.assertEqual([m['id'] for m in limited],ids[::-1][:2])   # newest first
   with_selected=dispatch({'action':'snapshot','meeting':ids[0],'limit':2},db)['meetings']
   self.assertEqual([m['id'] for m in with_selected],ids[::-1][:2]+[ids[0]])   # the open meeting is never dropped
   self.assertEqual(len(dispatch({'action':'snapshot','limit':0},db)['meetings']),5)   # junk limit falls back to the default
 def test_diagnostics_uses_destination_volume_and_missing_progress_is_safe(self):
  from unittest.mock import patch
  from meeting_os.diagnostics import collect
  with tempfile.TemporaryDirectory() as t:
   root=Path(t);output=root/'report.json';missing=root/'gone-progress.json'
   with patch('meeting_os.diagnostics.collect',wraps=collect) as collector:
    dispatch({'action':'diagnostics','path':str(output),'progress':str(missing)})
    collector.assert_called_once_with(root,str(missing))
   self.assertEqual(json.loads(output.read_text())['progress']['stage'],'unknown')


class CloudRetryQueueTests(unittest.TestCase):
    """T7: which meetings an idle Mac may re-send, and which audio may never be deleted."""

    def _rec(self,store,data,name,metadata,status='incomplete'):
        d=data/'recordings'/name;d.mkdir(parents=True)
        (d/'system-full.wav').write_bytes(b'x'*1000)
        mid=store.create_meeting(name,{'capture_dir':str(d),'paths':{'system':str(d/'system-full.wav')},'cloud_mode':'capture','engine':'openrouter',**metadata})
        with store.db: store.db.execute('UPDATE meetings SET status=? WHERE id=?',(status,mid))
        return mid,d

    def test_selection_honours_kind_backoff_audio_and_the_attempt_cap(self):
        from datetime import datetime,timedelta,timezone
        from meeting_os.cloud_finalize import MAX_CLOUD_RETRIES
        from meeting_os.desktop import retry_candidates,cloud_error_line
        now=datetime.now(timezone.utc)
        def failure(kind,minutes,attempt=1):
            return {'cloud_error':{'kind':kind,'message':'m','at':now.isoformat()},'cloud_retry_attempt':attempt,
                    'cloud_retry_after':(now+timedelta(minutes=minutes)).isoformat()}
        with tempfile.TemporaryDirectory() as tmp:
            data=Path(tmp);store=Store(data/'meeting-os.sqlite')
            due,_=self._rec(store,data,'due',failure('unavailable',-1))
            waiting,_=self._rec(store,data,'bekleyen',failure('unavailable',30))
            auth,_=self._rec(store,data,'anahtar',failure('auth',-1))
            credit,_=self._rec(store,data,'kredi',failure('credit',-1))
            never,_=self._rec(store,data,'hic',{})                       # a job that never reported anything
            capped,_=self._rec(store,data,'dolu',failure('other',-1,attempt=MAX_CLOUD_RETRIES))
            done,_=self._rec(store,data,'biten',{},status='complete')
            local,_=self._rec(store,data,'yerel',{'cloud_mode':None,'engine':'sherpa'})
            gone,folder=self._rec(store,data,'sessiz',failure('unavailable',-1))
            for f in folder.iterdir(): f.unlink()                        # audio is gone: nothing left to send
            result=retry_candidates(store)
            self.assertEqual({e['meeting'] for e in result['candidates']},{due,never})
            self.assertEqual({e['meeting'] for e in result['blocked']},{auth,credit})
            self.assertNotIn(waiting,{e['meeting'] for e in result['candidates']})   # backoff has not passed
            for excluded in (capped,done,local,gone):
                self.assertNotIn(excluded,{e['meeting'] for e in result['candidates']})
            self.assertEqual({e['kind'] for e in result['blocked']},{'auth','credit'})
            store.close()

    def test_a_job_the_user_stopped_is_not_restarted_ten_minutes_later(self):
        """A cancel (⌘. or quit) raises KeyboardInterrupt: status `incomplete`, no `cloud_error`. That read as
        "never reported anything", so the idle queue restarted the upload the user had just refused."""
        from meeting_os.cloud_finalize import note_cloud_cancel
        from meeting_os.desktop import retry_candidates
        with tempfile.TemporaryDirectory() as tmp:
            data=Path(tmp);store=Store(data/'meeting-os.sqlite')
            stopped,_=self._rec(store,data,'durduruldu',{})
            other,_=self._rec(store,data,'devam',{})
            self.assertEqual({e['meeting'] for e in retry_candidates(store)['candidates']},{stopped,other})
            note_cloud_cancel(store,stopped)
            self.assertEqual({e['meeting'] for e in retry_candidates(store)['candidates']},{other})
            self.assertIsNone(json.loads(store.db.execute('SELECT metadata FROM meetings WHERE id=?',(stopped,)).fetchone()[0]).get('cloud_error'))
            # Starting a finalize by hand is the user asking again: the mark goes and the queue may help once more.
            meta=json.loads(store.db.execute('SELECT metadata FROM meetings WHERE id=?',(stopped,)).fetchone()[0]);meta.pop('cloud_canceled')
            with store.db: store.db.execute('UPDATE meetings SET metadata=? WHERE id=?',(json.dumps(meta),stopped))
            self.assertEqual({e['meeting'] for e in retry_candidates(store)['candidates']},{stopped,other})
            store.close()

    def test_a_cloud_recording_quit_before_finalize_is_still_found(self):
        """Quitting mid-job leaves a provisional recording that never reached finalize, so it has no
        `cloud_mode` yet. The `--cloud` marker written at record time is what the queue recognises."""
        from meeting_os.desktop import retry_candidates
        with tempfile.TemporaryDirectory() as tmp:
            data=Path(tmp);store=Store(data/'meeting-os.sqlite')
            never,_=self._rec(store,data,'hic-baslamadi',{'cloud_mode':None,'engine':None,'cloud_intent':'capture'},status='provisional')
            local,_=self._rec(store,data,'yerel',{'cloud_mode':None,'engine':'sherpa'},status='provisional')
            found={e['meeting'] for e in retry_candidates(store)['candidates']}
            self.assertIn(never,found)
            self.assertNotIn(local,found)   # a local-mode recording is never sent to the cloud behind the user's back
            store.close()

    def test_snapshot_shows_one_honest_line_per_meeting(self):
        from datetime import datetime,timedelta,timezone
        from meeting_os.desktop import cloud_error_line
        now=datetime.now(timezone.utc)
        self.assertIsNone(cloud_error_line({}))
        self.assertEqual(cloud_error_line({'cloud_error':{'kind':'auth'}}),'Anahtar geçersiz · Ayarlar → Sistem → OpenRouter anahtarı')
        self.assertEqual(cloud_error_line({'cloud_error':{'kind':'credit'}}),'Kredi bitti')
        at=now+timedelta(minutes=45)
        line=cloud_error_line({'cloud_error':{'kind':'unavailable'},'cloud_retry_after':at.isoformat()})
        self.assertEqual(line,'Yeniden denenecek · '+at.astimezone().strftime('%H:%M'))
        self.assertEqual(cloud_error_line({'cloud_error':{'kind':'unavailable'}}),'Yeniden denenecek')
        with tempfile.TemporaryDirectory() as tmp:
            data=Path(tmp);db=data/'meeting-os.sqlite';store=Store(db)
            mid,_=self._rec(store,data,'kritik',{'cloud_error':{'kind':'credit','message':'OpenRouter kredisi bitti','at':now.isoformat()}})
            store.close()
            row=[m for m in dispatch({'action':'snapshot'},db)['meetings'] if m['id']==mid][0]
            self.assertEqual(row['cloud_line'],'Kredi bitti')

    def test_audio_of_an_unfinished_or_waiting_meeting_survives_every_retention_setting(self):
        from datetime import datetime,timedelta,timezone
        with tempfile.TemporaryDirectory() as tmp:
            data=Path(tmp);db=data/'meeting-os.sqlite';store=Store(db)
            old=(datetime.now(timezone.utc)-timedelta(days=400)).isoformat()
            half,dhalf=self._rec(store,data,'yarim',{})                                      # incomplete
            failed,dfailed=self._rec(store,data,'basarisiz',{},status='failed')
            waiting,dwaiting=self._rec(store,data,'bekleyen',
                {'cloud_error':{'kind':'unavailable','message':'m','at':old}},status='complete')   # transcript done, retry pending
            plain,dplain=self._rec(store,data,'biten',{},status='complete')
            with store.db: store.db.execute('UPDATE meetings SET created=?',(old,))
            store.close()
            result=dispatch({'action':'storage_cleanup','days':1,'dry_run':False},db)
            self.assertEqual([m['meeting'] for m in result['meetings']],[plain])
            self.assertFalse(dplain.exists())
            for folder in (dhalf,dfailed,dwaiting):
                self.assertTrue((folder/'system-full.wav').is_file(),folder)
            # The retention housekeeping the app runs hourly reaches the same conclusion.
            from meeting_os.reports import save_settings
            save_settings(data,{'audio_retention_days':1})
            dispatch({'action':'storage_housekeeping'},db)
            for folder in (dhalf,dfailed,dwaiting):
                self.assertTrue((folder/'system-full.wav').is_file(),folder)

    def test_auto_retry_setting_defaults_on_and_round_trips(self):
        from meeting_os.reports import load_settings,save_settings
        with tempfile.TemporaryDirectory() as tmp:
            self.assertTrue(load_settings(Path(tmp))['auto_retry'])
            self.assertFalse(save_settings(Path(tmp),{'auto_retry':False})['auto_retry'])
            self.assertFalse(load_settings(Path(tmp))['auto_retry'])
            self.assertFalse(save_settings(Path(tmp),{'auto_retry':'evet'})['auto_retry'])   # only a real bool is accepted

    def test_low_priority_env_keeps_the_idle_queue_silent(self):
        import os
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as tmp:
            data=Path(tmp);db=data/'meeting-os.sqlite';store=Store(data/'meeting-os.sqlite')
            self._rec(store,data,'kritik',{});store.close()
            self.assertEqual(len(dispatch({'action':'retry_candidates'},db)['candidates']),1)
            with patch.dict(os.environ,{'MEETING_OS_LOW_PRIORITY':'1'}):
                self.assertEqual(dispatch({'action':'retry_candidates'},db),{'candidates':[],'blocked':[],'low_priority':True})

class CommandLineFallbackTests(unittest.TestCase):
    """The app hands user-typed values over the environment instead of argv: a question can start with '-' or
    hold a newline, and on macOS every process can read another process's command line."""
    def _parse(self,env,argv):
        import os
        from unittest.mock import patch
        from meeting_os.cli import parser
        with patch.dict(os.environ,env,clear=False): return parser().parse_args(argv)   # the default is read per call
    def test_the_question_comes_from_the_environment_when_argv_has_none(self):
        self.assertEqual(self._parse({'MEETING_OS_QUESTION':'Karar ne oldu?'},['ask']).question,'Karar ne oldu?')
        self.assertEqual(self._parse({'MEETING_OS_QUESTION':'Karar ne oldu?'},['ask','Baska soru']).question,'Baska soru')   # argv still wins
        self.assertIsNone(self._parse({},['ask']).question)
    def test_the_import_audio_path_comes_from_the_environment_and_stays_a_path(self):
        self.assertEqual(self._parse({'MEETING_OS_AUDIO_PATH':'/tmp/kayit.wav'},['openrouter-import']).audio,Path('/tmp/kayit.wav'))
        self.assertIsNone(self._parse({},['openrouter-import']).audio)
