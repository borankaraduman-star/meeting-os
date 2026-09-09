import json,subprocess,sys,tempfile,unittest
from datetime import datetime,timedelta,timezone
from pathlib import Path
from meeting_os.decisions import decision_log,export_decision_log,render_decision_log
from meeting_os.desktop import dispatch
from meeting_os.digest import build_digest,parse_range,render_digest
from meeting_os.memory import Memory
from meeting_os.review import review_debt
from meeting_os.store import Store
from meeting_os.types import Segment
from meeting_os.waiting import age_days,build_waiting,render_waiting

def analysis(sid,decision,*,risks=(),questions=(),actions=()):
 return {'summary':[{'text':'Konuşuldu','evidence':[{'segment_id':sid,'quote':'konuşuldu','start':0,'speaker':'Boran'}]}],
         'decisions':[{'text':decision,'evidence':[{'segment_id':sid,'quote':decision,'start':0,'speaker':'İpek'}]}],
         'risks':[{'text':r,'evidence':[{'segment_id':sid,'quote':r[:20],'start':0,'speaker':'İpek'}]} for r in risks],
         'questions':[{'text':q,'evidence':[{'segment_id':sid,'quote':q[:20],'start':0,'speaker':'İpek'}]} for q in questions],
         'actions':[{'title':t,'owner':o,'due_text':d,'evidence':[{'segment_id':sid,'quote':f'{t} sözü','start':0,'speaker':'Boran'}]} for t,o,d in actions]}

def seed(db,title,created,decision,**kw):
 s=Store(db);mid=s.create_meeting(title,{})
 with s.db:s.db.execute('UPDATE meetings SET created=? WHERE id=?',(created,mid))
 sid=s.add_segment(mid,Segment(0,60,'Boran raporu çıkaracak, İpek tasarımı bitirecek.','system','S0',speaker_name='Boran'))
 s.add_segment(mid,Segment(60,120,'Tamam, bekliyoruz.','system','S1',speaker_name='İpek'))
 s.status(mid,'complete');mem=Memory(s);mem.save_analysis(mid,mem.current_hash(mid),'test-model',analysis(sid,decision,**kw));s.close()
 return mid,sid

def week(db):
 """Two meetings: an older one whose decision the newer one repeats, tasks for Boran and for other people."""
 now=datetime.now(timezone.utc);old=now-timedelta(days=2)
 a,sa=seed(db,'Sprint planı',old.isoformat(),'Önce iOS çıkacak',risks=('Takvim dar',),questions=('Rapor ne zaman?',),
           actions=(('Raporu çıkarmak','Boran','yarın'),('Tasarımı bitirmek','İpek',None),('Sözleşmeyi imzalamak',None,None)))
 b,sb=seed(db,'Haftalık durum',now.isoformat(),'Önce iOS çıkacak, Android sonra',risks=(),questions=(),
           actions=(('Tasarımı bitirmek','İpek','cuma'),('Sunucuyu kurmak','Mehmet Can',None),('Notları toplamak','boran',None)))
 return a,sa,b,sb,old,now

