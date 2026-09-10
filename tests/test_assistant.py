import io,json,tempfile,unittest
from pathlib import Path
from meeting_os.store import Store
from meeting_os.types import Segment
from meeting_os.intelligence import fingerprint,validate_record
from meeting_os.memory import Memory
from meeting_os import assistant,mcp
from meeting_os.desktop import dispatch
class FakeLLM:
 model_id='fixture'
 def __init__(self,text=json.dumps({'sections':[{'heading':'Amaç','content':'PRD kapsamı kaynakta verilmemiş.'}],'open_questions':['Kapsam nedir?']})):self.text=text;self.calls=0
 def complete(self,*args,**kwargs):self.calls+=1;return self.text
class AssistantTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name)/'db';self.s=Store(self.path);self.mid=self.s.create_meeting('Plan');self.sid=self.s.add_segment(self.mid,Segment(0,8,'Ben PRD taslağını yarın hazırlayacağım.','mic','S0','Boran'));self.s.status(self.mid,'complete');self.mem=Memory(self.s)
  self.record=validate_record({'actions':[{'title':'PRD taslağını hazırla','owner':'Boran','due_text':'yarın','evidence':[{'segment_id':self.sid,'quote':'Ben PRD taslağını yarın hazırlayacağım.'}]}]},self.s.display_segments(self.mid));self.mem.save_analysis(self.mid,self.mem.current_hash(self.mid),'fixture',self.record);self.task=self.mem.actions()[0]
 def tearDown(self):self.s.close();self.tmp.cleanup()
 def test_removed_action_in_new_version_is_stale_even_if_source_same(self):
  self.mem.save_analysis(self.mid,self.mem.current_hash(self.mid),'fixture',{k:[] for k in self.record})
  self.assertTrue(self.mem.task(self.task['id'])['stale'])
 def test_cached_analysis_avoids_model_call(self):
  llm=FakeLLM();r=assistant.analyze(self.s,self.mid,llm);self.assertEqual(llm.calls,0);self.assertFalse(r['stale'])
 def test_draft_becomes_stale_after_manual_edit(self):
  d=assistant.prepare(self.s,self.task['id'],FakeLLM());self.assertFalse(d['stale']);self.mem.update_action(self.task['id'],{'owner':'Ece'});self.assertTrue(assistant.draft(self.s,d['id'])['stale'])
 def test_source_edit_blocks_draft_and_handoff(self):
  self.s.correct_text(self.mid,self.sid,'PRD iptal edildi.')
  with self.assertRaises(ValueError):assistant.prepare(self.s,self.task['id'],FakeLLM())
  with self.assertRaises(ValueError):assistant.handoff(self.s,self.task['id'],Path(self.tmp.name)/'out.md')
 def test_handoff_has_only_selected_context_and_no_sending(self):
  result=assistant.handoff(self.s,self.task['id'],Path(self.tmp.name)/'out.md');self.assertFalse(result['sent']);self.assertIn('PRD',Path(result['path']).read_text())
 def test_task_state_audit_and_desktop_bridge(self):
  dispatch({'action':'action_update','task':self.task['id'],'changes':{'state':'done'}},self.path)
  self.assertEqual(self.mem.task(self.task['id'])['state'],'done');self.assertEqual(self.s.db.execute('SELECT count(*) FROM task_edits').fetchone()[0],1)
  self.assertEqual(len(dispatch({'action':'intelligence','meeting':self.mid},self.path)['tasks']),1)
 def test_empty_search_abstains_without_loading_model(self):
  llm=FakeLLM();r=assistant.ask(self.s,'buzullar',llm);self.assertTrue(r['abstained']);self.assertEqual(llm.calls,0)
 def test_qa_rejects_fabricated_quotes(self):
  llm=FakeLLM(json.dumps({'summary':[{'text':'Wrong','evidence':[{'segment_id':self.sid,'quote':'Invented'}]}]}))
  with self.assertRaises(ValueError):assistant.ask(self.s,'PRD',llm)
 def test_mcp_protocol_read_only_and_malformed_input(self):
  messages=[{'jsonrpc':'2.0','id':1,'method':'initialize','params':{}},{'jsonrpc':'2.0','method':'notifications/initialized'},{'jsonrpc':'2.0','id':2,'method':'tools/list'},{'jsonrpc':'2.0','id':3,'method':'tools/call','params':{'name':'action_update','arguments':{}}}]
  sink=io.StringIO();mcp.serve(self.s,io.StringIO('\n'.join(json.dumps(m) for m in messages)+'\nINVALID\n'),sink);rows=[json.loads(x) for x in sink.getvalue().splitlines()]
  self.assertEqual(len(rows),4);self.assertTrue(all(t['annotations']['readOnlyHint'] for t in rows[1]['result']['tools']));self.assertTrue(rows[2]['result']['isError']);self.assertEqual(rows[3]['error']['code'],-32700)
 def test_mcp_does_not_expose_audio_paths_or_embeddings(self):
  r=mcp.call(self.s,'get_meeting',{'meeting':self.mid});self.assertNotIn('embedding',json.dumps(r));self.assertNotIn('paths',json.dumps(mcp.call(self.s,'list_meetings',{})))
 def test_analysis_write_detects_changed_source_atomically(self):
  digest=self.mem.current_hash(self.mid);self.s.correct_text(self.mid,self.sid,'İptal edildi.')
  with self.assertRaises(ValueError):self.mem.save_analysis(self.mid,digest,'fixture',self.record)
  self.assertEqual(self.s.db.execute('SELECT count(*) FROM analyses').fetchone()[0],1)
 def test_draft_edit_is_audited(self):
  d=assistant.prepare(self.s,self.task['id'],FakeLLM());assistant.edit_draft(self.s,d['id'],'Elle düzenlenen taslak')
  self.assertEqual(assistant.draft(self.s,d['id'])['text'],'Elle düzenlenen taslak');self.assertEqual(self.s.db.execute('SELECT count(*) FROM draft_edits').fetchone()[0],1)
 def test_summary_export_contains_tasks_and_sources(self):
  path=Path(self.tmp.name)/'summary.md';dispatch({'action':'export_analysis','meeting':self.mid,'path':str(path)},self.path);self.assertIn('PRD',path.read_text());self.assertIn('Görevler',path.read_text())
 def test_draft_cache_and_progress_do_not_waste_model_calls(self):
  llm=FakeLLM();d=assistant.prepare(self.s,self.task['id'],llm);self.mem.update_action(self.task['id'],{'state':'in_progress'});d2=assistant.prepare(self.s,self.task['id'],llm);self.assertEqual(d['id'],d2['id']);self.assertEqual(llm.calls,1)
 def test_fabricated_draft_date_is_rejected(self):
  llm=FakeLLM(json.dumps({'sections':[{'heading':'Tarih','content':'2025-04-05 tarihinde teslim edilecek.'}],'open_questions':[]}))
  with self.assertRaises(ValueError):assistant.prepare(self.s,self.task['id'],llm)
  self.assertEqual(self.s.db.execute('SELECT count(*) FROM drafts').fetchone()[0],0)
 def test_completed_task_cannot_be_handed_off(self):
  self.mem.update_action(self.task['id'],{'state':'done'})
  with self.assertRaises(ValueError):assistant.handoff(self.s,self.task['id'],Path(self.tmp.name)/'task.md')
 def test_prepare_rechecks_competing_draft_inside_transaction(self):
  outer=FakeLLM();inner=FakeLLM();original=outer.complete
  def competing(*a,**k):assistant.prepare(self.s,self.task['id'],inner);return original(*a,**k)
  outer.complete=competing
  assistant.prepare(self.s,self.task['id'],outer)
  self.assertEqual(self.s.db.execute('SELECT count(*) FROM drafts').fetchone()[0],1)
 def test_truncated_draft_retries_without_partial_save(self):
  llm=FakeLLM();original=llm.complete
  def truncated(*a,**k):
   if llm.calls==0:llm.calls+=1;return '{"sections":[{"content":"unfinished'
   return original(*a,**k)
  llm.complete=truncated
  result=assistant.prepare(self.s,self.task['id'],llm);self.assertTrue(result['text']);self.assertEqual(llm.calls,2)

 def test_bounded_draft_does_not_publish_cut_off_clause(self):
  self.assertEqual(assistant.complete_bounded_text('Tam cümle. Kesilm',16),'Tam cümle.')


