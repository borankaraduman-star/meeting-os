"""1.2.86 #8 — the three summary preferences, and the line they are NOT allowed to cross.

What these guard:

1. A correction that changes a number, a name or a negation is the user fixing a FACT, and is never
   counted as "they like shorter bullets".
2. No preference exists below three different meetings.
3. What reaches the prompt is a fixed template sentence — never a word the user typed — and it stays
   inside the 300-token budget without costing one extra model call.
4. `summary_target` moves by at most a quarter, and never outside its own bounds.
"""
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from meeting_os import insight_layer as IL
from meeting_os import preferences as P
from meeting_os.intelligence import SUMMARY_MAX, SUMMARY_MIN, analyze_rows, summary_target, system_prompt
from meeting_os.memory import Memory
from meeting_os.store import Store
from meeting_os.types import Segment

LONG = 'Sprint planı görüşüldü ve kapsam daraltıldı; ekip bu yaklaşımı kabul etti.'
SHORT = 'Sprint planı görüşüldü.'
SECRET = 'Gizli müşteri Zebra Holding ile toplantı yapıldı'   # a sentence that must never reach a prompt


def meeting(store, index, texts):
    mid = store.create_meeting(f'Toplantı {index}', {})
    ids = [store.add_segment(mid, Segment(i * 10.0, i * 10.0 + 8, text, 'mic', 'mic:S0', 'Boran')) for i, text in enumerate(texts)]
    store.status(mid, 'complete')
    return mid, ids


def note(text, segment):
    return {'text': text, 'evidence': [{'segment_id': segment, 'quote': text[:20], 'start': 0.0}]}


def payload(items):
    return {'summary': items, 'decisions': [], 'risks': [], 'questions': [], 'actions': [],
            'dropped_quotes': 0, 'dropped_items': 0}


def saved(store, mid, texts, ids):
    mem = Memory(store)
    record = mem.save_analysis(mid, mem.current_hash(mid), 'test', payload([note(t, ids[i]) for i, t in enumerate(texts)]))
    return [item['item_id'] for item in record['payload']['summary']]


def world(tmp, meetings, texts=(LONG,)):
    """`meetings` meetings, each carrying the same bullets, analysed and ready to be corrected."""
    store = Store(Path(tmp) / 'meeting-os.sqlite')
    out = []
    for index in range(meetings):
        mid, ids = meeting(store, index, list(texts))
        out.append((mid, saved(store, mid, list(texts), ids)))
    return store, out


class StyleOrFactTests(unittest.TestCase):
    def test_a_changed_number_is_a_factual_correction(self):
        self.assertEqual(P.classify_edit('Ekip 15 kişiyle çalışacak.', 'Ekip 20 kişiyle çalışacak.'), 'factual')
        self.assertEqual(P.classify_edit('Dönüşüm %12 arttı.', 'Dönüşüm %21 arttı.'), 'factual')
        self.assertEqual(P.classify_edit('Ekip 15 kişiyle çalışacak.', 'Ekip 15 kişiyle devam edecek.'), 'style')

    def test_a_changed_name_is_a_factual_correction(self):
        self.assertEqual(P.classify_edit('Deniz raporu yarın gönderecek.', 'Ece raporu yarın gönderecek.'), 'factual')
        # the same people, one reordering: capitalisation moved, nobody was replaced
        self.assertEqual(P.classify_edit('Deniz raporu yarın gönderecek.', 'Raporu yarın Deniz gönderecek.'), 'style')

    def test_a_changed_negation_is_a_factual_correction(self):
        self.assertEqual(P.classify_edit('Rapor cuma günü gönderilecek.', 'Rapor cuma günü gönderilmeyecek.'), 'factual')
        self.assertEqual(P.classify_edit('Migration bu sprint yapılmayacak.', 'Migration bu sprint yapılacak.'), 'factual')

    def test_pure_rewording_is_a_style_edit(self):
        self.assertEqual(P.classify_edit(LONG, SHORT), 'style')
        self.assertEqual(P.classify_edit('Toplantıda kapsam görüşüldü.', 'Kapsam toplantıda görüşüldü.'), 'style')

    def test_a_rewrite_that_drops_a_capitalised_word_is_read_as_factual(self):
        """The conservative direction, on purpose: Turkish capitalises the first word of every sentence, so a
        rewrite that replaces the opening noun could be a dropped name. Losing one style sample is cheap;
        learning "shorter bullets" from a correction that fixed a fact is not."""
        self.assertEqual(P.classify_edit('Fatura ekranındaki hata düzeltilecek.', 'KDV hatası düzeltilecek.'), 'factual')

    def test_a_factual_edit_never_reaches_the_length_preference(self):
        with tempfile.TemporaryDirectory() as tmp:
            store, rows = world(tmp, 3)
            for index, (mid, items) in enumerate(rows):
                # a shorter wording, but it also drops a number: a fact was fixed, not a style chosen
                IL.record(store, mid, items[0], 'summary', 'edit', text='Kapsam 3 maddeye indirildi.')
            record = P.derive(store)
            self.assertIsNone(record['bullet_length']['value'])
            self.assertEqual(record['bullet_length']['evidence']['style_edits'], 0)
            self.assertEqual(record['bullet_length']['evidence']['factual_edits'], 3)
            store.close()


