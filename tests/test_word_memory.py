"""Teach a word once. One correction becomes a rule for that exact spelling, near-misses are offered in
Kontrol instead of being rewritten behind the user's back, and every part of it is reversible."""
import json
import tempfile
import unittest
from pathlib import Path
from meeting_os.store import Store
from meeting_os.types import Segment
from meeting_os import correction_memory as cm
from meeting_os.desktop import dispatch
from meeting_os.review import review_queue


class WordMemoryTests(unittest.TestCase):
    def _fixture(self, tmp, vocabulary='Trendyol\n'):
        data = Path(tmp)
        (data / 'vocabulary.txt').write_text(vocabulary, encoding='utf-8')   # a fixed list; the repo seed is never copied
        db = Store(data / 'meeting-os.sqlite')
        return data, db

    def _segment(self, db, mid, text, start=0.0):
        return db.add_segment(mid, Segment(start, start + 4, text, 'system', 'system:S1'))

    def test_teaching_a_word_fixes_every_occurrence_and_keeps_the_case(self):
        with tempfile.TemporaryDirectory() as tmp:
            data, db = self._fixture(tmp, 'Jira\n')
            mid = db.create_meeting('a')
            first = self._segment(db, mid, 'Trendyoll ekibi ve trendyoll tarafı, ikisi de Trendyoll.')
            second = self._segment(db, mid, 'Alakasız bir cümle.', 10)
            result = cm.teach(db, mid, 'Trendyoll', 'Trendyol', data)
            self.assertEqual((result['segments'], result['fixes'], result['vocabulary_added']), (1, 3, True))
            self.assertEqual(result['rule']['source'], 'taught')
            rows = {r['id']: r for r in db.segments(mid)}
            self.assertEqual(rows[first]['text'], 'Trendyol ekibi ve Trendyol tarafı, ikisi de Trendyol.')
            self.assertIn('word_corrected', rows[first]['flags'])
            self.assertEqual(rows[first]['original_text'], 'Trendyoll ekibi ve trendyoll tarafı, ikisi de Trendyoll.')
            self.assertEqual(rows[first]['metrics']['word_corrections'][0]['count'], 3)
            self.assertEqual(rows[second]['text'], 'Alakasız bir cümle.')
            self.assertEqual(cm.vocabulary_terms(data), ['Jira', 'Trendyol'])   # the ASR hint list learned it too
            self.assertEqual(cm.teach(db, mid, 'Trendyoll', 'Trendyol', data)['vocabulary_added'], False)   # idempotent
            self.assertEqual(cm.vocabulary_terms(data), ['Jira', 'Trendyol'])
            db.close()

    def test_a_taught_word_fixes_the_exact_spelling_only_and_leaves_the_turkish_suffix_alone(self):
        """A near-miss is a suggestion, never an automatic rewrite; the apostrophe suffix stays where it was."""
        with tempfile.TemporaryDirectory() as tmp:
            data, db = self._fixture(tmp, 'Jira\n')
            teaching = db.create_meeting('öğret'); later = db.create_meeting('sonra')
            self._segment(db, teaching, 'Trendyoll ile görüştük.')
            cm.teach(db, teaching, 'Trendyoll', 'Trendyol', data)
            sid = self._segment(db, later, "Trendyoll'a yazdık, Trendiyol raporu geldi, Trendyol'a değil, Trendyola da değil.")
            db.status(later, 'complete')
            report = cm.apply_rules(db, later, data_dir=data)
            row = next(r for r in db.segments(later) if r['id'] == sid)
            self.assertEqual(row['text'], "Trendyol'a yazdık, Trendiyol raporu geldi, Trendyol'a değil, Trendyola da değil.")
            self.assertEqual((report['segments'], report['fixes']), (1, 1))
            self.assertIn('auto_corrected', row['flags'])
            words = [i for i in review_queue(db, later, data)['items'] if i['kind'] == 'word']
            self.assertEqual([(i['original'], i['replacement']) for i in words], [('Trendiyol', 'Trendyol')])
            self.assertIn('muhtemelen', words[0]['reason'])   # the near-miss is offered, not performed
            db.close()

    def test_a_taught_word_never_rewrites_an_unrelated_turkish_word(self):
        """Measured on the user's own transcripts: "Ayşe → Ayşen" rewrote "Aynen" three times, and
        "eğitimize → eğitimimize" rewrote eighteen tokens. A rule matches the spelling it was taught."""
        with tempfile.TemporaryDirectory() as tmp:
            data, db = self._fixture(tmp, 'Jira\n')
            teaching = db.create_meeting('öğret'); later = db.create_meeting('sonra')
            self._segment(db, teaching, 'Ayşe raporu yolladı.')
            cm.teach(db, teaching, 'Ayşe', 'Ayşen', data)
            self._segment(db, teaching, 'yaşıyoruz burada.', 20)
            cm.teach(db, teaching, 'yaşıyoruz', 'yaşıyorum', data)
            text = 'Aynen, aynen öyle. Ben de yapıyorum, atıyorum, arıyorum, alıyoruz. Ayşe geldi.'
            sid = self._segment(db, later, text)
            db.status(later, 'complete')
            cm.apply_rules(db, later, data_dir=data)
            row = next(r for r in db.segments(later) if r['id'] == sid)
            self.assertEqual(row['text'], 'Aynen, aynen öyle. Ben de yapıyorum, atıyorum, arıyorum, alıyoruz. Ayşen geldi.')
            offered = {i['original'] for i in review_queue(db, later, data)['items'] if i['kind'] == 'word'}
            self.assertIn('Aynen', offered)          # a near-miss is a question in Kontrol, never a rewrite
            self.assertTrue(all(i['reason'].count('muhtemelen') for i in review_queue(db, later, data)['items'] if i['kind'] == 'word'))
            db.close()

    def test_a_taught_original_that_is_also_a_vocabulary_term_keeps_working(self):
        """Teaching a word adds the RIGHT spelling to the vocabulary; if the wrong one is in there too (the
        user put it there, or an earlier version did), the rule stopped firing from the second meeting on."""
        with tempfile.TemporaryDirectory() as tmp:
            data, db = self._fixture(tmp, 'Spilendo\n')
            teaching = db.create_meeting('öğret'); later = db.create_meeting('sonra')
            self._segment(db, teaching, 'Spilendo demosu.')
            cm.teach(db, teaching, 'Spilendo', 'Splendo', data)
            sid = self._segment(db, later, 'Spilendo yine gündemde.')
            cm.apply_rules(db, later, data_dir=data)
            self.assertEqual(next(r for r in db.segments(later) if r['id'] == sid)['text'], 'Splendo yine gündemde.')
            db.close()

    def test_teaching_the_same_rule_three_times_grows_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            data, db = self._fixture(tmp, 'Jira\n')
            mid = db.create_meeting('a')
            sid = self._segment(db, mid, 'Bunu kanal üzerinden konuşalım.')
            for _ in range(3): cm.teach(db, mid, 'kanal', 'kanal ekibi', data)
            row = next(r for r in db.segments(mid) if r['id'] == sid)
            self.assertEqual(row['text'], 'Bunu kanal ekibi üzerinden konuşalım.')
            self.assertEqual(len(row['metrics']['word_corrections']), 1)
            cm.apply_rules(db, mid, data_dir=data)   # the finalize pass must not grow it either
            self.assertEqual(next(r for r in db.segments(mid) if r['id'] == sid)['text'], 'Bunu kanal ekibi üzerinden konuşalım.')
            db.close()

    def test_a_word_another_rule_produces_or_the_vocabulary_holds_is_never_rewritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            data, db = self._fixture(tmp, 'Splenda\nrefinement\n')
            mid = db.create_meeting('a')
            self._segment(db, mid, 'Splendoo raporu')
            cm.teach(db, mid, 'Splendoo', 'Splendo', data)
            later = db.create_meeting('b')
            sid = self._segment(db, later, 'Splenda ekibi ve refinement toplantısı ve Splendoo notu')
            cm.apply_rules(db, later, data_dir=data)
            row = next(r for r in db.segments(later) if r['id'] == sid)
            self.assertEqual(row['text'], 'Splenda ekibi ve refinement toplantısı ve Splendo notu')
            db.close()

    def test_forget_puts_the_sentences_back_and_takes_the_vocabulary_line_out(self):
        with tempfile.TemporaryDirectory() as tmp:
            data, db = self._fixture(tmp, 'Jira\n')
            mid = db.create_meeting('a')
            sid = self._segment(db, mid, 'Spilendo demosu yarın.')
            cm.teach(db, mid, 'Spilendo', 'Splendo', data)
            self.assertEqual(next(r for r in db.segments(mid) if r['id'] == sid)['text'], 'Splendo demosu yarın.')
            result = cm.forget(db, 'spilendo', data)
            self.assertEqual((result['forgotten'], result['meetings'], result['segments'], result['vocabulary_removed']), (True, 1, 1, True))
            row = next(r for r in db.segments(mid) if r['id'] == sid)
            self.assertEqual(row['text'], 'Spilendo demosu yarın.')
            self.assertNotIn('word_corrected', row['flags'])
            self.assertIsNone(row.get('original_text'))    # teaching set it; forgetting takes it back
            self.assertEqual(cm.vocabulary_terms(data), ['Jira'])
            self.assertEqual(cm.word_rules(db), [])
            self.assertEqual(cm.forget(db, 'spilendo', data)['forgotten'], False)   # idempotent
            db.close()

    def test_forget_leaves_a_segment_the_user_edited_after_the_fix(self):
        """Forgetting a word put back the sentence as it was BEFORE the fix — throwing away whatever the user
        had typed over it since. That segment is left alone and counted instead."""
        with tempfile.TemporaryDirectory() as tmp:
            data, db = self._fixture(tmp, 'Jira\n')
            mid = db.create_meeting('a')
            kept = self._segment(db, mid, 'Spilendo demosu yarın.')
            plain = self._segment(db, mid, 'Spilendo raporu geldi.', 10)
            cm.teach(db, mid, 'Spilendo', 'Splendo', data)
            db.correct_text(mid, kept, 'Splendo demosu bugün.')   # a manual edit made after the word was taught
            result = cm.forget(db, 'Spilendo', data)
            self.assertEqual((result['segments'], result['kept']), (1, 1))
            rows = {r['id']: r for r in db.segments(mid)}
            self.assertEqual(rows[kept]['text'], 'Splendo demosu bugün.')      # the user's sentence survives
            self.assertEqual(rows[plain]['text'], 'Spilendo raporu geldi.')    # the untouched one is put back
            db.close()

    def test_forget_keeps_a_manual_edit_made_before_the_word_was_taught(self):
        with tempfile.TemporaryDirectory() as tmp:
            data, db = self._fixture(tmp, 'Jira\n')
            mid = db.create_meeting('a')
            sid = self._segment(db, mid, 'Spilendo demosu yarin.')
            db.correct_text(mid, sid, 'Spilendo demosu yarın.')
            cm.teach(db, mid, 'Spilendo', 'Splendo', data)
            cm.forget(db, 'Spilendo', data)
            row = next(r for r in db.segments(mid) if r['id'] == sid)
            self.assertEqual(row['text'], 'Spilendo demosu yarın.')
            self.assertEqual(row['original_text'], 'Spilendo demosu yarin.')   # the user's own edit history survives
            db.close()

    def test_kontrol_shows_an_untaught_near_miss_and_stops_after_dismiss_or_correction(self):
        with tempfile.TemporaryDirectory() as tmp:
            data, db = self._fixture(tmp, 'Trendyol\n')
            mid = db.create_meeting('a')
            sid = self._segment(db, mid, 'Trendiyol raporu bugün geldi, Trendyol tarafı bekliyor.')
            db.status(mid, 'complete')
            items = [i for i in review_queue(db, mid, data)['items'] if i['kind'] == 'word']
            self.assertEqual([(i['original'], i['replacement'], i['segment_id'], i['count'], i['severity']) for i in items],
                             [('Trendiyol', 'Trendyol', sid, 1, 2)])
            self.assertIn('sözlük terimi', items[0]['reason'])
            cm.dismiss_word(db, mid, 'Trendiyol')
            self.assertEqual([i for i in review_queue(db, mid, data)['items'] if i['kind'] == 'word'], [])
            other = db.create_meeting('b')
            second = self._segment(db, other, 'Trendiyol raporu, Trendyoll notu.')
            db.status(other, 'complete')
            # "Bu doğru" holds everywhere: the same word was asked about again in every new meeting.
            self.assertEqual([i['original'] for i in review_queue(db, other, data)['items'] if i['kind'] == 'word'], ['Trendyoll'])
            cm.teach(db, other, 'Trendyoll', 'Trendyol', data)
            self.assertEqual([i for i in review_queue(db, other, data)['items'] if i['kind'] == 'word'], [])
            self.assertEqual(next(r for r in db.segments(other) if r['id'] == second)['text'], 'Trendiyol raporu, Trendyol notu.')
            db.close()

    def test_kontrol_does_not_flag_ordinary_turkish_words(self):
        with tempfile.TemporaryDirectory() as tmp:
            data, db = self._fixture(tmp, 'Trendyol\nkontrol\n')
            mid = db.create_meeting('a')
            self._segment(db, mid, 'Kontrolü yaptık, karar sonra gelecek.')
            db.status(mid, 'complete')
            self.assertEqual([i for i in review_queue(db, mid, data)['items'] if i['kind'] == 'word'], [])
            db.close()

    def test_a_short_vocabulary_term_is_not_a_suggestion(self):
        """Five letters is one letter from half of Turkish; the vocabulary side of Kontrol starts at six."""
        with tempfile.TemporaryDirectory() as tmp:
            data, db = self._fixture(tmp, 'Kanal\nRefinement\n')
            mid = db.create_meeting('a')
            self._segment(db, mid, 'Kanat raporu ve refinemant notu.')
            db.status(mid, 'complete')
            items = [i for i in review_queue(db, mid, data)['items'] if i['kind'] == 'word']
            self.assertEqual([(i['original'], i['replacement']) for i in items], [('refinemant', 'Refinement')])
            db.close()

    def test_bridge_actions_teach_list_dismiss_and_forget(self):
        with tempfile.TemporaryDirectory() as tmp:
            data, db = self._fixture(tmp, 'Jira\n')
            mid = db.create_meeting('a')
            sid = self._segment(db, mid, "Trendyoll'a bir mail attık.")
            db.status(mid, 'complete'); db.close()
            path = data / 'meeting-os.sqlite'
            taught = dispatch({'action': 'learn_word', 'meeting': mid, 'original': 'Trendyoll', 'replacement': 'Trendyol'}, path)
            self.assertEqual((taught['segments'], taught['fixes'], taught['vocabulary_added']), (1, 1, True))
            rules = dispatch({'action': 'word_rules'}, path)['rules']
            self.assertEqual([(r['original'], r['replacement'], r['source'], r['count'], r['meetings'], r['vocabulary_added']) for r in rules],
                             [('Trendyoll', 'Trendyol', 'taught', 1, 1, True)])
            self.assertTrue(rules[0]['created'])
            self.assertEqual(dispatch({'action': 'word_dismiss', 'meeting': mid, 'original': 'Trendiyol'}, path)['dismissed'], True)
            self.assertEqual(dispatch({'action': 'correction_rules'}, path)['rules'], [])   # the learned-rule screen is untouched
            again = dispatch({'action': 'word_apply', 'meeting': mid, 'original': 'Trendyoll', 'replacement': 'Trendyol'}, path)
            self.assertEqual(again['rule']['count'], 2)
            forgotten = dispatch({'action': 'forget_word', 'original': 'Trendyoll'}, path)
            self.assertEqual((forgotten['forgotten'], forgotten['meetings'], forgotten['segments']), (True, 1, 1))
            store = Store(path)
            self.assertEqual(next(r for r in store.segments(mid) if r['id'] == sid)['text'], "Trendyoll'a bir mail attık.")
            self.assertEqual(cm.word_rules(store), [])
            store.close()