class DigestRangeTests(unittest.TestCase):
 def test_parse_range_defaults_to_one_day_and_rejects_a_backwards_period(self):
  today=datetime.now(timezone.utc).astimezone().date()
  self.assertEqual(parse_range(),(today,today))
  self.assertEqual(parse_range(None,'2026-09-01','2026-09-07'),(__import__('datetime').date(2026,9,1),__import__('datetime').date(2026,9,7)))
  self.assertEqual(parse_range(None,'2026-09-01',None),parse_range(None,None,'2026-09-01'))
  with self.assertRaises(ValueError):parse_range(None,'2026-09-07','2026-09-01')
  with self.assertRaises(ValueError):parse_range(None,'dün',None)
 def test_range_digest_groups_by_meeting_newest_first_with_open_and_closed_tasks(self):
  with tempfile.TemporaryDirectory() as tmp:
   db=Path(tmp)/'db';a,sa,b,sb,old,now=week(db)
   s=Store(db);mem=Memory(s)
   done=[t for t in mem.actions() if t['meeting']==a and t['title']=='Raporu çıkarmak'][0]
   mem.update_action(done['id'],{'state':'done'});s.close()
   first=old.astimezone().date().isoformat();last=now.astimezone().date().isoformat()
   d=build_digest(Store(db),start=first,end=last)
   self.assertEqual((d['from'],d['to'],d['range']),(first,last,first!=last))
   self.assertEqual([g['meeting'] for g in d['groups']],[b,a])
   self.assertEqual([x['text'] for x in d['risks']],['Takvim dar'])
   self.assertEqual([x['text'] for x in d['decisions']],['Önce iOS çıkacak','Önce iOS çıkacak, Android sonra'])
   older=d['groups'][1]
   self.assertEqual([t['title'] for t in older['closed']],['Raporu çıkarmak'])
   self.assertEqual(sorted(t['title'] for t in older['open']),['Sözleşmeyi imzalamak','Tasarımı bitirmek'])
   self.assertEqual([t['title'] for t in d['groups'][0]['closed']],[])
   text=render_digest(d)
   for needle in (f'# Dönem özeti · {first} → {last}','## Toplantı toplantı','### Haftalık durum · ','**Riskler**','- Takvim dar','**Bu dönemde kapanan görevler**','- Raporu çıkarmak · Boran · yarın · tamamlandı','**Hâlâ açık görevler**','## Dönemdeki toplantılar'):
    self.assertIn(needle,text)
   self.assertNotIn('# Gün sonu özeti',text)
 def test_single_day_digest_keeps_the_old_shape_and_masking_hides_names(self):
  with tempfile.TemporaryDirectory() as tmp:
   db=Path(tmp)/'db';a,sa,b,sb,old,now=week(db)
   plain=render_digest(build_digest(Store(db)))
   self.assertIn('# Gün sonu özeti',plain);self.assertNotIn('## Toplantı toplantı',plain);self.assertIn('## Bugünkü toplantılar',plain)
   first=old.astimezone().date().isoformat();last=now.astimezone().date().isoformat()
   masked=build_digest(Store(db),start=first,end=last,mask_names=True)
   self.assertGreaterEqual(masked['masked_names'],2)
   text=render_digest(masked)
   self.assertIn('isimler maskelendi',text);self.assertIn('Kişi A',text)
   for name in ('Boran','İpek'): self.assertNotIn(name,text)
   self.assertIn('Önce iOS çıkacak',text)   # only names are masked
 def test_digest_bridge_and_cli_accept_a_period(self):
  with tempfile.TemporaryDirectory() as tmp:
   db=Path(tmp)/'db';a,sa,b,sb,old,now=week(db)
   first=old.astimezone().date().isoformat();last=now.astimezone().date().isoformat()
   out=Path(tmp)/'hafta.md'
   r=dispatch({'action':'digest','from':first,'to':last,'mask_names':True,'path':str(out)},db)
   self.assertEqual((r['from'],r['to'],r['meetings'],r['risks']),(first,last,2,1))
   self.assertEqual(len(r['groups']),2);self.assertGreaterEqual(r['masked_names'],2)
   self.assertIn('## Toplantı toplantı',out.read_text());self.assertNotIn('İpek',out.read_text())
   self.assertEqual(dispatch({'action':'digest'},db)['range'],False)
   cli=Path(tmp)/'cli.md'
   p=subprocess.run([sys.executable,'-m','meeting_os','--db',str(db),'digest','--from',first,'--to',last,'--output',str(cli)],capture_output=True,text=True)
   self.assertEqual(p.returncode,0,p.stderr);self.assertEqual(json.loads(p.stdout)['meetings'],2);self.assertIn('## Toplantı toplantı',cli.read_text())