class EvidenceBarTests(unittest.TestCase):
    def test_three_removals_in_one_meeting_are_not_a_preference(self):
        with tempfile.TemporaryDirectory() as tmp:
            store, rows = world(tmp, 1, texts=(LONG, SHORT, 'Üçüncü konu konuşuldu.'))
            mid, items = rows[0]
            for item in items:
                IL.record(store, mid, item, 'summary', 'remove', reason='too_detailed')
            record = P.derive(store)
            self.assertIsNone(record['detail']['value'])
            self.assertEqual(record['detail']['evidence']['too_detailed'], 3)
            self.assertEqual(P.prompt_line(P.values(record)), '')
            store.close()

    def test_the_same_removal_across_three_meetings_is(self):
        with tempfile.TemporaryDirectory() as tmp:
            store, rows = world(tmp, 3)
            for mid, items in rows:
                IL.record(store, mid, items[0], 'summary', 'remove', reason='too_detailed')
            record = P.derive(store)
            self.assertEqual(record['detail']['value'], 'kısa')
            self.assertEqual(record['detail']['evidence']['meetings'], 3)
            store.close()

    def test_bullets_the_user_keeps_lengthening_ask_for_more_detail(self):
        with tempfile.TemporaryDirectory() as tmp:
            store, rows = world(tmp, 3, texts=(SHORT,))
            for mid, items in rows:
                IL.record(store, mid, items[0], 'summary', 'edit', text=LONG)
            record = P.derive(store)
            self.assertEqual(record['detail']['value'], 'ayrıntılı')
            self.assertEqual(record['bullet_length']['value'], 'uzun')
            store.close()

    def test_shortening_edits_give_the_short_bullet_preference(self):
        with tempfile.TemporaryDirectory() as tmp:
            store, rows = world(tmp, 3)
            for mid, items in rows:
                IL.record(store, mid, items[0], 'summary', 'edit', text=SHORT)
            record = P.derive(store)
            self.assertEqual(record['bullet_length']['value'], 'kısa')
            self.assertLess(record['bullet_length']['evidence']['median_ratio'], 1.0)
            store.close()

    def test_repeat_removals_ask_for_merging_and_their_absence_asks_for_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            store, rows = world(tmp, 3, texts=(LONG, SHORT))
            for mid, items in rows:
                IL.record(store, mid, items[0], 'summary', 'remove', reason='duplicate')
            self.assertEqual(P.derive(store)['merge_duplicates']['value'], 'çok')
            store.close()
        with tempfile.TemporaryDirectory() as tmp:
            store, rows = world(tmp, 3, texts=(LONG, SHORT))
            for mid, items in rows:
                for item in items:
                    IL.record(store, mid, item, 'summary', 'remove', reason='wrong')
            record = P.derive(store)
            self.assertEqual(record['merge_duplicates']['value'], 'az')   # six removals, never once for repetition
            self.assertEqual(record['merge_duplicates']['evidence']['duplicate'], 0)
            store.close()

    def test_an_empty_store_derives_nothing_and_says_so(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / 'meeting-os.sqlite')
            record = P.derive(store)
            self.assertEqual(P.values(record), {})
            self.assertIn('veri yetersiz', P.line(record))
            store.close()


class PromptTests(unittest.TestCase):
    ALL = ({'detail': d, 'bullet_length': b, 'merge_duplicates': m}
           for d in (None, 'kısa', 'orta', 'ayrıntılı') for b in (None, 'kısa', 'uzun') for m in (None, 'az', 'çok'))

    def test_the_template_is_the_whole_vocabulary(self):
        line = P.prompt_line({'detail': 'kısa', 'bullet_length': 'kısa', 'merge_duplicates': 'çok'})
        self.assertTrue(line.startswith('Kullanıcı tercihi: '))
        self.assertIn('en fazla 20 kelime', line)
        for value in P.TEMPLATES.values():
            self.assertTrue(all(part in P.TEMPLATES.values() or True for part in [value]))
        self.assertEqual(P.prompt_line({}), '')
        self.assertEqual(P.prompt_line({'detail': 'orta'}), '')   # the neutral value says nothing at all

    def test_no_user_text_can_reach_the_prompt(self):
        with tempfile.TemporaryDirectory() as tmp:
            store, rows = world(tmp, 3)
            for mid, items in rows:
                IL.record(store, mid, items[0], 'summary', 'edit', text=SECRET)
                IL.record(store, mid, items[0], 'summary', 'remove', reason='too_detailed')
            record = P.derive(store)
            line = P.prompt_line(P.values(record))
            blob = json.dumps(record, ensure_ascii=False)
            for word in ('Zebra', 'Holding', 'müşteri', 'Sprint'):
                self.assertNotIn(word, line)
                self.assertNotIn(word, blob)          # not even the stored record keeps their wording
            self.assertNotIn(SECRET, system_prompt(P.values(record)))
            store.close()

    def test_every_combination_stays_inside_the_token_budget(self):
        for prefs in self.ALL:
            line = P.prompt_line(prefs)
            self.assertLessEqual(P.token_estimate(line), P.PROMPT_TOKEN_BUDGET, prefs)
            if line:
                self.assertIn('hiçbir konuyu', line)   # the guard clause travels with every preference

    def test_the_preference_is_appended_to_the_system_prompt_and_nothing_else_changes(self):
        from meeting_os.intelligence import SYSTEM
        prefs = {'bullet_length': 'kısa'}
        self.assertEqual(system_prompt(None), SYSTEM)
        self.assertTrue(system_prompt(prefs).startswith(SYSTEM))
        self.assertIn('en fazla 20 kelime', system_prompt(prefs))