if __name__ == '__main__':
    unittest.main()


class ShortClusterTests(unittest.TestCase):
    def test_a_two_second_cluster_is_not_offered_for_naming(self):
        import tempfile
        from pathlib import Path
        from meeting_os.store import Store
        from meeting_os.types import Segment
        from meeting_os.review import review_queue
        with tempfile.TemporaryDirectory() as tmp:
            db=Store(Path(tmp)/'db'); mid=db.create_meeting('t')
            db.add_segment(mid,Segment(0,12,'uzun bir konuşma burada','system','system:S1',metrics={'cluster':'0:S1'},flags=['cloud_diarization']))
            db.add_segment(mid,Segment(20,21.5,'hı','system','system:S14',metrics={'cluster':'0:S14'},flags=['cloud_diarization']))
            q=review_queue(db,mid,tmp); items=q['items'] if isinstance(q,dict) else q
            kinds={(i['kind'],i.get('speaker_key')) for i in items}
            self.assertIn(('unnamed_speaker','system:S1'),kinds); self.assertNotIn(('unnamed_speaker','system:S14'),kinds)
            db.close()


class ApostropheTeachTests(unittest.TestCase):
    def test_teaching_an_inflected_word_learns_the_stem_and_fixes_the_token(self):
        import tempfile
        from pathlib import Path
        from meeting_os.store import Store
        from meeting_os.types import Segment
        from meeting_os import correction_memory as CM
        with tempfile.TemporaryDirectory() as tmp:
            db=Store(Path(tmp)/'db'); mid=db.create_meeting('t')
            sid=db.add_segment(mid,Segment(0,5,"Sonra Trendyoll'a gittik, Trendyoll güzel.",'system','S1',flags=['cloud_transcript']))
            r=CM.teach(db,mid,"Trendyoll'a","Trendyol'a",tmp)
            self.assertEqual(r['rule']['original'].lower(),'trendyoll')
            text=[x for x in db.segments(mid) if x['id']==sid][0]['text']
            self.assertEqual(text,"Sonra Trendyol'a gittik, Trendyol güzel.")
            db.close()
    def test_case_only_fix_is_a_real_correction(self):
        import tempfile
        from pathlib import Path
        from meeting_os.store import Store
        from meeting_os.types import Segment
        from meeting_os import correction_memory as CM
        with tempfile.TemporaryDirectory() as tmp:
            db=Store(Path(tmp)/'db'); mid=db.create_meeting('t')
            sid=db.add_segment(mid,Segment(0,5,"istanbul toplantısı",'system','S1',flags=['cloud_transcript']))
            CM.teach(db,mid,"istanbul","İstanbul",tmp)
            self.assertEqual([x for x in db.segments(mid) if x['id']==sid][0]['text'],"İstanbul toplantısı")
            db.close()


