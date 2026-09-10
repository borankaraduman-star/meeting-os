import json,subprocess,sys,tempfile,unittest
from datetime import datetime,timedelta,timezone
from pathlib import Path
from meeting_os.decisions import decision_log,export_decision_log,render_decision_log
from meeting_os.desktop import dispatch
from meeting_os.digest import build_digest,parse_range,render_digest
from meeting_os.memory import Memory
from meeting_os.questions import export_question_radar,question_radar,render_question_radar
from meeting_os.review import review_debt
from meeting_os.scorecard import build_scorecard,label,percent,talk_share
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
   board=build_waiting(Store(db),owner='Boran')   # the caller resolves the name; reports.settings_owner does it in the app
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
   (Path(tmp)/'settings.json').write_text(json.dumps({'user_name':'Boran','user_name_confirmed':True}),encoding='utf-8')   # the board needs to know whose Mac this is
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

def radar(db):
 """Aynı soru iki toplantıda; en yeni toplantının kararı diğer soruyu cevaplamış görünüyor."""
 now=datetime.now(timezone.utc)
 a,_=seed(db,'Sprint planı',(now-timedelta(days=3)).isoformat(),'Önce iOS çıkacak',questions=('Rapor ne zaman hazır olacak?','Bütçe onayı kimde?'))
 b,_=seed(db,'Haftalık durum',(now-timedelta(days=2)).isoformat(),'Sunucu maliyeti düşecek',questions=('Rapor ne zaman hazır olacak?',))
 c,_=seed(db,'Karar toplantısı',now.isoformat(),'Bütçe onayı kimde belli oldu')
 return a,b,c

def carded(db,title,created,status='complete'):
 """Bir toplantı: adlı iki konuşmacı, isimsiz bir küme ve sayılmaması gereken bir hoparlör yankısı."""
 s=Store(db);mid=s.create_meeting(title,{})
 with s.db:s.db.execute('UPDATE meetings SET created=? WHERE id=?',(created,mid))
 sid=s.add_segment(mid,Segment(0,60,'Boran raporu çıkaracak.','system','S0',speaker_name='Boran'))
 s.add_segment(mid,Segment(60,90,'Tamam.','system','S1',speaker_name='İpek'))
 s.add_segment(mid,Segment(90,120,'isimsiz konuşma','system','S2'))
 s.add_segment(mid,Segment(120,150,'yankı','mic','S0',flags=['possible_echo']))
 s.status(mid,status);mem=Memory(s)
 mem.save_analysis(mid,mem.current_hash(mid),'test-model',analysis(sid,'Önce iOS çıkacak',risks=('Takvim dar',),questions=('Rapor ne zaman?',),actions=(('Raporu çıkarmak','Boran','yarın'),)))
 s.close()
 return mid