class WaitingTests(unittest.TestCase):
 def test_board_keeps_other_people_only_and_marks_repeats(self):
  with tempfile.TemporaryDirectory() as tmp:
   db=Path(tmp)/'db';a,sa,b,sb,old,now=week(db)
   board=build_waiting(Store(db))
   self.assertEqual([g['owner'] for g in board['people']],['İpek','Mehmet Can'])
   self.assertEqual(board['total'],3)
   ipek=board['people'][0]
   self.assertEqual([i['meeting_title'] for i in ipek['items']],['Sprint planı','Haftalık durum'])   # oldest first
   self.assertTrue(all(i['repeat'] for i in ipek['items']));self.assertEqual(ipek['items'][0]['meetings'],2)
   self.assertEqual(ipek['items'][0]['age_days'],0)   # tasks are recorded when the analysis is saved, not when the meeting happened
   self.assertEqual(ipek['items'][0]['quote'],'Tasarımı bitirmek sözü')
   self.assertFalse(board['people'][1]['items'][0]['repeat'])
   for text in (ipek['reminder_text'],render_waiting(board)):
    self.assertIn('Tasarımı bitirmek',text)
   self.assertIn('Merhaba İpek',ipek['reminder_text']);self.assertIn('0 gündür açık',ipek['reminder_text']);self.assertIn('Teşekkürler',ipek['reminder_text'])
   titles=[i['title'] for g in board['people'] for i in g['items']]
   self.assertNotIn('Raporu çıkarmak',titles);self.assertNotIn('Notları toplamak',titles);self.assertNotIn('Sözleşmeyi imzalamak',titles)
   self.assertIsNone(age_days('yok'));self.assertEqual(build_waiting(Store(db),owner='İpek')['total'],3)
 def test_waiting_bridge_and_cli(self):
  with tempfile.TemporaryDirectory() as tmp:
   db=Path(tmp)/'db';week(db)
   r=dispatch({'action':'waiting_board'},db)
   self.assertEqual(r['total'],3);self.assertEqual(len(r['people']),2);self.assertIn('reminder_text',r['people'][0])
   out=Path(tmp)/'bekleyen.md';dispatch({'action':'waiting_board','path':str(out)},db)
   self.assertIn('# Beklediklerim',out.read_text());self.assertIn('Hatırlatma taslağı',out.read_text())
   p=subprocess.run([sys.executable,'-m','meeting_os','--db',str(db),'waiting'],capture_output=True,text=True)
   self.assertEqual(p.returncode,0,p.stderr);self.assertEqual(json.loads(p.stdout)['total'],3)

class DecisionLogTests(unittest.TestCase):
 def test_log_is_newest_first_with_previous_versions_and_a_text_filter(self):
  with tempfile.TemporaryDirectory() as tmp:
   db=Path(tmp)/'db';a,sa,b,sb,old,now=week(db)
   log=decision_log(Store(db))
   self.assertEqual([d['meeting'] for d in log['decisions']],[b,a]);self.assertEqual((log['total'],log['matched']),(2,2))
   newest=log['decisions'][0]
   self.assertEqual(newest['evidence'],{'segment_id':sb,'start':0,'quote':'Önce iOS çıkacak, Android sonra'})
   self.assertEqual([p['meeting'] for p in newest['previous']],[a]);self.assertGreaterEqual(newest['previous'][0]['similarity'],0.45)
   self.assertEqual(log['decisions'][1]['previous'],[])   # nothing earlier than the first meeting
   self.assertEqual(decision_log(Store(db),'ANDROİD')['matched'],1)
   self.assertEqual(decision_log(Store(db),'sprint')['matched'],1)   # meeting title matches too
   self.assertEqual(decision_log(Store(db),'blokzincir')['matched'],0)
   self.assertEqual(len(decision_log(Store(db),limit=1)['decisions']),1)
   text=render_decision_log(log)
   self.assertIn('# Karar günlüğü',text);self.assertIn('## Önce iOS çıkacak, Android sonra',text);self.assertIn('Önceki hâli: Önce iOS çıkacak',text);self.assertIn(f'Kaynak #{sb}',text)
 def test_export_masks_names_and_bridge_and_cli_agree(self):
  with tempfile.TemporaryDirectory() as tmp:
   db=Path(tmp)/'db';week(db)
   out=Path(tmp)/'kararlar.md'
   r=export_decision_log(Store(db),out,mask_names=True)
   self.assertEqual((r['decisions'],r['total']),(2,2));self.assertGreaterEqual(r['masked_names'],0)
   self.assertIn('Önce iOS çıkacak',out.read_text())
   bridge=dispatch({'action':'decision_log','query':'android'},db)
   self.assertEqual(bridge['matched'],1);self.assertEqual(bridge['total'],2)
   e=dispatch({'action':'decision_log_export','path':str(out),'mask_names':True},db)
   self.assertEqual(e['path'],str(out))
   p=subprocess.run([sys.executable,'-m','meeting_os','--db',str(db),'decisions','--query','android'],capture_output=True,text=True)
   self.assertEqual(p.returncode,0,p.stderr);self.assertEqual(json.loads(p.stdout)['matched'],1)

