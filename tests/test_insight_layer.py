"""1.2.81 — the user's decision about a summary item survives the next analysis.

What these guard: an item keeps one identity across re-analysis, a correction/removal/approval is laid over
the model's output instead of into it, a decision whose item disappeared is handed back rather than dropped,
and every export shows the user's view — their wording, without what they removed.
"""
import json
import tempfile
import unittest
from pathlib import Path

from meeting_os import insight_layer as IL
from meeting_os.desktop import dispatch
from meeting_os.intelligence import ensure_item_ids, item_id, merge_records, similarity
from meeting_os.memory import Memory
from meeting_os.share import prepare_share
from meeting_os.store import Store
from meeting_os.types import Segment

TEXT = 'Fatura ekranındaki KDV hesaplama hatası sprint sonunda düzeltilecek ve Deniz testleri çalıştıracak.'
# The same claim, one verb reworded: no containment, so it has to clear the 0.8 similarity bar on its own.
REWORDED = 'Fatura ekranındaki KDV hesaplama hatası sprint sonunda giderilecek ve Deniz testleri çalıştıracak.'
OTHER = 'Ekim sonuna kadar arama indeksini yeniden kuracağız.'


def payload(summary, decisions=(), risks=(), questions=()):
    return {'summary': list(summary), 'decisions': list(decisions), 'risks': list(risks), 'questions': list(questions),
            'actions': [], 'dropped_quotes': 0, 'dropped_items': 0}


def note(text, segment=1, quote=None):
    return {'text': text, 'evidence': [{'segment_id': segment, 'quote': quote or text[:20], 'start': 0.0}]}


def meeting(tmp, texts=(TEXT, OTHER)):
    """A complete meeting whose segments carry the sentences the analysis will cite."""
    store = Store(Path(tmp) / 'meeting-os.sqlite')
    mid = store.create_meeting('Sprint', {})
    ids = [store.add_segment(mid, Segment(i * 10.0, i * 10.0 + 8, text, 'mic', 'mic:S0', 'Boran')) for i, text in enumerate(texts)]
    store.status(mid, 'complete')
    return store, mid, ids


def save(store, mid, record):
    mem = Memory(store)
    return mem.save_analysis(mid, mem.current_hash(mid), 'test', record)


class ItemIdentityTests(unittest.TestCase):
    def test_the_same_item_keeps_one_id_across_reanalysis(self):
        with tempfile.TemporaryDirectory() as tmp:
            store, mid, ids = meeting(tmp)
            first = save(store, mid, payload([note(TEXT, ids[0])]))
            was = first['payload']['summary'][0]['item_id']
            again = save(store, mid, payload([note(TEXT, ids[0])]))
            self.assertEqual(again['payload']['summary'][0]['item_id'], was)
            store.close()

    def test_a_reworded_item_backed_by_the_same_source_inherits_the_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            store, mid, ids = meeting(tmp)
            was = save(store, mid, payload([note(TEXT, ids[0])]))['payload']['summary'][0]['item_id']
            self.assertGreaterEqual(similarity(TEXT, REWORDED), 0.8)
            after = save(store, mid, payload([note(REWORDED, ids[0])]))['payload']['summary'][0]
            self.assertEqual(after['item_id'], was)   # the sentence moved, the item did not
            store.close()

    def test_a_different_claim_gets_a_different_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            store, mid, ids = meeting(tmp)
            was = save(store, mid, payload([note(TEXT, ids[0])]))['payload']['summary'][0]['item_id']
            after = save(store, mid, payload([note(OTHER, ids[1])]))['payload']['summary'][0]
            self.assertNotEqual(after['item_id'], was)
            store.close()

    def test_an_analysis_saved_before_ids_existed_gets_them_when_it_is_read(self):
        with tempfile.TemporaryDirectory() as tmp:
            store, mid, ids = meeting(tmp)
            save(store, mid, payload([note(TEXT, ids[0])]))
            raw = json.loads(store.db.execute('SELECT payload FROM analyses WHERE meeting=?', (mid,)).fetchone()[0])
            for item in raw['summary']: item.pop('item_id')
            with store.db: store.db.execute('UPDATE analyses SET payload=? WHERE meeting=?', (json.dumps(raw, ensure_ascii=False), mid))
            read = Memory(store).latest(mid)['payload']['summary'][0]
            self.assertEqual(read['item_id'], item_id('summary', read))   # deterministic: no migration needed
            store.close()

    def test_two_sections_carrying_the_same_sentence_are_two_items(self):
        one = payload([note(TEXT)], decisions=[note(TEXT)])
        ensure_item_ids(one)
        self.assertNotEqual(one['summary'][0]['item_id'], one['decisions'][0]['item_id'])

    def test_merge_records_hands_back_identified_items(self):
        merged = merge_records([payload([note(TEXT)]), payload([note(OTHER, 2)])])
        self.assertTrue(all(i.get('item_id') for i in merged['summary']))
        self.assertEqual(len({i['item_id'] for i in merged['summary']}), 2)


