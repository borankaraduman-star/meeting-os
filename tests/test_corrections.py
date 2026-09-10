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
            attempt='a'*32; ws=Path(tmp)/('meeting-os-retry-'+attempt); ws.mkdir(mode=0o700); (ws/'mic-full.wav').write_bytes(b'x'*10)
            info=ws.stat()
            db.db.execute('INSERT INTO retry_attempts VALUES(?,?,?,?)',(attempt,mid,'{}','interrupted'))
            db.db.execute('INSERT INTO retry_workspaces VALUES(?,?,?,?,?)',(attempt,str(Path(tmp).resolve()),ws.name,info.st_dev,info.st_ino)); db.db.commit()
            meta=db.delete_meeting(mid)
            self.assertFalse(ws.exists())   # the temp audio goes with the meeting, through the hardened remover
            self.assertEqual(meta['retry_workspaces']['kept'],[])
            # a workspace whose identity changed is refused, not force-deleted, and the refusal is reported
            mid2=db.create_meeting('u'); a2='b'*32; ws2=Path(tmp)/('meeting-os-retry-'+a2); ws2.mkdir(mode=0o700)
            db.db.execute('INSERT INTO retry_attempts VALUES(?,?,?,?)',(a2,mid2,'{}','interrupted'))
            db.db.execute('INSERT INTO retry_workspaces VALUES(?,?,?,?,?)',(a2,str(Path(tmp).resolve()),ws2.name,0,0)); db.db.commit()
            meta2=db.delete_meeting(mid2)
            self.assertTrue(ws2.exists()); self.assertEqual(len(meta2['retry_workspaces']['kept']),1)
            db.close()


