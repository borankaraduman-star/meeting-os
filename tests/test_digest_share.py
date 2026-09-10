import unittest,tempfile,json,subprocess,sys
from datetime import datetime,timedelta,timezone
from pathlib import Path
from meeting_os.desktop import dispatch
from meeting_os.digest import build_digest,render_digest,local_day,duration_label
from meeting_os.memory import Memory
from meeting_os.share import NameMasker,placeholder,prepare_share,speaker_label
from meeting_os.store import Store
from meeting_os.types import Segment

def analysis(sid,**overrides):
 base={'summary':[{'text':'Rollout planı konuşuldu','evidence':[{'segment_id':sid,'quote':'rollout','start':0,'speaker':'İpek'}]}],
       'decisions':[{'text':'Önce iOS çıkacak','evidence':[{'segment_id':sid,'quote':'iOS önce','start':0,'speaker':'İpek'}]}],'risks':[],
       'questions':[{'text':'Rapor ne zaman?','evidence':[{'segment_id':sid,'quote':'Rapor ne zaman','start':0,'speaker':'İpek'}]}],
       'actions':[{'title':'Raporu çıkarmak','owner':'Boran','due_text':'yarın','evidence':[{'segment_id':sid,'quote':'raporu ben çıkaracağım','start':0,'speaker':'Boran'}]},
                  {'title':'Tasarımı bitirmek','owner':'İpek','due_text':None,'evidence':[{'segment_id':sid,'quote':'İpek tasarımı bitirecek','start':0,'speaker':'İpek'}]}]}
 base.update(overrides);return base

def seed(db,created=None,title='Sprint planı'):
 s=Store(db);mid=s.create_meeting(title,{})
 if created:
  with s.db:s.db.execute('UPDATE meetings SET created=? WHERE id=?',(created,mid))
 sid=s.add_segment(mid,Segment(0,5,'Yarın raporu ben çıkaracağım, İpek tasarımı bitirecek. Rapor ne zaman? iOS önce, rollout sonra.','system','S0',speaker_name='Boran'))
 s.add_segment(mid,Segment(5,125,'Tamam, Boran’ın raporunu bekliyoruz.','system','S1',speaker_name='İpek'))
 s.status(mid,'complete');mem=Memory(s);mem.save_analysis(mid,mem.current_hash(mid),'test-model',analysis(sid));s.close()
 return mid,sid

