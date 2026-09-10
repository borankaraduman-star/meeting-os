import tempfile, unittest
from pathlib import Path
from meeting_os.store import Store
from meeting_os.types import Segment
from meeting_os import correction_memory as cm

class CorrectionMemoryTests(unittest.TestCase):
    def _store(self, tmp):
        db=Store(Path(tmp)/'db'); m1=db.create_meeting('a'); m2=db.create_meeting('b'); m3=db.create_meeting('c'); return db,m1,m2,m3
    def _edit(self, db, mid, before, after):
        sid=db.add_segment(mid,Segment(0,5,before,'system','system:S1')); db.correct_text(mid,sid,after); return sid
    def test_substitutions_are_word_level_and_bounded(self):
        self.assertEqual(cm.substitutions('Bugün Spilendo demosu var','Bugün Splendo demosu var'),[('Spilendo','Splendo')])
        self.assertEqual(cm.substitutions('kısa','çok uzun bambaşka bir cümle yazdım buraya'),[])
        self.assertEqual(cm.substitutions('Ali geldi','ali geldi'),[])   # case-only edits are not mishearings
    def test_rule_needs_two_meetings_and_agreement(self):
        with tempfile.TemporaryDirectory() as tmp:
            db,m1,m2,m3=self._store(tmp)
            self._edit(db,m1,'Spilendo ekibi','Splendo ekibi')
            self.assertEqual(cm.learned_rules(db),[])
            self._edit(db,m2,'yeni spilendo sürümü','yeni Splendo sürümü')
            rules=cm.learned_rules(db)
            self.assertEqual([(r['original'],r['replacement'],r['meetings']) for r in rules],[('Spilendo','Splendo',2)])
            self._edit(db,m1,'PRD hazır','PRD tamam'); self._edit(db,m2,'PRD hazır','PRD bitti'); self._edit(db,m3,'PRD hazır','PRD tamam')
            self.assertNotIn('hazır',[r['original'] for r in cm.learned_rules(db)])   # 2/3 agreement is below 0.75
            db.close()
    def test_apply_is_whole_word_case_preserving_reversible(self):
        with tempfile.TemporaryDirectory() as tmp:
            db,m1,m2,m3=self._store(tmp)
            self._edit(db,m1,'Spilendo ekibi','Splendo ekibi'); self._edit(db,m2,'spilendo sürümü','Splendo sürümü')
            s1=db.add_segment(m3,Segment(0,5,'Spilendo ve spilendo, ama Spilendoya değil.','system','system:S1'))
            s2=db.add_segment(m3,Segment(5,9,'Alakasız cümle','system','system:S1'))
            r=cm.apply_rules(db,m3)
            self.assertEqual((r['segments'],r['fixes']),(1,2))
            row=next(x for x in db.segments(m3) if x['id']==s1)
            self.assertEqual(row['text'],'Splendo ve Splendo, ama Spilendoya değil.')
            self.assertIn('auto_corrected',row['flags']); self.assertEqual(row['pre_auto_text'],'Spilendo ve spilendo, ama Spilendoya değil.')
            self.assertIsNone(row.get('original_text'))   # original_text belongs to the user's own edits
            self.assertEqual(cm.apply_rules(db,m3)['fixes'],0)   # idempotent
            self.assertEqual(cm.revert(db,m3,s1)['reverted'],1)
            row=next(x for x in db.segments(m3) if x['id']==s1)
            self.assertEqual(row['text'],'Spilendo ve spilendo, ama Spilendoya değil.'); self.assertNotIn('auto_corrected',row['flags'])
            self.assertEqual(cm.learned_rules(db),[])              # rejected rule stays off
            cm.accept_rule(db,'Spilendo'); self.assertEqual(len(cm.learned_rules(db)),1)
            self.assertEqual(cm.apply_rules(db,m3)['segments'],1)
            self.assertEqual(next(x for x in db.segments(m3) if x['id']==s2)['text'],'Alakasız cümle')
            db.close()
    def test_revert_gives_back_the_manual_edit_not_the_asr_text(self):
        """The user fixed a segment by hand, the automatic pass then ran over it. Undoing the automatic fix
        must return the sentence the user wrote — sharing `original_text` returned the raw ASR text instead."""
        with tempfile.TemporaryDirectory() as tmp:
            db,m1,m2,m3=self._store(tmp)
            self._edit(db,m1,'Spilendo ekibi','Splendo ekibi'); self._edit(db,m2,'spilendo sürümü','Splendo sürümü')
            sid=db.add_segment(m3,Segment(0,5,'Yarın spilendo demusu var','system','system:S1'))
            db.correct_text(m3,sid,'Yarın spilendo demosu var')   # the user's own edit: demusu → demosu
            self.assertEqual(cm.apply_rules(db,m3)['fixes'],1)
            row=next(x for x in db.segments(m3) if x['id']==sid)
            self.assertEqual(row['text'],'Yarın Splendo demosu var')
            cm.revert(db,m3,sid)
            row=next(x for x in db.segments(m3) if x['id']==sid)
            self.assertEqual(row['text'],'Yarın spilendo demosu var')      # the manual edit survives
            self.assertEqual(row['original_text'],'Yarın spilendo demusu var')
            db.close()
    def test_capitalization_follows_turkish_letters(self):
        self.assertEqual(cm._upper_first('istanbul'),'İstanbul')
        self.assertEqual(cm._upper_first('ışık'),'Işık')
        self.assertEqual(cm._upper_first('splendo'),'Splendo')
        self.assertEqual(cm._upper_first(''),'')
        with tempfile.TemporaryDirectory() as tmp:
            db,m1,m2,m3=self._store(tmp)
            self._edit(db,m1,'burada istinbul var','burada istanbul var'); self._edit(db,m2,'yine istinbul geldi','yine istanbul geldi')
            sid=db.add_segment(m3,Segment(0,5,'Istinbul toplantısı','system','system:S1'))
            cm.apply_rules(db,m3)
            self.assertEqual(next(x for x in db.segments(m3) if x['id']==sid)['text'],'İstanbul toplantısı')
            db.close()
    def test_reverting_an_automatic_pass_leaves_a_taught_rule_alone(self):
        """Undo convicts the rule the system inferred. A word the user taught by hand is their decision: it
        stays in Ayarlar → Sesler ve sözlük, and only Unut takes it away."""
        with tempfile.TemporaryDirectory() as tmp:
            db,m1,m2,m3=self._store(tmp)
            self._edit(db,m1,'Spilendo ekibi','Splendo ekibi'); self._edit(db,m2,'spilendo sürümü','Splendo sürümü')
            cm.teach(db,m1,'Jirra','Jira',None)
            sid=db.add_segment(m3,Segment(0,5,'Spilendo ve Jirra','system','system:S1'))
            self.assertEqual(cm.apply_rules(db,m3)['fixes'],2)
            self.assertEqual(next(x for x in db.segments(m3) if x['id']==sid)['text'],'Splendo ve Jira')
            self.assertEqual(cm.revert(db,m3,sid)['rejected'],['Spilendo'])   # the learned one only
            self.assertEqual([(r['original'],r['source']) for r in cm.word_rules(db)],[('Jirra','taught')])
            db.close()

    def test_a_multi_word_rule_matches_by_turkish_folding(self):
        """`re.IGNORECASE` calls "ISI" and "isi" the same word and misses "İ": a phrase rule folds instead."""
        self.assertTrue(cm._pattern('kanal ekibi').search('Bugün Kanal Ekibi toplandı'))
        self.assertTrue(cm._pattern('ısı testi').search('ISI TESTİ yapıldı'))
        self.assertFalse(cm._pattern('isı testi').search('ISI TESTİ yapıldı'))
        self.assertFalse(cm._pattern('kanal ekibi').search('kanal ekibimiz'))

    def test_glossary_proposals(self):
        rules=[{'original':'Spilendo','replacement':'Splendo','count':2,'meetings':2},{'original':'foo','replacement':'bar','count':2,'meetings':2}]
        entries=[{'term':'Splendo','aliases':[],'mishearings':['Splendou']}]
        self.assertEqual(cm.glossary_proposals(rules,entries),[{'term':'Splendo','mishearing':'Spilendo','meetings':2}])