class RenameHistoryTests(unittest.TestCase):
    """A cluster the user names more than once. Every naming must take back only what it replaces: the verdicts
    this same cluster filed earlier, the sample this same naming stored, the evidence it produced once."""
    def _voice(self, seed):
        import random
        rnd=random.Random(seed); return [rnd.uniform(-1,1) for _ in range(8)]
    def _cluster(self, db, mid, vector, speaker='system:S1', name=None, suggested=None, cluster='0:S1'):
        seg=Segment(0,12,'uzun bir konuşma','system',speaker,metrics={'cluster':cluster,'identity':{'name':name,'suggested':suggested}},flags=['cloud_diarization'])
        seg.embedding=vector; seg.embedding_model='m'
        sid=db.add_segment(mid,seg)
        if name: db.db.execute('UPDATE segments SET speaker_name=? WHERE id=?',(name,sid)); db.db.commit()
        return sid
    def test_renaming_back_to_the_first_person_lifts_that_clusters_own_veto(self):
        """Ali → Veli → Ali. The veto the middle naming filed is this cluster's own verdict about Ali, so naming
        the cluster Ali again has to cancel it: a rejection outranks any score, and Ali never came back."""
        with tempfile.TemporaryDirectory() as tmp:
            db=Store(Path(tmp)/'db'); mid=db.create_meeting('t')
            ali=self._voice(21); db.enroll('Ali',ali,'m',10,'manual')
            db.add_sample_if_new('Ali',ali,'m',12,f'auto:{mid}:0:S1')
            self._cluster(db,mid,ali,name='Ali')
            db.enroll_speaker(mid,'system:S1','Veli')
            self.assertEqual(db.identify(ali,'m',threshold=0.5,margin=0.0)['name'],'Veli')
            self.assertEqual(db.db.execute("SELECT count(*) FROM rejections WHERE name='Ali'").fetchone()[0],1)
            db.enroll_speaker(mid,'system:S1','Ali')
            self.assertEqual(db.db.execute("SELECT count(*) FROM rejections WHERE name='Ali'").fetchone()[0],0)
            self.assertEqual(db.identify(ali,'m',threshold=0.5,margin=0.0)['name'],'Ali')
            self.assertEqual({p['name']:p['samples'] for p in db.profiles()}['Ali'],3)   # manual + the un-hidden auto one + the cluster
            db.close()
    def test_a_speaker_label_is_matched_whole_not_as_a_prefix(self):
        """The rejection dedupe asked for provenance LIKE "…:speaker:S1%", which "…:speaker:S10@<time>" answers.
        Naming S1 after S10 therefore filed no veto of its own and the wrong person stayed matchable."""
        with tempfile.TemporaryDirectory() as tmp:
            db=Store(Path(tmp)/'db'); mid=db.create_meeting('t')
            first=self._voice(22); second=self._voice(23)
            db.enroll('Ali',first,'m',10,'manual')
            self._cluster(db,mid,second,speaker='S10',name='Ali',cluster='0:S10')   # the model called both clusters Ali
            self._cluster(db,mid,first,speaker='S1',name='Ali',cluster='0:S1')
            db.enroll_speaker(mid,'S10','Deniz')
            db.enroll_speaker(mid,'S1','Veli')
            self.assertEqual(db.db.execute("SELECT count(*) FROM rejections WHERE name='Ali'").fetchone()[0],2)
            self.assertNotEqual(db.identify(first,'m',threshold=0.5,margin=0.0)['name'],'Ali')
            db.close()
    def test_a_wildcard_in_a_speaker_label_stays_literal(self):
        self.assertEqual(Store._mark_patterns('abc','%_x'),('abc:speaker:\\%\\_x@%','abc:speaker:%_x'))
    def test_undo_deletes_only_the_sample_this_naming_stored(self):
        """enroll_speaker skips the insert when the slot is already filled, but undo deleted by (name,
        provenance) regardless — so undoing the second naming destroyed the first naming's sample."""
        with tempfile.TemporaryDirectory() as tmp:
            db=Store(Path(tmp)/'db'); mid=db.create_meeting('t')
            self._cluster(db,mid,self._voice(24))
            db.enroll_speaker(mid,'system:S1','Ayşe')
            first=db.db.execute("SELECT id FROM samples WHERE name='Ayşe'").fetchone()[0]
            again=db.enroll_speaker(mid,'system:S1','Ayşe')   # the same person again: the slot is filled, no new sample
            self.assertFalse(again['profile_saved'])
            self.assertIsNone(json.loads(db.db.execute('SELECT feedback FROM corrections ORDER BY id DESC LIMIT 1').fetchone()[0])['sample_id'])
            db.undo_correction(mid)
            self.assertEqual([r[0] for r in db.db.execute('SELECT id FROM samples WHERE deleted_by IS NULL')],[first])
            self.assertEqual(db.segments(mid)[0]['speaker_name'],'Ayşe')
            db.close()
    def test_one_automatic_mistake_is_convicted_once_however_often_the_user_renames(self):
        with tempfile.TemporaryDirectory() as tmp:
            db=Store(Path(tmp)/'db'); mid=db.create_meeting('t')
            veli=self._voice(25); db.enroll('Veli',veli,'m',10,'manual')
            self._cluster(db,mid,veli,name='Veli')
            for typed in ('Kaya','Deniz','Ece'): db.correct(mid,'system:S1',typed)
            self.assertEqual(db.db.execute("SELECT wrong FROM profile_stats WHERE name='Veli'").fetchone()[0],1)
            self.assertAlmostEqual(db.person_threshold('Veli',0.87),0.89)   # one mistake, not three
            identity=db.segments(mid)[0]['metrics']['identity']
            self.assertEqual((identity['settled'],identity['name']),('Ece','Veli'))   # judged once; the guess stays readable for the scorecard
            db.close()
    def test_a_confirmed_suggestion_is_counted_once_too(self):
        with tempfile.TemporaryDirectory() as tmp:
            db=Store(Path(tmp)/'db'); mid=db.create_meeting('t')
            ali=self._voice(26); db.enroll('Ali',ali,'m',10,'manual')
            self._cluster(db,mid,ali,suggested='Ali')
            for _ in range(3): db.correct(mid,'system:S1','Ali')
            self.assertEqual(db.db.execute("SELECT confirmed FROM profile_stats WHERE name='Ali'").fetchone()[0],1)
            db.close()
    def test_undo_restores_a_label_no_rejection_ever_recorded(self):
        """"Ayşe" retyped as "Ayse" is a confirmation, so nothing is rejected and previous_name stayed NULL —
        undo then blanked a label the user had never removed."""
        with tempfile.TemporaryDirectory() as tmp:
            db=Store(Path(tmp)/'db'); mid=db.create_meeting('t')
            self._cluster(db,mid,self._voice(27))
            db.correct(mid,'system:S1','Ayşe')
            db.correct(mid,'system:S1','Ayse')
            self.assertEqual(db.db.execute('SELECT previous_name FROM corrections ORDER BY id DESC LIMIT 1').fetchone()[0],'Ayşe')
            db.undo_correction(mid)
            self.assertEqual(db.segments(mid)[0]['speaker_name'],'Ayşe')
            db.close()