class QuestionRadarTests(unittest.TestCase):
 def test_repeated_questions_group_and_a_later_decision_is_only_a_hint(self):
  with tempfile.TemporaryDirectory() as tmp:
   db=Path(tmp)/'db';a,b,c=radar(db)
   r=question_radar(Store(db))
   self.assertEqual((r['total'],r['matched'],r['questions']),(2,2,3))
   repeated,single=r['groups']
   self.assertEqual(repeated['text'],'Rapor ne zaman hazır olacak?');self.assertEqual(repeated['count'],2)
   self.assertEqual([x['meeting'] for x in repeated['meetings']],[b,a])   # newest phrasing first
   self.assertIsNone(repeated['answered_by'])   # sonraki karar bu soruya benzemiyor
   self.assertEqual(repeated['evidence']['quote'],'Rapor ne zaman hazır')
   self.assertEqual((single['text'],single['count']),('Bütçe onayı kimde?',1))
   self.assertEqual((single['answered_by']['meeting'],single['answered_by']['text']),(c,'Bütçe onayı kimde belli oldu'))
   self.assertGreaterEqual(single['answered_by']['similarity'],0.45)
   self.assertEqual(question_radar(Store(db),'bütçe')['matched'],1)
   self.assertEqual(question_radar(Store(db),'haftalık')['matched'],1)   # toplantı başlığı da eşleşir
   self.assertEqual(question_radar(Store(db),'blokzincir')['matched'],0)
   self.assertEqual(len(question_radar(Store(db),limit=1)['groups']),1)
   text=render_question_radar(r)
   self.assertIn('# Soru radarı',text);self.assertIn('## Rapor ne zaman hazır olacak?',text);self.assertIn('- 2 toplantıda soruldu',text)
   self.assertIn('Muhtemelen cevaplandı: Bütçe onayı kimde belli oldu',text)
 def test_radar_bridge_export_and_cli_agree(self):
  with tempfile.TemporaryDirectory() as tmp:
   db=Path(tmp)/'db';radar(db)
   bridge=dispatch({'action':'question_radar','query':'rapor'},db)
   self.assertEqual((bridge['total'],len(bridge['groups'])),(2,1))
   out=Path(tmp)/'sorular.md'
   e=dispatch({'action':'question_radar_export','path':str(out),'mask_names':True},db)
   self.assertEqual((e['path'],e['groups'],e['answered']),(str(out),2,1))
   body=out.read_text();self.assertIn('# Soru radarı',body);self.assertNotIn('İpek',body)
   self.assertEqual(export_question_radar(Store(db),out,mask_names=False)['masked_names'],0);self.assertIn('Sprint planı',out.read_text())
   p=subprocess.run([sys.executable,'-m','meeting_os','--db',str(db),'questions','--query','bütçe'],capture_output=True,text=True)
   self.assertEqual(p.returncode,0,p.stderr);self.assertEqual(json.loads(p.stdout)['matched'],1)

class ScorecardTests(unittest.TestCase):
 def test_talk_share_matches_the_app_and_counts_come_from_the_latest_analysis(self):
  with tempfile.TemporaryDirectory() as tmp:
   db=Path(tmp)/'db';mid=carded(db,'Sprint planı',datetime.now(timezone.utc).isoformat())
   s=Store(db);s.db.executescript("CREATE TABLE cloud_chunks(meeting TEXT,position INTEGER,usage TEXT,PRIMARY KEY(meeting,position));INSERT INTO cloud_chunks VALUES('"+mid+"',0,'{\"cost\":0.01,\"seconds\":150}');INSERT INTO cloud_chunks VALUES('"+mid+"',1,'{\"skipped\":\"echo\"}');");s.close()
   card=build_scorecard(Store(db))['meetings'][0]
   self.assertEqual((card['meeting'],card['seconds'],card['cost']),(mid,150.0,0.01))   # süre yankı dahil son bitiş
   self.assertEqual([(x['label'],x['seconds'],x['percent']) for x in card['speakers']],[('Boran',60.0,50),('Konuşmacı 3',30.0,25),('İpek',30.0,25)])
   self.assertNotIn('Hoparlör yankısı',[x['label'] for x in card['speakers']])   # yankı payı sayılmaz
   self.assertEqual([x['named'] for x in card['speakers']],[True,False,True])
   self.assertEqual(card['counts'],{'decisions':1,'actions':1,'questions':1,'risks':1})
   self.assertTrue(card['analyzed']);self.assertFalse(card['stale'])
   self.assertEqual(label({'speaker':'S0','flags':['provisional']}),'Geçici konuşmacı')
   self.assertEqual(label({'speaker':'0:S4','flags':[]}),'Konuşmacı 5')
   self.assertEqual(label({'speaker':'unknown','flags':[],'suggested':'Ayşe'}),'Ayşe?')
   self.assertEqual(label({'speaker':'Konuşmacı 2','flags':['cloud_transcript']}),'Konuşmacı 2')
   self.assertEqual((percent(0.125),percent(0.5)),(13,50))   # Swift .rounded(): half away from zero
   self.assertEqual(talk_share([{'start':0,'end':0,'speaker':'S0','flags':[]}]),[])
 def test_period_defaults_to_seven_days_and_bridge_and_cli_agree(self):
  with tempfile.TemporaryDirectory() as tmp:
   db=Path(tmp)/'db';now=datetime.now(timezone.utc)
   carded(db,'Bu hafta',now.isoformat())
   carded(db,'Dün',(now-timedelta(days=1)).isoformat())
   old=carded(db,'Geçen ay',(now-timedelta(days=40)).isoformat())
   carded(db,'Yarım',now.isoformat(),status='processing')
   period=build_scorecard(Store(db))['period']
   self.assertEqual((period['meetings'],period['seconds'],period['hours']),(2,300.0,0.08))
   self.assertEqual((period['decisions'],period['tasks'],period['questions'],period['risks'],period['cost']),(2,2,2,2,0.0))
   self.assertEqual([(p['name'],p['minutes'],p['meetings']) for p in period['speakers']],[('Boran',2.0,2),('İpek',1.0,2)])   # isimsiz küme sayılmaz
   wide=build_scorecard(Store(db),start=(now-timedelta(days=40)).astimezone().date().isoformat(),end=now.astimezone().date().isoformat())
   self.assertEqual(wide['period']['meetings'],3);self.assertIn(old,[c['meeting'] for c in wide['meetings']])
   with self.assertRaises(ValueError):build_scorecard(Store(db),start='dün')
   r=dispatch({'action':'scorecard'},db)
   self.assertEqual(r['period']['meetings'],2);self.assertEqual(len(r['meetings']),2)
   self.assertEqual(dispatch({'action':'scorecard','from':(now-timedelta(days=40)).astimezone().date().isoformat(),'to':now.astimezone().date().isoformat()},db)['period']['meetings'],3)
   self.assertEqual(dispatch({'action':'scorecard','from':(now-timedelta(days=40)).astimezone().date().isoformat()},db)['period']['meetings'],1)   # tek uç verilince digest gibi tek gün
   p=subprocess.run([sys.executable,'-m','meeting_os','--db',str(db),'scorecard'],capture_output=True,text=True)
   self.assertEqual(p.returncode,0,p.stderr);self.assertEqual(json.loads(p.stdout)['period']['meetings'],2)

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