class GlossaryAcceptLearnsTests(unittest.TestCase):
    def _db(self):
        import tempfile
        from pathlib import Path
        from meeting_os.store import Store
        from meeting_os.types import Segment
        tmp=tempfile.TemporaryDirectory(); db=Store(Path(tmp.name)/'db'); mid=db.create_meeting('t')
        a=db.add_segment(mid,Segment(0,5,'AB Testi sonuçları geldi.','system','S1',flags=['cloud_transcript']))
        b=db.add_segment(mid,Segment(6,9,'AB Testi bitince konuşuruz.','system','S1',flags=['cloud_transcript']))
        import json
        db.db.execute("UPDATE meetings SET metadata=? WHERE id=?",(json.dumps({'glossary_suggestions':[{'segment_id':a,'original':'AB Testi','replacement':'A/B Test','source':'llm'},{'segment_id':b,'original':'AB Testi','replacement':'A/B Test','source':'llm'}]}),mid)); db.db.commit()
        return tmp,db,mid,a,b
    def test_accepting_a_glossary_proposal_fixes_every_occurrence_and_stops_asking(self):
        from meeting_os import glossary as G
        from meeting_os.review import review_queue
        tmp,db,mid,a,b=self._db()
        r=G.apply_suggestion(db,mid,a,'AB Testi','A/B Test',tmp.name)
        texts=[x['text'] for x in db.segments(mid)]
        self.assertEqual(texts,['A/B Test sonuçları geldi.','A/B Test bitince konuşuruz.'])
        self.assertTrue(r['learned']); self.assertEqual(r['remaining'],0)
        # a new meeting with the same wording is fixed at finalize, not asked about
        from meeting_os.types import Segment
        from meeting_os.correction_memory import apply_rules
        m2=db.create_meeting('u'); db.add_segment(m2,Segment(0,5,'Yeni AB Testi planı.','system','S1',flags=['cloud_transcript']))
        apply_rules(db,m2,data_dir=tmp.name)
        self.assertEqual([x['text'] for x in db.segments(m2)],['Yeni A/B Test planı.'])
        q=review_queue(db,m2,tmp.name); items=q['items'] if isinstance(q,dict) else q
        self.assertFalse([i for i in items if i['kind']=='glossary'])
        db.close(); tmp.cleanup()
    def test_dismissing_a_glossary_proposal_is_global(self):
        from meeting_os import glossary as G
        from meeting_os.review import review_queue
        tmp,db,mid,a,b=self._db()
        G.dismiss_suggestion(db,mid,a,'AB Testi')
        q=review_queue(db,mid,tmp.name); items=q['items'] if isinstance(q,dict) else q
        self.assertFalse([i for i in items if i['kind']=='glossary'])
        db.close(); tmp.cleanup()