class DigestTests(unittest.TestCase):
 def test_local_day_converts_utc_and_tolerates_junk(self):
  self.assertEqual(local_day(datetime(2026,9,9,12,0,tzinfo=timezone.utc).isoformat()),datetime(2026,9,9,12,0,tzinfo=timezone.utc).astimezone().date())
  self.assertIsNone(local_day('yok'));self.assertIsNone(local_day(None))
  self.assertEqual(duration_label(125),'2 dk');self.assertEqual(duration_label(3900),'1 sa 05 dk');self.assertEqual(duration_label(10),'1 dk altı')
 def test_digest_keeps_only_the_owner_and_only_that_day(self):
  with tempfile.TemporaryDirectory() as tmp:
   db=Path(tmp)/'db';now=datetime.now(timezone.utc)
   mid,sid=seed(db,now.isoformat())
   old,_=seed(db,(now-timedelta(days=3)).isoformat(),title='Eski toplantı')
   s=Store(db);empty=s.create_meeting('Analizsiz',{});s.add_segment(empty,Segment(0,30,'Selam','system','S0'));s.status(empty,'complete');s.close()
   d=build_digest(Store(db),owner='boran')
   self.assertEqual([m['id'] for m in d['meetings']],[mid,empty]);self.assertEqual([t['title'] for t in d['tasks']],['Raporu çıkarmak'])
   self.assertEqual([q['text'] for q in d['questions']],['Rapor ne zaman?']);self.assertEqual([x['text'] for x in d['decisions']],['Önce iOS çıkacak'])
   self.assertEqual((d['meetings'][0]['seconds'],d['meetings'][0]['speakers'],d['meetings'][0]['analyzed']),(125,2,True));self.assertFalse(d['meetings'][1]['analyzed'])
   text=render_digest(d)
   for needle in ('## Verdiğin sözler','## Cevapsız sorular','## Değişen/alınan kararlar','## Bugünkü toplantılar','Raporu çıkarmak · yarın · açık  (Sprint planı)','Kaynak #%d: “raporu ben çıkaracağım”'%sid,'Rapor ne zaman?','Önce iOS çıkacak','Sprint planı · 2 dk · 2 konuşmacı · analiz hazır','Analizsiz · 1 dk altı · 1 konuşmacı · analiz yok'):
    self.assertIn(needle,text)
   self.assertNotIn('Tasarımı bitirmek',text);self.assertNotIn('Eski toplantı',text)
   other=build_digest(Store(db),day=(now-timedelta(days=3)).astimezone().date().isoformat())
   self.assertEqual([m['id'] for m in other['meetings']],[old])
   self.assertIn('Bu gün kayıtlı toplantı yok.',render_digest(build_digest(Store(db),day='2000-01-01')))
   with self.assertRaises(ValueError):build_digest(Store(db),day='dün')
 def test_digest_bridge_writes_file_and_counts(self):
  with tempfile.TemporaryDirectory() as tmp:
   db=Path(tmp)/'db';seed(db)
   (Path(tmp)/'settings.json').write_text(json.dumps({'user_name':'Boran','user_name_confirmed':True}),encoding='utf-8')   # whose day it is
   out=Path(tmp)/'ozet.md';r=dispatch({'action':'digest','path':str(out)},db)
   self.assertEqual((r['tasks'],r['questions'],r['decisions'],r['meetings']),(1,1,1,1));self.assertIn('# Gün sonu özeti',out.read_text())
   self.assertEqual(dispatch({'action':'digest','day':'2000-01-01'},db)['meetings'],0)
 def test_digest_and_waiting_follow_the_user_name_setting(self):
  """Whose day it is comes from settings; nothing is hard-wired to one person."""
  with tempfile.TemporaryDirectory() as tmp:
   from meeting_os import reports
   db=Path(tmp)/'meeting-os.sqlite';seed(db);out=Path(tmp)/'ozet.md'
   dispatch({'action':'digest','path':str(out)},db)   # no name yet: the day belongs to nobody, so nothing is claimed as "mine"
   self.assertNotIn('Raporu çıkarmak',out.read_text());self.assertNotIn('Tasarımı bitirmek',out.read_text())
   self.assertEqual([g['owner'] for g in dispatch({'action':'waiting_board'},db)['people']],['Boran','İpek'])   # nobody is me: everyone is somebody I wait on
   reports.save_settings(Path(tmp),{'user_name':'Boran'})
   dispatch({'action':'digest','path':str(out)},db)
   self.assertIn('Raporu çıkarmak',out.read_text());self.assertNotIn('Tasarımı bitirmek',out.read_text())
   self.assertEqual([g['owner'] for g in dispatch({'action':'waiting_board'},db)['people']],['İpek'])
   reports.save_settings(Path(tmp),{'user_name':'İpek'})
   dispatch({'action':'digest','path':str(out)},db)
   self.assertIn('Tasarımı bitirmek',out.read_text());self.assertIn('İpek için',out.read_text())
   self.assertEqual([g['owner'] for g in dispatch({'action':'waiting_board'},db)['people']],['Boran'])