class SegmentOnlyCorrectionTests(unittest.TestCase):
    """Boran, 10 Sep 2026: one piece of a voice went to the wrong person. Fixing that piece must not rename the
    cluster, must not convict anybody, and must teach the profile of the right person."""
    def _voice(self, seed):
        import random
        rnd=random.Random(seed); return [rnd.uniform(-1,1) for _ in range(8)]
    def _meeting(self):
        tmp=tempfile.TemporaryDirectory(); db=Store(Path(tmp.name)/'db'); mid=db.create_meeting('test')
        ids=[db.add_segment(mid,Segment(i*10,i*10+8,f'söz {i}','system','system:S1',metrics={'cluster':'0:S1'},flags=['cloud_diarization'],embedding=self._voice(i),embedding_model='m')) for i in range(3)]
        db.enroll_speaker(mid,'system:S1','Ayşe')
        return tmp,db,mid,ids
    def test_only_that_piece_changes_and_the_right_person_learns(self):
        tmp,db,mid,ids=self._meeting()
        result=db.correct_segment_only(mid,ids[1],'Ali')
        rows={r['id']:r for r in db.segments(mid)}
        self.assertEqual([rows[i]['speaker_name'] for i in ids],['Ayşe','Ali','Ayşe'])
        self.assertTrue(result['profile_saved']); self.assertEqual(result['previous'],'Ayşe')
        self.assertEqual([s['provenance'] for s in db.profile_samples('Ali')],[f'{mid}:{ids[1]}'])
        self.assertEqual(db.db.execute('SELECT count(*) FROM rejections').fetchone()[0],0)   # the cluster as a whole was right
        self.assertEqual(len(db.profile_samples('Ayşe')),1)   # Ayşe keeps her cluster sample
        db.close(); tmp.cleanup()
    def test_short_or_unclean_piece_gets_only_the_label(self):
        tmp,db,mid,ids=self._meeting()
        short=db.add_segment(mid,Segment(40,43,'kısa','system','system:S1',metrics={'cluster':'0:S1'},flags=['cloud_diarization'],embedding=self._voice(9),embedding_model='m'))
        result=db.correct_segment_only(mid,short,'Ali')
        self.assertFalse(result['profile_saved']); self.assertEqual(db.profile_samples('Ali'),[])
        self.assertEqual({r['id']:r['speaker_name'] for r in db.segments(mid)}[short],'Ali')
        db.close(); tmp.cleanup()
    def test_later_cluster_naming_skips_the_pinned_piece(self):
        tmp,db,mid,ids=self._meeting()
        db.correct_segment_only(mid,ids[1],'Ali')
        db.correct(mid,'system:S1','Ayşe Yılmaz')
        rows={r['id']:r for r in db.segments(mid)}
        self.assertEqual([rows[i]['speaker_name'] for i in ids],['Ayşe Yılmaz','Ali','Ayşe Yılmaz'])
        db.undo_correction(mid)
        rows={r['id']:r for r in db.segments(mid)}
        self.assertEqual([rows[i]['speaker_name'] for i in ids],['Ayşe','Ali','Ayşe'])
        db.close(); tmp.cleanup()
    def test_cluster_naming_after_a_pin_convicts_nobody_and_undo_keeps_the_pin(self):
        tmp,db,mid,ids=self._meeting()
        db.correct_segment_only(mid,ids[1],'Ali')
        db.correct(mid,'system:S1','Ayşe Yılmaz')
        self.assertEqual(db.db.execute("SELECT count(*) FROM rejections WHERE name='Ali'").fetchone()[0],0)
        self.assertEqual(db.db.execute("SELECT previous_name FROM corrections WHERE speaker='system:S1' ORDER BY id DESC LIMIT 1").fetchone()[0],'Ayşe')
        db.undo_correction(mid)   # undoes the cluster naming, not the pin
        rows={r['id']:r for r in db.segments(mid)}
        self.assertEqual([rows[i]['speaker_name'] for i in ids],['Ayşe','Ali','Ayşe'])
        db.undo_correction(mid)   # now the pin itself
        rows={r['id']:r for r in db.segments(mid)}
        self.assertEqual([rows[i]['speaker_name'] for i in ids],['Ayşe','Ayşe','Ayşe'])
        self.assertEqual(db.profile_samples('Ali'),[])
        db.close(); tmp.cleanup()
    def test_pin_does_not_block_automatic_identification_of_the_rest(self):
        tmp=tempfile.TemporaryDirectory(); db=Store(Path(tmp.name)/'db'); mid=db.create_meeting('test')
        voice=self._voice(1)
        db.enroll('Kerem',voice,'m',20)
        other=self._voice(7)   # the mis-assigned piece really is another voice
        ids=[db.add_segment(mid,Segment(i*10,i*10+8,f'söz {i}','system','system:S1',metrics={'cluster':'0:S1'},flags=['cloud_diarization'],embedding=(other if i==0 else voice),embedding_model='m')) for i in range(3)]
        db.correct_segment_only(mid,ids[0],'Ali')
        db.resuggest(mid)
        rows={r['id']:r for r in db.segments(mid)}
        self.assertEqual([rows[i]['speaker_name'] for i in ids],['Ali','Kerem','Kerem'])
        db.close(); tmp.cleanup()
    def test_enroll_segment_does_not_pin(self):
        tmp,db,mid,ids=self._meeting()
        db.enroll_segment(mid,ids[0],'Ayşe')
        db.correct(mid,'system:S1','Ayşe Yılmaz')
        self.assertEqual({r['speaker_name'] for r in db.segments(mid)},{'Ayşe Yılmaz'})
        db.close(); tmp.cleanup()


