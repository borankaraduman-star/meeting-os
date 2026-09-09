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
            self.assertIn('auto_corrected',row['flags']); self.assertEqual(row['original_text'],'Spilendo ve spilendo, ama Spilendoya değil.')
            self.assertEqual(cm.apply_rules(db,m3)['fixes'],0)   # idempotent
            self.assertEqual(cm.revert(db,m3,s1)['reverted'],1)
            row=next(x for x in db.segments(m3) if x['id']==s1)
            self.assertEqual(row['text'],'Spilendo ve spilendo, ama Spilendoya değil.'); self.assertNotIn('auto_corrected',row['flags'])
            self.assertEqual(cm.learned_rules(db),[])              # rejected rule stays off
            cm.accept_rule(db,'Spilendo'); self.assertEqual(len(cm.learned_rules(db)),1)
            self.assertEqual(cm.apply_rules(db,m3)['segments'],1)
            self.assertEqual(next(x for x in db.segments(m3) if x['id']==s2)['text'],'Alakasız cümle')
            db.close()
    def test_glossary_proposals(self):
        rules=[{'original':'Spilendo','replacement':'Splendo','count':2,'meetings':2},{'original':'foo','replacement':'bar','count':2,'meetings':2}]
        entries=[{'term':'Splendo','aliases':[],'mishearings':['Splendou']}]
        self.assertEqual(cm.glossary_proposals(rules,entries),[{'term':'Splendo','mishearing':'Spilendo','meetings':2}])

if __name__=='__main__': unittest.main()
