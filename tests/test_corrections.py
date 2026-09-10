import json
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


    def test_a_diacritic_free_retype_is_not_a_rejection(self):
        """Typing the suggestion back as "Ayse" is the same person. It used to be read as "this voice is not
        Ayşe": her samples were deleted and her profile vetoed for that voice for good."""
        from meeting_os.store import fold_name
        self.assertEqual(fold_name('Ayse'),fold_name('Ayşe'))
        self.assertEqual(fold_name('İSTANBUL'),fold_name('istanbul'))
        self.assertNotEqual(fold_name('Ayşe'),fold_name('Ayla'))
        for typed in ('Ayse','ayşe','AYŞE'):
            with self.subTest(typed=typed),tempfile.TemporaryDirectory() as tmp:
                db=Store(Path(tmp)/'db'); mid=db.create_meeting('t')
                voice=self._voice(7); db.enroll('Ayşe',voice,'m',10,'manual')
                db.add_sample_if_new('Ayşe',voice,'m',12,f'auto:{mid}:0:S1')
                self._cluster(db,mid,voice,suggested='Ayşe')
                db.correct(mid,'system:S1',typed)
                self.assertEqual(db.db.execute('SELECT count(*) FROM rejections').fetchone()[0],0)
                self.assertEqual({p['name']:p['samples'] for p in db.profiles()},{'Ayşe':2})
                self.assertEqual(db.identify(voice,'m',threshold=0.5,margin=0.0)['name'],'Ayşe')
                row=db.db.execute('SELECT confirmed FROM profile_stats WHERE name=?',('Ayşe',)).fetchone()
                self.assertFalse(row and row[0])   # a retype is not a rejection, but only the exact suggested spelling counts as a confirmation
                db.close()
        with tempfile.TemporaryDirectory() as tmp:
            db=Store(Path(tmp)/'db'); mid=db.create_meeting('t'); voice=self._voice(7); db.enroll('Ayşe',voice,'m',10,'manual')
            self._cluster(db,mid,voice,suggested='Ayşe'); db.correct(mid,'system:S1','Ayşe')
            self.assertEqual(db.db.execute('SELECT confirmed FROM profile_stats WHERE name=?',('Ayşe',)).fetchone()[0],1)
            db.close()
    def test_rejected_samples_are_hidden_not_destroyed(self):
        """A naming that rejects a person hides their samples; the rows stay so undo can hand them back, and
        nothing that reads profiles or scores a voice may see them in the meantime."""
        with tempfile.TemporaryDirectory() as tmp:
            db=Store(Path(tmp)/'db'); mid=db.create_meeting('t')
            ali=self._voice(11); db.enroll('Ali',ali,'m',10,'manual')
            db.add_sample_if_new('Ali',ali,'m',12,f'auto:{mid}:0:S1')
            self._cluster(db,mid,ali,name='Ali')
            db.enroll_speaker(mid,'system:S1','Veli')
            self.assertEqual({p['name']:p['samples'] for p in db.profiles()},{'Ali':1,'Veli':1})
            self.assertEqual(len(db.profile_samples('Ali')),1)
            self.assertEqual([p['samples'] for p in db.profile_health() if p['name']=='Ali'],[1])
            self.assertEqual(db.db.execute('SELECT count(*) FROM samples WHERE deleted_by IS NOT NULL').fetchone()[0],1)   # kept, not deleted
            db.undo_correction(mid)
            self.assertEqual({p['name']:p['samples'] for p in db.profiles()},{'Ali':2})   # the hidden sample is back
            self.assertEqual(len(db.profile_samples('Ali')),2)
            self.assertEqual(db.db.execute('SELECT count(*) FROM samples WHERE deleted_by IS NOT NULL').fetchone()[0],0)
            self.assertEqual(db.identify(ali,'m',threshold=0.5,margin=0.0)['name'],'Ali')
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