class ShareTests(unittest.TestCase):
 def test_placeholders_and_masker_are_stable_and_turkish_aware(self):
  self.assertEqual([placeholder(i) for i in (0,1,25,26,27)],['Kişi A','Kişi B','Kişi Z','Kişi AA','Kişi AB'])
  m=NameMasker([['İpek','ipek hanım'],['Ali Tasarım'],['Ali']])
  self.assertEqual(m.mask('İPEK ve ipek, Ali Tasarım ile Ali’yi aradı; Alina gelmedi. Ipek?'),'Kişi A ve Kişi A, Kişi B ile Kişi C’yi aradı; Alina gelmedi. Kişi A?')
  self.assertEqual(m.masked_names,3);self.assertEqual(NameMasker([]).mask('aynı'),'aynı')
  self.assertEqual(speaker_label({'speaker':'mic:S2'}),'Konuşmacı 3');self.assertEqual(speaker_label({'speaker':'Konuşmacı 1','flags':['cloud_transcript']}),'Konuşmacı 1');self.assertEqual(speaker_label({'speaker':'unknown'}),'İsimsiz konuşmacı')
 def test_prepare_share_masks_everywhere_and_never_writes(self):
  with tempfile.TemporaryDirectory() as tmp:
   db=Path(tmp)/'db';mid,sid=seed(db,title='Boran ile sprint');s=Store(db)
   before=[(r['speaker_name'],r['text']) for r in s.segments(mid)]
   glossary=[{'term':'Mehmet Can','category':'kişi','aliases':['Memo']},{'term':'PMD','category':'kısaltma','aliases':[]}]
   s.add_segment(mid,Segment(130,140,'Memo dedi ki PMD ertelendi.','system','S3'));s.status(mid,'complete')
   plain=prepare_share(s,mid)
   self.assertIn('**00:00 · Boran**',plain['text']);self.assertIn('## Kararlar',plain['text']);self.assertIn('## Özet',plain['text']);self.assertIn('## Görevler',plain['text']);self.assertIn('Raporu çıkarmak · Boran · yarın · açık',plain['text'])
   self.assertEqual((plain['masked_names'],plain['segments']),(0,3));self.assertIn('Konuşmacı 4',plain['text']);self.assertIn('> Analiz güncel değil',plain['text'])
   masked=prepare_share(s,mid,mask_names=True,glossary=glossary)
   t=masked['text']
   self.assertEqual(masked['masked_names'],3);self.assertIn('# Kişi A ile sprint',t);self.assertIn('**00:00 · Kişi A**',t);self.assertIn('**00:05 · Kişi B**',t)
   self.assertIn('Kişi C dedi ki PMD ertelendi.',t);self.assertIn('Kişi A’ın raporunu',t);self.assertIn('Kişi B tasarımı bitirecek',t);self.assertIn('Raporu çıkarmak · Kişi A',t)
   for name in ('Boran','İpek','Memo','Mehmet'): self.assertNotIn(name,t)
   only=prepare_share(s,mid,only_decisions=True,mask_names=True)
   self.assertIn('## Kararlar',only['text']);self.assertIn('Önce iOS çıkacak',only['text']);self.assertNotIn('## Transkript',only['text']);self.assertNotIn('## Özet',only['text']);self.assertEqual(only['segments'],0)
   picked=prepare_share(s,mid,include_segments=[sid],kinds=('transcript',))
   self.assertEqual(picked['segments'],1);self.assertNotIn('## Kararlar',picked['text']);self.assertIn('raporu ben çıkaracağım',picked['text'])
   self.assertEqual(prepare_share(s,mid,exclude_segments=[sid],kinds=['transcript'])['segments'],2)
   self.assertEqual([(r['speaker_name'],r['text']) for r in s.segments(mid)][:2],before)
   with self.assertRaises(ValueError):prepare_share(s,'yok')
   s.close()
 def test_share_bridge_preview_and_export(self):
  with tempfile.TemporaryDirectory() as tmp:
   db=Path(tmp)/'db';mid,_=seed(db)
   (Path(tmp)/'glossary.jsonl').write_text(json.dumps({'term':'İpek','category':'kişi'})+'\n')
   p=dispatch({'action':'share_preview','meeting':mid,'mask_names':True,'kinds':['summary']},db)
   self.assertEqual((p['masked_names'],p['segments']),(2,0));self.assertNotIn('İpek',p['text']);self.assertNotIn('## Transkript',p['text'])
   out=Path(tmp)/'paylas.md';e=dispatch({'action':'share_export','meeting':mid,'path':str(out),'only_decisions':True},db)
   self.assertEqual(e['path'],str(out));self.assertIn('Önce iOS çıkacak',out.read_text());self.assertNotIn('## Özet',out.read_text())
 def test_cli_digest_and_share_write_files(self):
  with tempfile.TemporaryDirectory() as tmp:
   db=Path(tmp)/'db';mid,_=seed(db);out=Path(tmp)/'cli.md'
   (Path(tmp)/'settings.json').write_text(json.dumps({'user_name':'Boran','user_name_confirmed':True}),encoding='utf-8')
   r=subprocess.run([sys.executable,'-m','meeting_os','--db',str(db),'share','--meeting',mid,'--mask-names','--only-decisions','--output',str(out)],capture_output=True,text=True)
   self.assertEqual(r.returncode,0,r.stderr);self.assertEqual(json.loads(r.stdout)['segments'],0);self.assertIn('## Kararlar',out.read_text());self.assertNotIn('Boran',out.read_text())
   r=subprocess.run([sys.executable,'-m','meeting_os','--db',str(db),'digest','--output',str(out)],capture_output=True,text=True)
   self.assertEqual(r.returncode,0,r.stderr);self.assertEqual(json.loads(r.stdout)['tasks'],1);self.assertIn('## Verdiğin sözler',out.read_text())