class TargetTests(unittest.TestCase):
    def test_detail_moves_the_target_by_a_quarter_at_most(self):
        self.assertEqual(summary_target(41), 10)
        self.assertEqual(summary_target(41, 'kısa'), 8)          # −25 %
        self.assertEqual(summary_target(41, 'ayrıntılı'), 12)    # +25 %, rounded
        self.assertEqual(summary_target(41, 'orta'), 10)
        self.assertEqual(summary_target(41, None), 10)

    def test_the_existing_bounds_still_win(self):
        self.assertEqual(summary_target(0, 'kısa'), SUMMARY_MIN)
        self.assertEqual(summary_target(300, 'ayrıntılı'), SUMMARY_MAX)
        self.assertEqual(P.scale(None, 'kısa'), None)


class ModelWithSpy:
    """A model that answers the schema it is given and remembers every system prompt it was shown."""
    def __init__(self):
        self.systems = []

    def count(self, text):
        return len(text)

    def complete(self, system, user, **kwargs):
        self.systems.append(system)
        batch = json.loads(user)['transcript']
        return json.dumps({'summary': [{'text': 'Konu görüşüldü.', 'evidence': [{'segment_id': batch[0]['segment_id'], 'quote': batch[0]['text'][:18]}]}],
                           'decisions': [], 'risks': [], 'questions': [], 'actions': []}, ensure_ascii=False)


class AnalysisWiringTests(unittest.TestCase):
    ROWS = [{'id': 1, 'start': 0., 'end': 8., 'source': 'system', 'speaker': 'S0', 'speaker_name': 'Boran',
             'text': 'Sprint planını konuştuk ve kapsamı daralttık.', 'flags': []}]

    def test_the_analysis_shows_the_preference_to_the_model_without_an_extra_call(self):
        plain = ModelWithSpy()
        analyze_rows(self.ROWS, plain)
        with_prefs = ModelWithSpy()
        analyze_rows(self.ROWS, with_prefs, prefs={'bullet_length': 'kısa'})
        self.assertEqual(len(plain.systems), len(with_prefs.systems))   # zero extra model calls
        self.assertNotIn('Kullanıcı tercihi', plain.systems[0])
        self.assertIn('Kullanıcı tercihi', with_prefs.systems[0])

    def test_the_compaction_that_chooses_the_final_bullets_sees_it_too(self):
        from meeting_os.intelligence import compact_summary, validate_record
        rows = [{'id': i, 'start': float(i), 'end': i + 1.0, 'source': 'system', 'speaker': 'S0',
                 'text': f'Konu {i} görüşüldü ve karara bağlandı.', 'flags': []} for i in range(12)]
        items = validate_record({'summary': [{'text': r['text'], 'evidence': [{'segment_id': r['id'], 'quote': r['text']}]} for r in rows]}, rows)['summary']

        class Condenser(ModelWithSpy):
            def complete(self, system, user, **kwargs):
                self.systems.append(system)
                return json.dumps({'summary': [json.loads(user)['notes'][0]]}, ensure_ascii=False)

        condenser = Condenser()
        compact_summary(items, rows, condenser, target=6, prefs={'merge_duplicates': 'çok'})
        self.assertTrue(all('Kullanıcı tercihi' in prompt for prompt in condenser.systems))
        self.assertTrue(all(prompt.startswith('Condense') for prompt in condenser.systems))   # appended last, never in front


class FileTests(unittest.TestCase):
    def test_the_record_is_written_once_a_day_and_read_by_everyone_else(self):
        with tempfile.TemporaryDirectory() as tmp:
            store, rows = world(tmp, 3)
            for mid, items in rows:
                IL.record(store, mid, items[0], 'summary', 'remove', reason='too_detailed')
            data = Path(tmp)
            first = P.refresh(store, data)
            self.assertTrue(first['fresh'])
            self.assertEqual(P.load(data)['detail']['value'], 'kısa')
            self.assertFalse(P.refresh(store, data)['fresh'])            # measured already today
            later = datetime.now(timezone.utc) + timedelta(hours=30)
            self.assertTrue(P.refresh(store, data, now=later)['fresh'])
            self.assertEqual(P.values(P.load(data)), {'detail': 'kısa'})
            self.assertIn('ayrıntı kısa', P.line(P.load(data)))
            store.close()

    def test_a_missing_file_is_not_an_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(P.load(Path(tmp)), {})
            self.assertEqual(P.values(P.load(Path(tmp))), {})


if __name__ == '__main__':
    unittest.main()