def at(similarity):
    """A 2-D unit vector whose cosine against [1,0] is exactly `similarity`. With one sample per person the blended
    score is that cosine, so a test can name the number it wants instead of hoping a random vector lands there."""
    import math
    angle=math.acos(similarity); return [math.cos(angle),math.sin(angle)]

def cluster(db, mid, vector, speaker, key, name=None, identity=None, seconds=12.0, text='uzun bir konuşma'):
    seg=Segment(0,seconds,text,'system',speaker,metrics={'cluster':key,'identity':identity or {}},flags=['cloud_diarization'])
    seg.embedding=vector; seg.embedding_model='m'
    sid=db.add_segment(mid,seg)
    if name: db.db.execute('UPDATE segments SET speaker_name=? WHERE id=?',(name,sid)); db.db.commit()
    return sid

def by_speaker(db, mid, speaker):
    return [r for r in db.segments(mid) if r['speaker']==speaker][0]


class ResuggestTests(unittest.TestCase):
    """Q9: naming one voice must change what the meeting's other unnamed voices are taken to be, right away."""
    def test_naming_a_cluster_suggests_the_same_voice_for_another(self):
        with tempfile.TemporaryDirectory() as tmp:
            db=Store(Path(tmp)/'db'); mid=db.create_meeting('t')
            cluster(db,mid,[1.0,0.0],'system:S1','0:S1')
            cluster(db,mid,at(0.85),'system:S2','0:S2')     # the same person, a little further away: suggestion band
            db.enroll_speaker(mid,'system:S1','Ali')
            self.assertEqual(db.resuggest(mid),{'renamed':0,'suggested':1})
            second=by_speaker(db,mid,'system:S2')
            self.assertEqual(second['metrics']['identity']['suggested'],'Ali')
            self.assertIsNone(second['speaker_name'])       # a suggestion is never written as a name
            db.close()
    def test_a_close_second_cluster_is_named_outright(self):
        with tempfile.TemporaryDirectory() as tmp:
            db=Store(Path(tmp)/'db'); mid=db.create_meeting('t')
            cluster(db,mid,[1.0,0.0],'system:S1','0:S1')
            cluster(db,mid,at(0.95),'system:S2','0:S2')
            db.enroll_speaker(mid,'system:S1','Ali')
            self.assertEqual(db.resuggest(mid),{'renamed':1,'suggested':0})
            self.assertEqual(by_speaker(db,mid,'system:S2')['speaker_name'],'Ali')
            db.close()
    def test_a_rejected_person_is_never_suggested_for_that_voice(self):
        with tempfile.TemporaryDirectory() as tmp:
            db=Store(Path(tmp)/'db'); mid=db.create_meeting('t')
            v=[1.0,0.0]; db.enroll('Ali',v,'m',10,'manual')
            cluster(db,mid,v,'system:S1','0:S1',identity={'name':None,'suggested':'Ali'})
            cluster(db,mid,v,'system:S2','0:S2')            # the same voice, split into a second cluster
            db.enroll_speaker(mid,'system:S1','Ayşe')       # "no, that is Ayşe"
            db.resuggest(mid)
            second=by_speaker(db,mid,'system:S2')
            self.assertEqual(second['speaker_name'],'Ayşe')
            self.assertNotEqual(second['metrics']['identity'].get('suggested'),'Ali')
            self.assertNotEqual(second['metrics']['identity'].get('name'),'Ali')
            db.close()
    def test_a_name_the_user_gave_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            db=Store(Path(tmp)/'db'); mid=db.create_meeting('t')
            v=[1.0,0.0]; db.enroll('Veli',v,'m',10,'manual')   # a perfect match for the cluster below
            cluster(db,mid,v,'system:S1','0:S1')
            db.correct(mid,'system:S1','Ali')
            self.assertEqual(db.resuggest(mid),{'renamed':0,'suggested':0})
            self.assertEqual(by_speaker(db,mid,'system:S1')['speaker_name'],'Ali')
            db.close()
    def test_the_bridge_reports_what_naming_changed(self):
        from meeting_os.desktop import dispatch
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'db'; db=Store(path); mid=db.create_meeting('t'); db.status(mid,'complete')
            cluster(db,mid,[1.0,0.0],'system:S1','0:S1')
            cluster(db,mid,at(0.85),'system:S2','0:S2')
            db.close()
            result=dispatch({'action':'label_speaker','meeting':mid,'speaker':'system:S1','name':'Ali','enroll':True},path)
            self.assertEqual((result['renamed'],result['suggested']),(0,1))