class ReviewDebtTests(unittest.TestCase):
 def build(self,db,title,created,status='complete'):
  s=Store(db);mid=s.create_meeting(title,{})
  with s.db:s.db.execute('UPDATE meetings SET created=? WHERE id=?',(created,mid))
  flags=['cloud_transcript','cloud_diarization']
  s.add_segment(mid,Segment(0,20,'isimsiz','system','Konuşmacı 2',metrics={'cluster':'0:1','identity':{'name':None,'candidate':'Ayşe','similarity':0.7,'suggested':None}},flags=flags))
  s.add_segment(mid,Segment(20,30,'çakışma','system','unknown',flags=flags+['speaker_ambiguous']))
  s.status(mid,status);s.close()
  return mid
 def test_debt_covers_only_recent_complete_meetings_and_sorts_by_severity(self):
  with tempfile.TemporaryDirectory() as tmp:
   db=Path(tmp)/'db';now=datetime.now(timezone.utc)
   recent=self.build(db,'Bu hafta',now.isoformat())
   newer=self.build(db,'Dün',(now-timedelta(days=1)).isoformat())
   self.build(db,'Geçen ay',(now-timedelta(days=40)).isoformat())
   self.build(db,'Yarım',(now-timedelta(hours=1)).isoformat(),status='processing')
   debt=review_debt(Store(db))
   self.assertEqual(debt['meetings'],2);self.assertEqual(debt['counts'],{'ambiguous':2,'unnamed_speaker':2})
   self.assertEqual([i['kind'] for i in debt['items']],['ambiguous','ambiguous','unnamed_speaker','unnamed_speaker'])
   self.assertEqual([i['meeting'] for i in debt['items'][:2]],[recent,newer])   # newest meeting first inside a severity
   self.assertEqual(debt['items'][0]['meeting_title'],'Bu hafta')
   self.assertEqual(review_debt(Store(db),days=60)['meetings'],3)
   self.assertEqual(review_debt(Store(db),days=0)['days'],0)
 def test_review_debt_bridge_and_cli(self):
  with tempfile.TemporaryDirectory() as tmp:
   db=Path(tmp)/'db';self.build(db,'Bu hafta',datetime.now(timezone.utc).isoformat())
   r=dispatch({'action':'review_debt'},db)
   self.assertEqual((r['days'],r['meetings'],r['count']),(7,1,2))
   self.assertEqual(dispatch({'action':'review_debt','days':1},db)['meetings'],1)
   p=subprocess.run([sys.executable,'-m','meeting_os','--db',str(db),'review-debt','--days','30'],capture_output=True,text=True)
   self.assertEqual(p.returncode,0,p.stderr);self.assertEqual(json.loads(p.stdout)['counts']['ambiguous'],1)
