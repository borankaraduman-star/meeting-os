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