class TurkishSearchTests(unittest.TestCase):
    def test_suffixed_forms_match_and_stopwords_are_ignored(self):
        from meeting_os.memory import query_terms,match_score
        self.assertEqual(query_terms('Eğitim modülleri kaç günde tamamlanıyor ve kim söyledi?'),['eğitim','modülleri','günde','tamamlanıyor'])
        self.assertEqual(query_terms('ne kaç mi'),['ne','kaç','mi'])   # nothing but function words: keep them rather than return nothing
        self.assertGreater(match_score(['modülleri','günde'],'1. modülü ve 3. modülü toplam 3 günde alıyoruz'),1.5)
        self.assertEqual(match_score(['modülleri'],'Bugün hava güzel'),0.0)
        self.assertEqual(match_score(['gün'],'bugün toplantı var'),1.0)   # substring behaviour kept for short words
    def test_search_ranks_suffixed_segment_above_single_word_hits(self):
        with tempfile.TemporaryDirectory() as tmp:
            db=Path(tmp)/'m.sqlite';s=Store(db);mid=s.create_meeting('Eğitim',{})
            for i in range(15):s.add_segment(mid,Segment(i,i+1,'İsviçre güzel bir ülke.','system','K1'))
            target=s.add_segment(mid,Segment(20,21,'1., 2. ve 3. modülü toplam 3 günde alıyoruz.','system','K2'))
            s.status(mid,'complete')
            hits=Memory(s).search('Eğitim modülleri kaç günde tamamlanıyor',limit=12)
            self.assertEqual(hits[0]['id'],target);s.close()