class BriefTests(unittest.TestCase):
    def test_brief_groups_owed_tasks_and_history_by_attendee(self):
        import tempfile, json
        from pathlib import Path
        from meeting_os.store import Store
        from meeting_os.memory import Memory
        from meeting_os.types import Segment
        from meeting_os.desktop import dispatch
        with tempfile.TemporaryDirectory() as tmp:
            db=Path(tmp)/'m.sqlite'; s=Store(db); mid=s.create_meeting('Sprint',{})
            s.add_segment(mid,Segment(0,10,'Cuma raporu ben gönderirim.','system','Konuşmacı 1',speaker_name='Ayşe Yılmaz')); s.status(mid,'complete')
            mem=Memory(s)
            with mem.db:
                mem.db.execute("INSERT INTO analyses(meeting,input_hash,model,payload,created) VALUES(?,?,?,?,?)",(mid,'h','m',json.dumps({'decisions':[{'text':'Rapor cuma gidecek'}],'questions':[{'text':'Bütçe onayı kimde?'}]}),'2026-09-09T10:00:00+00:00'))
                mem.db.execute("INSERT INTO tasks(id,meeting,analysis,input_hash,title,owner,due_text,state,payload,user_edited,created,updated) VALUES('t1',?,NULL,'h','Raporu gönder','Ayşe','cuma','open','{}',0,'2026-09-09T10:00:00+00:00','2026-09-09T10:00:00+00:00')",(mid,))
                mem.db.execute("INSERT INTO tasks(id,meeting,analysis,input_hash,title,owner,due_text,state,payload,user_edited,created,updated) VALUES('t2',?,NULL,'h','Bütçeyi sor','Boran',NULL,'open','{}',0,'2026-09-09T10:00:00+00:00','2026-09-09T10:00:00+00:00')",(mid,))
            s.close()
            (Path(tmp)/'settings.json').write_text(json.dumps({'user_name':'Boran','user_name_confirmed':True}),encoding='utf-8')   # "Benim açık görevlerim" needs a name to filter by
            r=dispatch({'action':'brief','title':'Haftalık','attendees':['Ayşe Yılmaz','Yeni Kişi']},db)
            self.assertEqual((r['people'],r['owed'],r['questions']),(2,1,1))
            self.assertIn('## Ayşe Yılmaz · son görüşme: Sprint',r['text']); self.assertIn('- Raporu gönder · cuma',r['text']); self.assertIn('Bütçe onayı kimde?',r['text'])
            self.assertIn('## Yeni Kişi · kayıtlı toplantı yok',r['text']); self.assertIn('- Bütçeyi sor',r['text'])