class PersonThresholdTests(unittest.TestCase):
    """Q5: the bar moves only for people the user has already judged, and only by his own corrections."""
    def _profile(self, db, name='Ali'):
        db.enroll(name,[1.0,0.0],'m',10,'manual'); return [1.0,0.0]
    def test_two_confirmed_suggestions_lower_the_bar(self):
        with tempfile.TemporaryDirectory() as tmp:
            db=Store(Path(tmp)/'db'); self._profile(db)
            probe=at(0.855)
            self.assertIsNone(db.identify(probe,'m',0.87,0.05)['name'])          # today's bar: not confident enough
            for i in range(2):
                mid=db.create_meeting(f't{i}')
                cluster(db,mid,[1.0,0.0],'system:S1','0:S1',identity={'name':None,'suggested':'Ali'})
                db.correct(mid,'system:S1','Ali')                                 # the user confirms the suggestion
            self.assertEqual(db.db.execute('SELECT confirmed,wrong FROM profile_stats WHERE name=?',('Ali',)).fetchone()[0],2)
            self.assertAlmostEqual(db.person_threshold('Ali',0.87),0.85)
            named=db.identify(probe,'m',0.87,0.05)
            self.assertEqual(named['name'],'Ali'); self.assertAlmostEqual(named['threshold_used'],0.85)
            db.close()
    def test_one_overruled_automatic_name_raises_the_bar_and_undo_lowers_it_again(self):
        with tempfile.TemporaryDirectory() as tmp:
            db=Store(Path(tmp)/'db'); self._profile(db,'Veli')
            probe=at(0.88)
            self.assertEqual(db.identify(probe,'m',0.87,0.05)['name'],'Veli')     # today's bar: named
            mid=db.create_meeting('t')
            cluster(db,mid,[0.0,1.0],'system:S1','0:S1',name='Veli',identity={'name':'Veli','suggested':None})   # a different voice the app called Veli
            db.correct(mid,'system:S1','Kaya')                                    # the user overrules the automatic name
            self.assertEqual(db.db.execute('SELECT wrong FROM profile_stats WHERE name=?',('Veli',)).fetchone()[0],1)
            self.assertAlmostEqual(db.person_threshold('Veli',0.87),0.89)
            careful=db.identify(probe,'m',0.87,0.05)
            self.assertIsNone(careful['name']); self.assertEqual(careful['candidate'],'Veli')   # a suggestion now, not a name
            db.undo_correction(mid)
            self.assertEqual(db.db.execute('SELECT wrong FROM profile_stats WHERE name=?',('Veli',)).fetchone()[0],0)
            self.assertEqual(db.identify(probe,'m',0.87,0.05)['name'],'Veli')
            db.close()
    def test_the_personal_bar_never_ends_up_above_the_global_one(self):
        """The 0.84 floor is a floor, not a target: on the local paths base is 0.80, and clamping to it made a
        person the user had *confirmed* harder to match than one he had never judged."""
        with tempfile.TemporaryDirectory() as tmp:
            db=Store(Path(tmp)/'db'); self._profile(db)
            for i in range(3):
                mid=db.create_meeting(f't{i}')
                cluster(db,mid,[1.0,0.0],'system:S1','0:S1',identity={'name':None,'suggested':'Ali'})
                db.correct(mid,'system:S1','Ali')
            for base in (0.80,0.82,0.84,0.87):
                with self.subTest(base=base):
                    self.assertLessEqual(db.person_threshold('Ali',base),base)
            self.assertAlmostEqual(db.person_threshold('Ali',0.80),0.80)   # floor may not push it up
            self.assertAlmostEqual(db.person_threshold('Ali',0.87),0.84)   # three confirmations, stopped by the floor
            self.assertAlmostEqual(db.person_threshold('Kimse',0.80),0.80)  # no evidence: the global bar stands
            db.close()
    def test_existing_corrections_are_backfilled_once(self):
        import sqlite3
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'db'
            raw=sqlite3.connect(path)   # a database written before profile_stats existed
            raw.executescript('''CREATE TABLE meetings(id TEXT PRIMARY KEY, title TEXT, created TEXT, status TEXT, metadata TEXT);
            CREATE TABLE segments(id INTEGER PRIMARY KEY, meeting TEXT, start REAL, end REAL, source TEXT, speaker TEXT, speaker_name TEXT, payload TEXT);
            CREATE TABLE corrections(id INTEGER PRIMARY KEY, meeting TEXT, speaker TEXT, name TEXT, created TEXT);''')
            raw.execute("INSERT INTO meetings VALUES('m','t','2026-01-01','complete','{}')")
            raw.execute("INSERT INTO segments(meeting,start,end,source,speaker,speaker_name,payload) VALUES('m',0,10,'system','system:S1','Ali',?)",
                        (json.dumps({'metrics':{'identity':{'name':None,'suggested':'Ali'}}}),))
            raw.execute("INSERT INTO corrections(meeting,speaker,name,created) VALUES('m','system:S1','Ali','2026-01-01')")
            raw.commit(); raw.close()
            db=Store(path)
            self.assertEqual(db.db.execute('SELECT confirmed FROM profile_stats WHERE name=?',('Ali',)).fetchone()[0],1)
            self.assertAlmostEqual(db.person_threshold('Ali',0.87),0.86)
            self.assertAlmostEqual(db.person_threshold('Ali',0.87,exclude='m'),0.87)   # a meeting never vouches for itself
            db.close()
            Store(path).close()   # reopening must not count the same correction twice
            db=Store(path); self.assertEqual(db.db.execute('SELECT confirmed FROM profile_stats WHERE name=?',('Ali',)).fetchone()[0],1); db.close()