class SearchRankingTests(unittest.TestCase):
    """Two segments with the same score are not equally useful, and the speaker filter has to mean a person."""
    def test_more_of_the_asked_words_and_the_shorter_segment_win_a_tie(self):
        with tempfile.TemporaryDirectory() as tmp:
            db=Path(tmp)/'m.sqlite';s=Store(db);mid=s.create_meeting('Eğitim',{})
            one=s.add_segment(mid,Segment(0,1,'modül eğitim','system','K1'))
            s.add_segment(mid,Segment(1,2,'modül modül ve başka bir sürü kelime daha burada duruyor','system','K1'))
            s.status(mid,'complete')
            hits=Memory(s).search('modül eğitim')
            self.assertEqual(hits[0]['id'],one);self.assertEqual(hits[0]['hits'],2);s.close()
    def test_the_speaker_filter_folds_spellings_and_knows_the_microphone_owner(self):
        with tempfile.TemporaryDirectory() as tmp:
            db=Path(tmp)/'m.sqlite';s=Store(db);mid=s.create_meeting('Eğitim',{})
            mine=s.add_segment(mid,Segment(0,1,'raporu ben yazacağım','mic','Boran',flags=['cloud_transcript']))
            s.add_segment(mid,Segment(1,2,'raporu İlker yazsın','system','S1',speaker_name='İlker'))
            s.status(mid,'complete');mem=Memory(s)
            self.assertEqual([h['id'] for h in mem.search('rapor',speaker='boran')],[mine])   # the mic label is a person
            self.assertEqual(len(mem.search('rapor',speaker='Ilker')),1)                      # İ/I is not a different person
            self.assertEqual(mem.search('rapor',speaker='Kimse'),[]);s.close()
