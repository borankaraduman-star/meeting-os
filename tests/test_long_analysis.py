import json,unittest
from meeting_os.intelligence import compact_summary,reconcile_actions,chunks,validate_record
class Model:
 def count(self,text):return len(text)
 def complete(self,system,user,**kwargs):
  if 'retain' in kwargs['schema']['properties']:return json.dumps({'retain':False,'evidence_segment_id':2})
  notes=json.loads(user)['notes'];return json.dumps({'summary':[notes[0]]})
class LongAnalysisTests(unittest.TestCase):
 def test_later_cancellation_removes_existing_task(self):
  rows=[{'id':1,'start':0,'source':'system','speaker':'S0','text':'Ben migration planını yazacağım.','flags':[]},{'id':2,'start':40,'source':'system','speaker':'S1','text':'Migration planını iptal ettik.','flags':[]}]
  a={'title':'Migration planını yaz','evidence':[{'segment_id':1,'quote':rows[0]['text'],'start':0}]}
  self.assertEqual(reconcile_actions([a],rows,Model()),[])
 def test_summary_reduction_keeps_original_quotes(self):
  rows=[{'id':i,'start':i,'source':'system','speaker':'S0','text':f'Madde {i}.','flags':[]} for i in range(12)]
  items=validate_record({'summary':[{'text':r['text'],'evidence':[{'segment_id':r['id'],'quote':r['text']}]} for r in rows]},rows)['summary']
  result=compact_summary(items,rows,Model());self.assertLessEqual(len(result),5);self.assertTrue(all(i['evidence'] for i in result))
 def test_long_segment_splitting_preserves_entire_text(self):
  text='abcd '*2000;rows=[{'id':1,'text':text,'speaker_name':None}];batches=list(chunks(rows,Model(),budget=2500));self.assertEqual(''.join(r['text'] for b in batches for r in b),text)
 def test_short_title_retraction_is_not_skipped(self):
  rows=[{'id':1,'start':0,'text':'PRD yazacağım.'},{'id':2,'start':60,'text':'PRD iptal edildi.'}]
  a={'title':'PRD yaz','evidence':[{'segment_id':1,'quote':'PRD yazacağım.','start':0}]}
  self.assertEqual(reconcile_actions([a],rows,Model()),[])