class LayerTests(unittest.TestCase):
    def test_an_edit_is_shown_and_the_model_sentence_is_kept_underneath(self):
        with tempfile.TemporaryDirectory() as tmp:
            store, mid, ids = meeting(tmp)
            iid = save(store, mid, payload([note(TEXT, ids[0])]))['payload']['summary'][0]['item_id']
            IL.record(store, mid, iid, 'summary', 'edit', text='Arama indeksi Ekim sonunda yenilenecek.')
            item = Memory(store).latest(mid)['payload']['summary'][0]
            self.assertEqual(item['text'], 'Arama indeksi Ekim sonunda yenilenecek.')
            self.assertEqual(item['model_text'], TEXT)
            self.assertTrue(item['user_edited'])
            store.close()

    def test_a_removed_item_is_hidden_not_deleted_and_carries_its_reason(self):
        with tempfile.TemporaryDirectory() as tmp:
            store, mid, ids = meeting(tmp)
            iid = save(store, mid, payload([note(TEXT, ids[0]), note(OTHER, ids[1])]))['payload']['summary'][0]['item_id']
            IL.record(store, mid, iid, 'summary', 'remove', reason='duplicate')
            loaded = Memory(store).latest(mid)['payload']
            self.assertEqual(len(loaded['summary']), 2)   # still there, so "göster" can bring it back
            self.assertTrue(loaded['summary'][0]['removed'])
            self.assertEqual(loaded['summary'][0]['remove_reason'], 'duplicate')
            self.assertEqual(loaded['removed_counts']['summary'], 1)
            self.assertEqual([i['text'] for i in IL.visible(loaded['summary'])], [OTHER])
            store.close()

    def test_confirm_is_a_switch_and_a_removal_can_be_taken_back(self):
        with tempfile.TemporaryDirectory() as tmp:
            store, mid, ids = meeting(tmp)
            iid = save(store, mid, payload([note(TEXT, ids[0])]))['payload']['summary'][0]['item_id']
            self.assertTrue(IL.toggle_confirm(store, mid, iid, 'summary')['confirmed'])
            self.assertTrue(Memory(store).latest(mid)['payload']['summary'][0]['confirmed'])
            self.assertFalse(IL.toggle_confirm(store, mid, iid, 'summary')['confirmed'])
            self.assertIsNone(Memory(store).latest(mid)['payload']['summary'][0].get('confirmed'))
            IL.record(store, mid, iid, 'summary', 'remove')
            IL.undo(store, mid, iid, 'remove')
            self.assertIsNone(Memory(store).latest(mid)['payload']['summary'][0].get('removed'))
            store.close()

    def test_a_reason_has_to_be_one_of_the_three_and_an_edit_needs_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            store, mid, ids = meeting(tmp)
            iid = save(store, mid, payload([note(TEXT, ids[0])]))['payload']['summary'][0]['item_id']
            with self.assertRaises(ValueError): IL.record(store, mid, iid, 'summary', 'remove', reason='hoşuma gitmedi')
            with self.assertRaises(ValueError): IL.record(store, mid, iid, 'summary', 'edit', text='   ')
            with self.assertRaises(ValueError): IL.record(store, mid, '', 'summary', 'confirm')
            store.close()

    def test_reanalysis_never_silently_overrides_the_user(self):
        with tempfile.TemporaryDirectory() as tmp:
            store, mid, ids = meeting(tmp)
            iid = save(store, mid, payload([note(TEXT, ids[0])]))['payload']['summary'][0]['item_id']
            IL.record(store, mid, iid, 'summary', 'edit', text='Arama indeksi Ekim sonunda yenilenecek.')
            IL.record(store, mid, iid, 'summary', 'confirm')
            after = save(store, mid, payload([note(REWORDED, ids[0])]))['payload']['summary'][0]
            self.assertEqual(after['text'], 'Arama indeksi Ekim sonunda yenilenecek.')
            self.assertEqual(after['model_text'], REWORDED)
            self.assertTrue(after['confirmed'])
            store.close()

    def test_a_decision_whose_item_is_gone_is_reported_not_dropped(self):
        with tempfile.TemporaryDirectory() as tmp:
            store, mid, ids = meeting(tmp)
            iid = save(store, mid, payload([note(TEXT, ids[0])]))['payload']['summary'][0]['item_id']
            IL.record(store, mid, iid, 'summary', 'remove', reason='wrong')
            latest = save(store, mid, payload([note(OTHER, ids[1])]))
            self.assertEqual([u['item_id'] for u in latest['insight_unmatched']], [iid])
            self.assertEqual(latest['insight_unmatched'][0]['label'], 'kaldırma · Yanlış')
            self.assertFalse(latest['payload']['summary'][0].get('removed'))   # never carried onto a different claim
            store.close()


