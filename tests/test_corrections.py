import tempfile
import unittest
from pathlib import Path
from meeting_os.store import Store
from meeting_os.types import Segment
class CorrectionTests(unittest.TestCase):
    def test_one_misclustered_segment_can_be_corrected(self):
        with tempfile.TemporaryDirectory() as tmp:
            db=Store(Path(tmp)/'db'); mid=db.create_meeting('test')
            first=db.add_segment(mid,Segment(0,4,'a','mic','mic:S0'))
            db.add_segment(mid,Segment(4,8,'b','mic','mic:S0'))
            db.correct_segment(mid,first,'İpek')
            rows=db.segments(mid)
            self.assertEqual(rows[0]['speaker_name'],'İpek'); self.assertIsNone(rows[1]['speaker_name'])
            self.assertEqual(db.profiles(),[]); db.close()


class NegativeFeedbackTests(unittest.TestCase):
    """Q4: correcting a wrong automatic name must unlearn it, not just relabel the meeting."""
    def _voice(self, seed):
        import random
        rnd=random.Random(seed); return [rnd.uniform(-1,1) for _ in range(8)]
    def _cluster(self, db, mid, vector, name=None, suggested=None, cluster='0:S1'):
        seg=Segment(0,12,'uzun bir konuşma','system','system:S1',metrics={'cluster':cluster,'identity':{'name':name,'suggested':suggested}},flags=['cloud_diarization'])
        seg.embedding=vector; seg.embedding_model='m'
        sid=db.add_segment(mid,seg)
        if name: db.db.execute('UPDATE segments SET speaker_name=? WHERE id=?',(name,sid)); db.db.commit()
        return sid
    def test_renaming_an_auto_match_drops_its_sample_and_vetoes_the_person(self):
        with tempfile.TemporaryDirectory() as tmp:
            db=Store(Path(tmp)/'db'); mid=db.create_meeting('t')
            ali=self._voice(1); db.enroll('Ali',ali,'m',10,'manual')
            db.add_sample_if_new('Ali',ali,'m',12,f'auto:{mid}:0:S1')   # the finalize step fed this cluster into Ali
            self.assertEqual(db.profiles()[0]['samples'],2)
            self._cluster(db,mid,ali,name='Ali')
            result=db.enroll_speaker(mid,'system:S1','Veli')                # the user says: that was Veli
            self.assertTrue(result['profile_saved'])
            by={p['name']:p['samples'] for p in db.profiles()}
            self.assertEqual(by,{'Ali':1,'Veli':1})                          # Ali lost the poisoned sample, keeps the manual one
            self.assertEqual(db.db.execute('SELECT previous_name FROM corrections ORDER BY id DESC LIMIT 1').fetchone()[0],'Ali')
            self.assertEqual(db.identify(ali,'m',threshold=0.5,margin=0.0)['name'],'Veli')   # the same voice can never be Ali again
            self.assertEqual([s['name'] for s in db._scores(ali,'m')],['Veli'])
            self.assertEqual([s['name'] for s in db._scores(ali,'m',exclude=mid)],['Ali'])    # replay ignores this meeting's own verdicts
            db.close()
    def test_rejecting_an_unconfirmed_suggestion_without_enrolling(self):
        with tempfile.TemporaryDirectory() as tmp:
            db=Store(Path(tmp)/'db'); mid=db.create_meeting('t')
            ali=self._voice(2); db.enroll('Ali',ali,'m',10,'manual')
            self._cluster(db,mid,ali,suggested='Ali')
            db.correct(mid,'system:S1','Ayşe')
            self.assertEqual(db.identify(ali,'m',threshold=0.5,margin=0.0)['name'],None)     # Ali vetoed, Ayşe has no profile
            db.rename_profile('Ali','Ali Kaya')
            self.assertEqual(db.db.execute('SELECT name FROM rejections').fetchone()[0],'Ali Kaya')
            db.delete_profile('Ali Kaya'); self.assertEqual(db.db.execute('SELECT count(*) FROM rejections').fetchone()[0],0)
            db.close()
    def test_naming_the_same_person_again_is_not_a_rejection(self):
        with tempfile.TemporaryDirectory() as tmp:
            db=Store(Path(tmp)/'db'); mid=db.create_meeting('t')
            ali=self._voice(3); db.enroll('Ali',ali,'m',10,'manual')
            self._cluster(db,mid,ali,suggested='Ali')
            db.enroll_speaker(mid,'system:S1','Ali')
            self.assertEqual(db.db.execute('SELECT count(*) FROM rejections').fetchone()[0],0)
            self.assertEqual(db.profiles()[0]['samples'],2)
            db.close()


class UndoTests(unittest.TestCase):
    def test_undo_restores_labels_and_unlearns(self):
        with tempfile.TemporaryDirectory() as tmp:
            db=Store(Path(tmp)/'db'); mid=db.create_meeting('t')
            import random; rnd=random.Random(9); v=[rnd.uniform(-1,1) for _ in range(8)]
            db.enroll('Ali',v,'m',10,'manual')
            seg=Segment(0,12,'x','system','system:S1',metrics={'cluster':'0:S1','identity':{'name':'Ali'}},flags=['cloud_diarization']); seg.embedding=v; seg.embedding_model='m'
            sid=db.add_segment(mid,seg); db.db.execute('UPDATE segments SET speaker_name=? WHERE id=?',('Ali',sid)); db.db.commit()
            db.enroll_speaker(mid,'system:S1','Veli')
            self.assertEqual({p['name'] for p in db.profiles()},{'Ali','Veli'})
            undone=db.undo_correction(mid)
            self.assertEqual((undone['name'],undone['previous']),('Veli','Ali'))
            self.assertEqual(db.segments(mid)[0]['speaker_name'],'Ali')
            self.assertEqual({p['name'] for p in db.profiles()},{'Ali'})
            self.assertEqual(db.db.execute('SELECT count(*) FROM rejections').fetchone()[0],0)
            self.assertEqual(db.identify(v,'m',threshold=0.5,margin=0.0)['name'],'Ali')
            with self.assertRaises(ValueError): db.undo_correction(mid)
            db.close()