class MemoryMemoTests(unittest.TestCase):
 def test_one_transcript_read_per_meeting_across_latest_and_actions(self):
  with tempfile.TemporaryDirectory() as tmp:
   db=Path(tmp)/'db';a,_,b,_,_,_=week(db)
   s=Store(db);reads=[];inner=s.display_segments
   s.display_segments=lambda mid:(reads.append(mid),inner(mid))[1]
   mem=Memory(s)
   mem.latest(a);mem.latest(b);mem.actions();mem.latest(a);mem.actions()
   self.assertEqual(reads,[a,b])
   s.correct(a,'S0','Yeni İsim')   # a write through the connection drops the memo
   mem.latest(a);mem.latest(b)
   self.assertEqual(reads,[a,b,a,b])

def _similarity_reference(a,b):
 """The similarity from before the screening, kept verbatim so the fast one can be checked against it."""
 import difflib,re
 from meeting_os.continuity import STOP
 from meeting_os.memory import normalize
 tok=lambda t:{w for w in re.split(r'\W+',normalize(t or '')) if len(w)>2 and w not in STOP}
 ta,tb=tok(a),tok(b)
 jaccard=len(ta&tb)/len(ta|tb) if ta and tb else 0.0
 ratio=difflib.SequenceMatcher(None,normalize(a or ''),normalize(b or '')).ratio()
 return round(max(jaccard,ratio),3)

def _synthetic_titles(n=80):
 import random
 words='rapor hazırlamak bütçe onay müşteri görüşme tasarım revizyon ekip toplantı sunum teslim tarih güncelleme liste fatura ödeme sözleşme imza test yayın sürüm hata düzeltme'.split()
 r=random.Random(11)
 return [' '.join(r.choices(words,k=r.randint(2,9))) for _ in range(n)]+['','Rapor hazır','rapor hazır','Rapor hazır!']

class SimilarityScreeningTests(unittest.TestCase):
 """The early exits may only skip work: every threshold decision and every kept score has to survive them."""
 def test_score_matches_the_reference_at_and_above_the_floor(self):
  from meeting_os.continuity import similarity
  texts=_synthetic_titles()
  for a in texts:
   for b in texts:
    old=_similarity_reference(a,b)
    self.assertEqual(similarity(a,b),old,(a,b))                    # no floor: exact everywhere
    for floor in (0.45,0.5,0.6):
     new=similarity(a,b,floor)
     self.assertEqual(old>=floor,new>=floor,(a,b,floor,old,new))   # same decision
     self.assertLessEqual(new,old,(a,b,floor))                     # never an overestimate
     if new>=floor: self.assertEqual(new,old,(a,b,floor))          # exact wherever it is kept

 def test_similarity_index_is_the_full_ordered_matrix(self):
  from meeting_os.continuity import similarity_index
  texts=_synthetic_titles(50)
  for floor in (0.45,0.6):
   self.assertEqual(similarity_index(texts,floor),
                    {(i,j):_similarity_reference(a,b) for i,a in enumerate(texts) for j,b in enumerate(texts)
                     if i!=j and _similarity_reference(a,b)>=floor})


def reversed_seed(db, title='Sprint planı', created=None):
 """Bir toplantı: kendi içinde geri alınmış bir karar ve onu iptal eden karar."""
 s=Store(db);mid=s.create_meeting(title,{})
 if created:
  with s.db:s.db.execute('UPDATE meetings SET created=? WHERE id=?',(created,mid))
 sid=s.add_segment(mid,Segment(0,60,'E-posta doğrulama eklenecek. Sonra: karar iptal edildi.','system','S0',speaker_name='Boran'))
 s.status(mid,'complete');mem=Memory(s)
 payload={'summary':[],'risks':[],'questions':[{'text':'Rapor ne zaman?','evidence':[{'segment_id':sid,'quote':'E-posta','start':0,'speaker':'İpek'}]}],'actions':[],
          'decisions':[{'text':'E-posta doğrulama eklenecek','superseded':True,'note':'geri alındı','needs_review':True,
                        'evidence':[{'segment_id':sid,'quote':'E-posta doğrulama eklenecek','start':0,'speaker':'Boran'}]},
                       {'text':'E-posta doğrulama adımı eklenmeyecek','evidence':[{'segment_id':sid,'quote':'karar iptal edildi','start':0,'speaker':'Boran'}]}]}
 mem.save_analysis(mid,mem.current_hash(mid),'test-model',payload);s.close()
 return mid,sid


