import json,tempfile,unittest
from pathlib import Path
from meeting_os.desktop import dispatch,export_text
from meeting_os.store import Store
class Tests(unittest.TestCase):
 def test_preview_does_not_write_and_preserves_unknown_times(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'db';r=dispatch({'action':'transcript_preview','text':'Merhaba\n\nİkinci paragraf'},p)
   self.assertIsNone(r['rows'][0]['start']);self.assertIsNone(r['rows'][0]['end']);self.assertIsNone(r['rows'][0]['speaker_name'])
   db=Store(p);self.assertEqual(db.meetings(),[]);db.close()
 def test_roundtrip_order_edit_raw_source_and_profile_rejection(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'db';raw='[00:12] Boran: İlk bölüm\n\nZamansız son bölüm'
   mid=dispatch({'action':'transcript_import','title':'Aktarılan','text':raw},p)['meeting']
   rows=dispatch({'action':'snapshot','meeting':mid},p)['segments'];self.assertEqual([r['text'] for r in rows],['İlk bölüm','Zamansız son bölüm']);self.assertEqual(rows[0]['start'],12);self.assertIsNone(rows[0]['end'])
   dispatch({'action':'edit_text','meeting':mid,'segment':rows[0]['id'],'text':'Düzeltildi'},p)
   dispatch({'action':'label','meeting':mid,'segment':rows[0]['id'],'name':'Boran'},p)
   with self.assertRaises(ValueError):dispatch({'action':'enroll','meeting':mid,'segment':rows[0]['id'],'name':'Boran','confirmed_clean':True},p)
   db=Store(p);self.assertEqual(json.loads(db.meetings()[0]['metadata'])['raw_source_text'],raw);self.assertEqual(db.profiles(),[]);self.assertEqual(db.segments(mid)[0]['text'],'Düzeltildi');db.close()
 def test_reject_bad_inputs_without_meetings(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'db'
   for text in ('  ','bad\x00data','a'*1048577,'[00:99] Boran: bad'):
    with self.subTest(text=text[:12]),self.assertRaises(ValueError):dispatch({'action':'transcript_import','title':'Test','text':text},p)
   db=Store(p);self.assertEqual(db.meetings(),[]);db.close()
 def test_existing_meeting_is_not_overwritten(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'db';db=Store(p);old=db.create_meeting('Existing');db.close()
   new=dispatch({'action':'transcript_import','meeting':old,'title':'New','text':'Metin'},p)['meeting'];self.assertNotEqual(old,new)
   db=Store(p);self.assertEqual(len(db.meetings()),2);self.assertEqual(db.segments(old),[]);db.close()
 def test_export_missing_times_has_no_fabricated_timestamp(self):
  rows=[{'start':None,'end':None,'speaker_name':None,'speaker':'unknown','text':'Merhaba'}]
  self.assertNotIn('00:00',export_text(rows,'md'))
  with self.assertRaises(ValueError):export_text(rows,'srt')