if __name__=='__main__': unittest.main()


class LearningProgressTests(unittest.TestCase):
    def test_weekly_series_counts_auto_and_user_names(self):
        from meeting_os.quality import learning_progress
        with tempfile.TemporaryDirectory() as tmp:
            db=Store(Path(tmp)/'db'); mid=db.create_meeting('a'); db.status(mid,'complete')
            db.add_segment(mid,Segment(0,5,'bir iki üç','system','system:S1',metrics={'cluster':'0:S1','identity':{'name':'Ali'}}))
            db.add_segment(mid,Segment(5,9,'dört beş','system','system:S2',metrics={'cluster':'0:S2','identity':{'suggested':'Veli'}}))
            db.add_segment(mid,Segment(9,12,'altı','system','system:S3',metrics={'cluster':'0:S3','identity':{}}))
            db.correct(mid,'system:S2','Veli')
            db.correct(mid,'system:S1','Ayşe')   # the automatic name was wrong
            rows=learning_progress(db)
            self.assertEqual(len(rows),1); r=rows[0]
            self.assertEqual((r['clusters'],r['auto'],r['auto_wrong'],r['suggested_ok'],r['unnamed']),(3,1,1,1,1))
            self.assertEqual(r['auto_share'],0.0)   # 1 auto − 1 wrong over 2 known voices
            db.close()