class CleanCandidateTests(unittest.TestCase):
    """Q8: the picker offers only turns that would actually make a good sample."""
    def test_longest_clean_turns_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            db=Store(Path(tmp)/'db'); mid=db.create_meeting('Pazartesi'); db.status(mid,'complete')
            good=cluster(db,mid,[1.0,0.0],'system:S1','0:S1',name='Ali',seconds=20.0,text='uzun ve temiz')
            cluster(db,mid,[1.0,0.0],'system:S1','0:S1',name='Ali',seconds=4.0)                  # too short
            short=Segment(0,30,'çakışma','system','system:S2',flags=['cloud_diarization','speaker_ambiguous'])
            short.embedding=[1.0,0.0];short.embedding_model='m'
            sid=db.add_segment(mid,short);db.db.execute('UPDATE segments SET speaker_name=? WHERE id=?',('Ali',sid));db.db.commit()   # flagged
            plain=Segment(0,40,'vektörsüz','system','system:S3',flags=['cloud_diarization'])
            sid=db.add_segment(mid,plain);db.db.execute('UPDATE segments SET speaker_name=? WHERE id=?',('Ali',sid));db.db.commit()   # no embedding
            got=db.clean_candidates('Ali')
            self.assertEqual([c['id'] for c in got],[good])
            self.assertEqual(got[0]['meeting_title'],'Pazartesi'); self.assertEqual(got[0]['seconds'],20.0)
            db.enroll_segment(mid,good,'Ali')
            self.assertEqual(db.clean_candidates('Ali'),[])                                       # already enrolled, not offered again
            self.assertEqual(db.profile_health()[0]['last_meeting_title'],'Pazartesi')
            db.close()
    def test_person_note_explains_a_thin_profile(self):
        with tempfile.TemporaryDirectory() as tmp:
            db=Store(Path(tmp)/'db'); db.enroll('Ali',[1.0,0.0],'m',10,'manual')
            note=db.explain_identity([1.0,0.0],'m',base=0.87)[0]
            self.assertEqual(note['person_note'],'tek örnek — ikinci bir temiz örnek isabeti artırır')
            self.assertAlmostEqual(note['threshold_used'],0.87)
            mid=db.create_meeting('t')
            cluster(db,mid,[1.0,0.0],'system:S1','0:S1',identity={'name':None,'suggested':'Ali'})
            db.correct(mid,'system:S1','Ali')
            note=db.explain_identity([1.0,0.0],'m',base=0.87)[0]
            self.assertIn('1 onaylı öneri → eşik 0,86',note['person_note'])
            db.close()