class ReversedDecisionTests(unittest.TestCase):
 """Dropping a reversed decision made the log claim the reversal never happened; showing it as live was worse."""
 def test_the_log_keeps_it_marked_and_counts_only_the_live_ones(self):
  with tempfile.TemporaryDirectory() as tmp:
   db=Path(tmp)/'db';reversed_seed(db)
   log=decision_log(Store(db))
   self.assertEqual((log['total'],log['live'],log['superseded']),(2,1,1))
   self.assertEqual([d['superseded'] for d in log['decisions']],[True,False])
   text=render_decision_log(log)
   self.assertIn('## E-posta doğrulama eklenecek (geri alındı)',text);self.assertIn('1 geri alındı',text)
 def test_digest_share_and_scorecard_agree_that_it_no_longer_stands(self):
  with tempfile.TemporaryDirectory() as tmp:
   from meeting_os.share import prepare_share
   db=Path(tmp)/'db';mid,_=reversed_seed(db)
   d=build_digest(Store(db))
   self.assertEqual((len(d['decisions']),d['live_decisions'],d['superseded_decisions']),(2,1,1))
   self.assertIn('- E-posta doğrulama eklenecek (geri alındı)',render_digest(d))
   s=Store(db);self.assertIn('(geri alındı)',prepare_share(s,mid)['text'])
   card=build_scorecard(s)['meetings'][0]
   self.assertEqual((card['counts']['decisions'],card['superseded_decisions']),(1,1));s.close()


class StaleAnalysisReportTests(unittest.TestCase):
 def test_a_report_says_how_many_meetings_show_an_out_of_date_analysis(self):
  with tempfile.TemporaryDirectory() as tmp:
   db=Path(tmp)/'db';mid,sid=reversed_seed(db)
   self.assertEqual(decision_log(Store(db))['stale_meetings'],0)
   s=Store(db);s.correct_text(mid,sid,'Metin değişti; e-posta doğrulama eklenecek.');s.close()
   log=decision_log(Store(db))
   self.assertEqual(log['stale_meetings'],1);self.assertTrue(all(d['stale'] for d in log['decisions']))
   self.assertIn('1 toplantının analizi güncel değil',render_decision_log(log))
   radar=question_radar(Store(db))
   self.assertEqual(radar['stale_meetings'],1);self.assertTrue(radar['groups'][0]['stale'])
 def test_the_header_counts_only_the_meetings_the_reader_can_see(self):
  """A filter or the limit hides the stale meeting; the header must stop announcing it."""
  with tempfile.TemporaryDirectory() as tmp:
   db=Path(tmp)/'db';mid,sid=reversed_seed(db,title='Eski karar',created=(datetime.now(timezone.utc)-timedelta(days=2)).isoformat())
   s=Store(db);s.correct_text(mid,sid,'Metin değişti; e-posta doğrulama eklenecek.');s.close()
   seed(db,'Taze toplantı',datetime.now(timezone.utc).isoformat(),'Fiyatlandırma sabit kalacak',questions=('Bütçe kimde?',))
   self.assertEqual(decision_log(Store(db))['stale_meetings'],1)
   self.assertEqual(decision_log(Store(db),query='Fiyatlandırma')['stale_meetings'],0)   # the stale meeting is not in the list
   self.assertEqual(decision_log(Store(db),limit=1)['stale_meetings'],0)                 # …nor below the limit
   self.assertEqual(question_radar(Store(db))['stale_meetings'],1)
   self.assertEqual(question_radar(Store(db),query='Bütçe')['stale_meetings'],0)


