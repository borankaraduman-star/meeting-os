import unittest,tempfile,json
from pathlib import Path
from meeting_os.store import Store
from meeting_os.types import Segment
from meeting_os.intelligence import validate_record, fingerprint, merge_records
from meeting_os.memory import Memory

ROWS=[{'id':1,'start':0.,'end':8.,'source':'mic','speaker':'mic:S0','speaker_name':'Boran','text':'Ben PRD taslağını yarın hazırlayacağım.','flags':[]}]
def record():
 return {'summary':[{'text':'PRD taslağı hazırlanacak.','evidence':[{'segment_id':1,'quote':'PRD taslağını yarın hazırlayacağım'}]}],'decisions':[],'risks':[],'questions':[],'actions':[{'title':'PRD taslağını hazırla','owner':'Boran','due_text':'yarın','evidence':[{'segment_id':1,'quote':'Ben PRD taslağını yarın hazırlayacağım.'}]}]}
class IntelligenceTests(unittest.TestCase):
 def test_bad_evidence_is_rejected(self):
  d=record();d['actions'][0]['evidence'][0]['segment_id']=99
  with self.assertRaises(ValueError): validate_record(d,ROWS)
 def test_unknown_owner_and_invented_deadline_abstain(self):
  d=record();d['actions'][0]['owner']='Can';d['actions'][0]['due_text']='2026-09-20'
  r=validate_record(d,ROWS);self.assertIsNone(r['actions'][0]['owner']);self.assertIsNone(r['actions'][0]['due_text']);self.assertTrue(r['actions'][0]['needs_review'])
 def test_uncertain_source_requires_review(self):
  r=validate_record(record(),[{**ROWS[0],'flags':['speaker_ambiguous']}]);self.assertTrue(r['actions'][0]['needs_review'])
 def test_status_and_manual_edits_survive_repeat_and_source_changes_stale(self):
  with tempfile.TemporaryDirectory() as tmp:
   s=Store(Path(tmp)/'db');mid=s.create_meeting('Sprint');sid=s.add_segment(mid,Segment(0,8,ROWS[0]['text'],'mic','mic:S0','Boran'));s.status(mid,'complete');mem=Memory(s)
   rows=s.display_segments(mid);d=record()
   for key in ('summary','actions'):
    for item in d[key]:item['evidence'][0]['segment_id']=sid
   good=validate_record(d,rows);mem.save_analysis(mid,fingerprint(rows),'test',good)
   action=mem.actions()[0];mem.update_action(action['id'],{'state':'done','title':'Düzeltilmiş PRD'})
   mem.save_analysis(mid,fingerprint(rows),'test',good)
   after=mem.actions()[0];self.assertEqual(after['state'],'done');self.assertEqual(after['title'],'Düzeltilmiş PRD');self.assertFalse(after['stale'])
   s.correct_text(mid,sid,'PRD iptal edildi.');self.assertTrue(mem.actions()[0]['stale']);s.close()
 def test_named_implicit_first_person_future_is_owned(self):
  rows=[{**ROWS[0],'text':'Raporu cuma günü yazacağım.'}];d=record();d['summary']=[];d['actions']=[{'title':'Raporu yaz','owner':'Boran','due_text':'cuma günü','evidence':[{'segment_id':1,'quote':rows[0]['text']}]}]
  self.assertEqual(validate_record(d,rows)['actions'][0]['owner'],'Boran')