class SecondOpinionTests(unittest.TestCase):
    """Council-4 verification pass: undo unwinds only the newest naming; partial chunks are not audio."""
    def test_undo_restores_only_the_second_namings_hidden_samples(self):
        import random
        with tempfile.TemporaryDirectory() as tmp:
            db=Store(Path(tmp)/'db'); mid=db.create_meeting('t')
            rnd=random.Random(11); v=[rnd.uniform(-1,1) for _ in range(8)]
            db.enroll('A',v,'m',10,'manual'); db.add_sample_if_new('A',v,'m',12,f'auto:{mid}:0:S1')
            seg=Segment(0,12,'x','system','system:S1',metrics={'cluster':'0:S1','identity':{'name':'A'}},flags=['cloud_diarization']); seg.embedding=v; seg.embedding_model='m'
            sid=db.add_segment(mid,seg); db.db.execute('UPDATE segments SET speaker_name=? WHERE id=?',('A',sid)); db.db.commit()
            db.enroll_speaker(mid,'system:S1','B')      # hides A's auto sample, rejects A
            db.enroll_speaker(mid,'system:S1','C')      # rejects B (its cluster sample hidden)
            db.undo_correction(mid)                     # back to B
            by={p['name']:p['samples'] for p in db.profiles()}
            self.assertEqual(by.get('B'),1); self.assertNotIn('C',by)
            self.assertEqual(by.get('A'),1)             # A's auto sample stays hidden: the first naming still stands
            self.assertEqual(db.segments(mid)[0]['speaker_name'],'B')
            db.close()
    def test_partial_chunk_is_not_audio(self):
        from meeting_os.desktop import has_audio
        with tempfile.TemporaryDirectory() as tmp:
            d=Path(tmp); (d/'system-000000.partial.wav').write_bytes(b'x')
            self.assertFalse(has_audio({'capture_dir':str(d)}))
            (d/'system-000000.wav').write_bytes(b'x'); self.assertTrue(has_audio({'capture_dir':str(d)}))


class PrivacySweepTests(unittest.TestCase):
    def test_deleting_a_meeting_removes_its_retry_workspace(self):
        with tempfile.TemporaryDirectory() as tmp:
            db=Store(Path(tmp)/'db'); mid=db.create_meeting('t')
            db.db.executescript('''CREATE TABLE IF NOT EXISTS retry_attempts(id TEXT PRIMARY KEY, meeting TEXT, owner TEXT, state TEXT);
                CREATE TABLE IF NOT EXISTS retry_workspaces(attempt TEXT PRIMARY KEY REFERENCES retry_attempts(id), root TEXT, name TEXT, device INTEGER, inode INTEGER);''')
            attempt='a'*32; ws=Path(tmp)/('meeting-os-retry-'+attempt); ws.mkdir(); (ws/'mic-full.wav').write_bytes(b'x'*10)
            db.db.execute('INSERT INTO retry_attempts VALUES(?,?,?,?)',(attempt,mid,'{}','interrupted'))
            db.db.execute('INSERT INTO retry_workspaces VALUES(?,?,?,?,?)',(attempt,str(Path(tmp)),ws.name,0,0)); db.db.commit()
            db.delete_meeting(mid)
            self.assertFalse(ws.exists())   # the temp audio goes with the meeting
            db.close()
