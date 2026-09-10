"""Teach a word once. One correction becomes a rule, near-miss spellings of it are fixed from then on,
Kontrol surfaces the ones nobody has taught yet, and every part of it is reversible."""
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
            self.assertTrue(result['rule']['fuzzy'])
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

    def test_a_taught_word_catches_near_misses_and_leaves_the_turkish_suffix_alone(self):
        with tempfile.TemporaryDirectory() as tmp:
            data, db = self._fixture(tmp, 'Jira\n')
            teaching = db.create_meeting('öğret'); later = db.create_meeting('sonra')
            self._segment(db, teaching, 'Trendyoll ile görüştük.')
            cm.teach(db, teaching, 'Trendyoll', 'Trendyol', data)
            sid = self._segment(db, later, "Trendyoll'a yazdık, Trendiyol raporu geldi, Trendyol'a değil, Trendyola da değil.")
            report = cm.apply_rules(db, later, data_dir=data)
            row = next(r for r in db.segments(later) if r['id'] == sid)
            self.assertEqual(row['text'], "Trendyol'a yazdık, Trendyol raporu geldi, Trendyol'a değil, Trendyola da değil.")
            self.assertEqual((report['segments'], report['fixes']), (1, 2))
            self.assertIn('auto_corrected', row['flags'])
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
            second = self._segment(db, other, 'Trendiyol raporu.')
            db.status(other, 'complete')
            self.assertTrue([i for i in review_queue(db, other, data)['items'] if i['kind'] == 'word'])
            cm.teach(db, other, 'Trendiyol', 'Trendyol', data)
            self.assertEqual([i for i in review_queue(db, other, data)['items'] if i['kind'] == 'word'], [])
            self.assertEqual(next(r for r in db.segments(other) if r['id'] == second)['text'], 'Trendyol raporu.')
            db.close()

    def test_kontrol_does_not_flag_ordinary_turkish_words(self):
        with tempfile.TemporaryDirectory() as tmp:
            data, db = self._fixture(tmp, 'Trendyol\nkontrol\n')
            mid = db.create_meeting('a')
            self._segment(db, mid, 'Kontrolü yaptık, karar sonra gelecek.')
            db.status(mid, 'complete')
            self.assertEqual([i for i in review_queue(db, mid, data)['items'] if i['kind'] == 'word'], [])
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