class OwnNameMaskingTests(unittest.TestCase):
 """A cloud microphone row keeps its label in `speaker`; a mask built from speaker_name published the one
 name the user most wanted hidden — their own."""
 def cloud(self,tmp):
  db=Path(tmp)/'meeting-os.sqlite';s=Store(db);mid=s.create_meeting('Boran ile sprint',{})
  sid=s.add_segment(mid,Segment(0,10,'Boran raporu yarın çıkaracak.','mic','Boran',flags=['cloud_transcript']))
  s.add_segment(mid,Segment(10,20,'Tamam Boran.','system','Konuşmacı 2',flags=['cloud_transcript','cloud_diarization']))
  s.status(mid,'complete');mem=Memory(s)
  mem.save_analysis(mid,mem.current_hash(mid),'test-model',{'summary':[],'risks':[],'questions':[],'decisions':[],
   'actions':[{'title':'Raporu çıkarmak','owner':'Boran','due_text':'yarın','evidence':[{'segment_id':sid,'quote':'Boran raporu yarın çıkaracak.','start':0,'speaker':'Boran'}]}]})
  s.close();return db,mid
 def test_share_masks_the_microphone_owner(self):
  with tempfile.TemporaryDirectory() as tmp:
   db,mid=self.cloud(tmp)
   s=Store(db);text=prepare_share(s,mid,mask_names=True)['text'];s.close()
   self.assertNotIn('Boran',text);self.assertIn('Kişi A',text)
 def test_the_settings_owner_is_masked_even_when_the_rows_say_ben(self):
  with tempfile.TemporaryDirectory() as tmp:
   from meeting_os import reports
   db,mid=self.cloud(tmp)
   s=Store(db)
   with s.db:s.db.execute("UPDATE segments SET speaker='Ben' WHERE source='mic'")
   s.close()
   reports.save_settings(Path(tmp),{'user_name':'Boran'})
   s=Store(db);text=prepare_share(s,mid,mask_names=True)['text'];s.close()
   self.assertNotIn('Boran',text)
 def test_the_digest_mask_covers_the_microphone_owner_too(self):
  with tempfile.TemporaryDirectory() as tmp:
   db,mid=self.cloud(tmp)
   masked=build_digest(Store(db),owner='Boran',mask_names=True)
   self.assertNotIn('Boran',render_digest(masked))

class UnansweredQuestionOrderTests(unittest.TestCase):
 def test_questions_asked_by_someone_else_come_first_and_the_section_is_honest(self):
  with tempfile.TemporaryDirectory() as tmp:
   db=Path(tmp)/'db';s=Store(db);mid=s.create_meeting('Sprint',{})
   sid=s.add_segment(mid,Segment(0,10,'Rapor ne zaman? Bütçe kimde?','system','S0',speaker_name='İpek'));s.status(mid,'complete')
   mem=Memory(s)
   mem.save_analysis(mid,mem.current_hash(mid),'test-model',{'summary':[],'risks':[],'decisions':[],'actions':[],
    'questions':[{'text':'Kendi sorum','evidence':[{'segment_id':sid,'quote':'Rapor ne zaman','start':0,'speaker':'Boran'}]},
                 {'text':'Bana sorulan','evidence':[{'segment_id':sid,'quote':'Bütçe kimde','start':5,'speaker':'İpek'}]}]})
   s.close()
   d=build_digest(Store(db),owner='Boran')
   self.assertEqual([q['text'] for q in d['questions']],['Bana sorulan','Kendi sorum'])
   self.assertEqual([q['for_me'] for q in d['questions']],[True,False])
   text=render_digest(d)
   self.assertIn('## Cevapsız sorular',text);self.assertNotIn('Senden beklenen cevaplar',text)