class TaskOwnerRenameTests(unittest.TestCase):
    """A rename used to relabel the transcript only: the tasks kept a name that no longer appeared anywhere in
    the meeting, so "Bana ait" and the waiting board answered with a person who no longer existed."""
    def _task(self, db, mid, tid, owner, *, user_edited=0, segments=(1,)):
        from meeting_os.memory import Memory
        Memory(db)   # creates the tasks table on this connection
        payload = json.dumps({'evidence': [{'segment_id': s, 'quote': 'q'} for s in segments]})
        with db.db:
            db.db.execute("INSERT INTO tasks(id,meeting,analysis,input_hash,title,owner,due_text,state,payload,user_edited,created,updated)"
                          " VALUES(?,?,NULL,'h','İş',?,NULL,'open',?,?,'2026-09-09T10:00:00+00:00','2026-09-09T10:00:00+00:00')",
                          (tid, mid, owner, payload, user_edited))

    def _owners(self, db):
        return {r[0]: r[1] for r in db.db.execute('SELECT id,owner FROM tasks')}

    def test_a_cluster_rename_moves_the_tasks_of_that_meeting_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Store(Path(tmp) / 'db'); mid = db.create_meeting('t'); other = db.create_meeting('başka')
            db.add_segment(mid, Segment(0, 12, 'uzun konuşma', 'system', 'system:S1', metrics={'cluster': '0:S1'}, flags=['cloud_diarization']))
            db.correct(mid, 'system:S1', 'Ayşe')
            self._task(db, mid, 'here', 'ayşe'); self._task(db, mid, 'edited', 'Ayşe', user_edited=1); self._task(db, other, 'elsewhere', 'Ayşe')
            db.correct(mid, 'system:S1', 'Ali')
            self.assertEqual(self._owners(db), {'here': 'Ali', 'edited': 'Ayşe', 'elsewhere': 'Ayşe'})
            db.close()

    def test_renaming_the_mic_owner_moves_their_tasks_in_every_meeting(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Store(Path(tmp) / 'db'); a = db.create_meeting('a'); b = db.create_meeting('b')
            for mid in (a, b): db.add_segment(mid, Segment(0, 5, 'ben yaparım', 'mic', 'Ben'))
            self._task(db, a, 'ta', 'Ben'); self._task(db, b, 'tb', 'ben'); self._task(db, b, 'other', 'İpek')
            result = db.rename_mic_owner('Ben', 'Boran')
            self.assertEqual((result['segments'], result['tasks']), (2, 2))
            self.assertEqual(self._owners(db), {'ta': 'Boran', 'tb': 'Boran', 'other': 'İpek'})
            db.close()

    def test_a_pinned_piece_moves_only_the_task_whose_evidence_is_that_piece(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Store(Path(tmp) / 'db'); mid = db.create_meeting('t')
            ids = [db.add_segment(mid, Segment(i * 10, i * 10 + 8, f'söz {i}', 'system', 'system:S1', metrics={'cluster': '0:S1'}, flags=['cloud_diarization'])) for i in range(2)]
            db.correct(mid, 'system:S1', 'Ayşe')
            self._task(db, mid, 'pinned', 'Ayşe', segments=(ids[1],)); self._task(db, mid, 'wider', 'Ayşe', segments=ids)
            db.correct_segment_only(mid, ids[1], 'Ali')
            self.assertEqual(self._owners(db), {'pinned': 'Ali', 'wider': 'Ayşe'})
            db.close()

    def test_a_sample_whose_meeting_was_deleted_says_so(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Store(Path(tmp) / 'db'); mid = db.create_meeting('Silinecek')
            db.enroll('Ali', [1.0, 0.0], 'm', 12, f'{mid}:speaker:system:S1'); db.enroll('Ali', [0.0, 1.0], 'm', 12, 'manual')
            self.assertEqual([s['meeting_title'] for s in db.profile_samples('Ali')], ['Silinecek', None])
            db.delete_meeting(mid)
            sample = db.profile_samples('Ali')[0]
            self.assertEqual((sample['meeting_title'], sample['meeting']), ('toplantı silindi', None))
            db.close()


class OwnerFollowsUndoTests(unittest.TestCase):
    """Second opinion on 1.2.47: a rename+undo must not strand tasks on a name nobody said."""
    def _voice(self, seed):
        import random
        rnd=random.Random(seed); return [rnd.uniform(-1,1) for _ in range(8)]
    def _db(self):
        tmp=tempfile.TemporaryDirectory(); db=Store(Path(tmp.name)/'db'); mid=db.create_meeting('test')
        sid=db.add_segment(mid,Segment(0,12,'raporu ben göndereceğim','system','system:S1',metrics={'cluster':'0:S1'},flags=['cloud_diarization'],embedding=self._voice(1),embedding_model='m'))
        from meeting_os.memory import Memory
        mem=Memory(db)
        mem.save_analysis(mid,mem.current_hash(mid),'m',{'summary':[],'decisions':[],'risks':[],'questions':[],'actions':[{'title':'Raporu gönder','owner':'Konuşmacı 2','due_text':None,'evidence':[{'segment_id':sid,'quote':'raporu ben göndereceğim','start':0,'speaker':'Konuşmacı 2'}]}]})
        db.db.execute("UPDATE tasks SET owner='Konuşmacı 2'"); db.db.commit()
        return tmp,db,mid,sid,mem
    def _owner(self,db): return db.db.execute('SELECT owner FROM tasks').fetchone()[0]
    def test_undo_moves_the_owner_back_and_redo_moves_it_again(self):
        tmp,db,mid,sid,mem=self._db()
        db.correct(mid,'system:S1','Ayşe'); db.db.execute("UPDATE tasks SET owner='Ayşe'"); db.db.commit()   # named, then re-analysed: the task is Ayşe's
        db.correct(mid,'system:S1','Zeynep'); self.assertEqual(self._owner(db),'Zeynep')
        db.undo_correction(mid); self.assertEqual(self._owner(db),'Ayşe')
        db.correct(mid,'system:S1','Zeynep'); self.assertEqual(self._owner(db),'Zeynep')
        db.close(); tmp.cleanup()
    def test_an_empty_re_analysis_does_not_retire_open_tasks(self):
        tmp,db,mid,sid,mem=self._db()
        mem.save_analysis(mid,mem.current_hash(mid),'m',{'summary':[],'decisions':[],'risks':[],'questions':[],'actions':[]})
        self.assertEqual(db.db.execute("SELECT state FROM tasks").fetchone()[0],'open')
        mem.save_analysis(mid,mem.current_hash(mid),'m',{'summary':[],'decisions':[],'risks':[],'questions':[],'actions':[{'title':'Raporu yolla','owner':None,'due_text':None,'evidence':[{'segment_id':sid,'quote':'raporu ben göndereceğim','start':0,'speaker':'S1'}]}]})
        states=sorted(r[0] for r in db.db.execute("SELECT state FROM tasks"))
        self.assertEqual(states,['open','superseded'])
        db.close(); tmp.cleanup()
    def test_marking_done_is_not_an_edit(self):
        tmp,db,mid,sid,mem=self._db()
        tid=db.db.execute('SELECT id FROM tasks').fetchone()[0]
        mem.update_action(tid,{'state':'done'})
        self.assertEqual(db.db.execute('SELECT user_edited FROM tasks').fetchone()[0],0)
        mem.update_action(tid,{'title':'Raporu gönder (yarın)'})
        self.assertEqual(db.db.execute('SELECT user_edited FROM tasks').fetchone()[0],1)
        db.close(); tmp.cleanup()
    def test_mic_owner_rename_moves_only_relabelled_meetings(self):
        tmp=tempfile.TemporaryDirectory(); db=Store(Path(tmp.name)/'db')
        a=db.create_meeting('A'); b=db.create_meeting('B')
        db.add_segment(a,Segment(0,5,'ben yaparım','mic','Ali'))
        sid=db.add_segment(b,Segment(0,5,'ben yaparım','system','system:S1',speaker_name='Ali'))
        from meeting_os.memory import Memory
        mem=Memory(db)
        for mid,seg in ((a,None),(b,sid)):
            mem.save_analysis(mid,mem.current_hash(mid),'m',{'summary':[],'decisions':[],'risks':[],'questions':[],'actions':[{'title':'İş','owner':'Ali','due_text':None,'evidence':[{'segment_id':seg or 1,'quote':'ben yaparım','start':0,'speaker':'Ali'}]}]})
        r=db.rename_mic_owner('Ali','Ali Yılmaz')
        owners={row[0]:row[1] for row in db.db.execute('SELECT meeting,owner FROM tasks')}
        self.assertEqual((owners[a],owners[b],r['tasks']),('Ali Yılmaz','Ali',1))
        db.close(); tmp.cleanup()