class ExportTests(unittest.TestCase):
    def test_the_share_preview_shows_the_user_view(self):
        with tempfile.TemporaryDirectory() as tmp:
            store, mid, ids = meeting(tmp)
            saved = save(store, mid, payload([note(TEXT, ids[0])], decisions=[note(OTHER, ids[1])]))
            IL.record(store, mid, saved['payload']['summary'][0]['item_id'], 'summary', 'edit', text='Arama indeksi yenilenecek.')
            IL.record(store, mid, saved['payload']['decisions'][0]['item_id'], 'decisions', 'remove', reason='duplicate')
            text = prepare_share(store, mid, kinds=('summary',))['text']
            self.assertIn('Arama indeksi yenilenecek.', text)
            self.assertNotIn(TEXT, text)
            self.assertNotIn(OTHER, text)
            self.assertIn('Kayıtlı karar yok.', text)
            store.close()

    def test_the_markdown_export_matches_what_the_app_shows(self):
        with tempfile.TemporaryDirectory() as tmp:
            store, mid, ids = meeting(tmp)
            db = Path(store.path)
            saved = save(store, mid, payload([note(TEXT, ids[0]), note(OTHER, ids[1])]))
            IL.record(store, mid, saved['payload']['summary'][1]['item_id'], 'summary', 'remove')
            store.close()
            out = Path(tmp) / 'ozet.md'
            dispatch({'action': 'export_analysis', 'meeting': mid, 'path': str(out)}, db)
            body = out.read_text(encoding='utf-8')
            self.assertIn(TEXT, body)
            self.assertNotIn(OTHER, body)


