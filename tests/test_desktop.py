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

 def test_diagnostics_uses_destination_volume_and_missing_progress_is_safe(self):
  from unittest.mock import patch
  from meeting_os.diagnostics import collect
  with tempfile.TemporaryDirectory() as t:
   root=Path(t);output=root/'report.json';missing=root/'gone-progress.json'
   with patch('meeting_os.diagnostics.collect',wraps=collect) as collector:
    dispatch({'action':'diagnostics','path':str(output),'progress':str(missing)})
    collector.assert_called_once_with(root,str(missing))
   self.assertEqual(json.loads(output.read_text())['progress']['stage'],'unknown')