class ScorecardCostTests(unittest.TestCase):
 def test_an_analysed_meeting_with_no_recorded_call_reports_an_unknown_cost(self):
  with tempfile.TemporaryDirectory() as tmp:
   db=Path(tmp)/'db';carded(db,'Sprint planı',datetime.now(timezone.utc).isoformat())
   card=build_scorecard(Store(db))
   self.assertIsNone(card['meetings'][0]['analysis_cost'])
   self.assertFalse(card['meetings'][0]['analysis_cost_known']);self.assertFalse(card['period']['analysis_cost_known'])
   self.assertFalse(card['empty'])
 def test_an_empty_window_says_so_instead_of_drawing_zeros(self):
  with tempfile.TemporaryDirectory() as tmp:
   db=Path(tmp)/'db';carded(db,'Geçen ay',(datetime.now(timezone.utc)-timedelta(days=40)).isoformat())
   card=build_scorecard(Store(db))
   self.assertTrue(card['empty']);self.assertEqual(card['period']['meetings'],0);self.assertTrue(card['period']['analysis_cost_known'])
 def test_the_microphone_owner_is_one_of_the_top_speakers(self):
  with tempfile.TemporaryDirectory() as tmp:
   db=Path(tmp)/'db';s=Store(db);mid=s.create_meeting('Bulut toplantısı',{})
   s.add_segment(mid,Segment(0,60,'Ben raporu çıkaracağım.','mic','Boran',flags=['cloud_transcript']))   # cloud mic row: the label is in `speaker`, speaker_name is NULL
   s.add_segment(mid,Segment(60,90,'Tamam.','system','Konuşmacı 2',flags=['cloud_transcript','cloud_diarization']))
   s.status(mid,'complete');s.close()
   period=build_scorecard(Store(db))['period']
   self.assertEqual([p['name'] for p in period['speakers']],['Boran'])   # the unnamed cloud cluster is not a person yet


class ReviewDebtWindowTests(unittest.TestCase):
 def test_the_window_is_seven_local_calendar_days_like_the_karne(self):
  with tempfile.TemporaryDirectory() as tmp:
   from datetime import datetime as dt, time as tm
   db=Path(tmp)/'db';today=dt.now(timezone.utc).astimezone().date()
   at=lambda day:dt.combine(day,tm(12,0)).astimezone().astimezone(timezone.utc).isoformat()
   carded(db,'Altı gün önce',at(today-timedelta(days=6)))
   carded(db,'Yedi gün önce',at(today-timedelta(days=7)))
   self.assertEqual(review_debt(Store(db))['meetings'],1)     # the karne's window: today and the six days before it
   self.assertEqual(review_debt(Store(db),days=8)['meetings'],2)


class BriefNameMatchTests(unittest.TestCase):
 def test_a_name_inside_another_name_is_not_the_same_person(self):
  from meeting_os.brief import build_brief,same_person
  self.assertTrue(same_person('Ayşe','ayşe yılmaz'));self.assertTrue(same_person('İlker','Ilker'))
  self.assertFalse(same_person('Ali','Salih'));self.assertFalse(same_person('Ali','Alican'))
  with tempfile.TemporaryDirectory() as tmp:
   db=Path(tmp)/'db';s=Store(db);mid=s.create_meeting('Sprint',{})
   s.add_segment(mid,Segment(0,10,'Salih raporu yazacak.','system','S0',speaker_name='Salih'));s.status(mid,'complete')
   mem=Memory(s)
   with mem.db:
    mem.db.execute("INSERT INTO tasks(id,meeting,analysis,input_hash,title,owner,due_text,state,payload,user_edited,created,updated)"
                   " VALUES('t1',?,NULL,'h','Raporu yaz','Salih','cuma','open','{}',0,'2026-09-09T10:00:00+00:00','2026-09-09T10:00:00+00:00')",(mid,))
   s.close()
   brief=build_brief(Store(db),'Haftalık',['Ali'])
   self.assertEqual((brief['people'][0]['owed'],brief['people'][0]['meetings']),([],0))
   self.assertEqual(len(build_brief(Store(db),'Haftalık',['Salih'])['people'][0]['owed']),1)