class BridgeTests(unittest.TestCase):
    def test_the_four_bridge_actions_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            store, mid, ids = meeting(tmp)
            db = Path(store.path)
            iid = save(store, mid, payload([note(TEXT, ids[0])]))['payload']['summary'][0]['item_id']
            store.close()
            dispatch({'action': 'insight_edit', 'meeting': mid, 'item_id': iid, 'section': 'summary', 'text': 'Kendi cümlem.'}, db)
            dispatch({'action': 'insight_confirm', 'meeting': mid, 'item_id': iid, 'section': 'summary'}, db)
            item = dispatch({'action': 'intelligence', 'meeting': mid}, db)['analysis']['payload']['summary'][0]
            self.assertEqual(item['text'], 'Kendi cümlem.')
            self.assertTrue(item['confirmed'])
            dispatch({'action': 'insight_remove', 'meeting': mid, 'item_id': iid, 'section': 'summary', 'reason': 'too_detailed'}, db)
            self.assertTrue(dispatch({'action': 'intelligence', 'meeting': mid}, db)['analysis']['payload']['summary'][0]['removed'])
            dispatch({'action': 'insight_restore', 'meeting': mid, 'item_id': iid, 'what': 'remove'}, db)
            dispatch({'action': 'insight_restore', 'meeting': mid, 'item_id': iid, 'what': 'edit'}, db)
            back = dispatch({'action': 'intelligence', 'meeting': mid}, db)['analysis']['payload']['summary'][0]
            self.assertEqual(back['text'], TEXT)
            self.assertIsNone(back.get('removed'))


class RetentionAndMetricsTests(unittest.TestCase):
    def test_deleting_the_meeting_deletes_the_wording_the_user_typed_about_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            store, mid, ids = meeting(tmp)
            db = Path(store.path)
            iid = save(store, mid, payload([note(TEXT, ids[0])]))['payload']['summary'][0]['item_id']
            IL.record(store, mid, iid, 'summary', 'edit', text='Kendi cümlem.')
            store.close()
            dispatch({'action': 'delete_meeting', 'meeting': mid}, db)
            store = Store(db)
            self.assertEqual(store.db.execute('SELECT count(*) FROM insight_edits WHERE meeting=?', (mid,)).fetchone()[0], 0)
            store.close()

    def test_each_decision_is_offered_to_the_metrics_recorder_once(self):
        seen = []
        with tempfile.TemporaryDirectory() as tmp:
            store, mid, ids = meeting(tmp)
            iid = save(store, mid, payload([note(TEXT, ids[0])]))['payload']['summary'][0]['item_id']
            was = IL.record_event
            IL.record_event = lambda store, action, **fields: seen.append((action, fields.get('object'), fields.get('outcome')))
            try:
                IL.record(store, mid, iid, 'summary', 'edit', text='Kendi cümlem.')
                IL.record(store, mid, iid, 'summary', 'remove', reason='wrong')
                IL.toggle_confirm(store, mid, iid, 'summary')
            finally:
                IL.record_event = was
            self.assertEqual([a for a, _, _ in seen], ['summary_edit', 'summary_remove', 'summary_confirm'])
            self.assertTrue(all(obj == iid for _, obj, _ in seen))
            self.assertEqual(seen[1][2], 'wrong')   # the reason is the outcome, and only a stated one is recorded
            store.close()

    def test_a_recorder_that_does_not_know_a_keyword_never_breaks_the_action(self):
        calls = []
        with tempfile.TemporaryDirectory() as tmp:
            store, mid, ids = meeting(tmp)
            iid = save(store, mid, payload([note(TEXT, ids[0])]))['payload']['summary'][0]['item_id']
            was = IL.record_event
            IL.record_event = lambda store, action, **fields: calls.append(action) if not fields else (_ for _ in ()).throw(TypeError('unexpected keyword'))
            try: IL.record(store, mid, iid, 'summary', 'confirm')
            finally: IL.record_event = was
            self.assertEqual(calls, ['summary_confirm'])   # retried without the extras rather than lost
            self.assertTrue(Memory(store).latest(mid)['payload']['summary'][0]['confirmed'])
            store.close()


if __name__ == '__main__':
    unittest.main()
