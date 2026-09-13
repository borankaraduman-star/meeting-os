"""Synthetic regression cases for user decisions across the actual analysis/save path."""
import json
import tempfile
import unittest
from pathlib import Path

from meeting_os import insight_layer, task_errors
from meeting_os.intelligence import merge_records
from meeting_os.memory import Memory, RETIRED
from meeting_os.store import Store
from meeting_os.types import Segment


TEXT = 'Fatura ekranındaki KDV hesaplama hatası sprint sonunda düzeltilecek ve Deniz testleri çalıştıracak.'
REWORDED = TEXT.replace('düzeltilecek', 'giderilecek')
TITLE = 'Aylık bütçe raporunu müşteriye hemen gönder'


def record(text=None, actions=()):
    return {'summary': [] if text is None else [{'text': text, 'evidence': [{'segment_id': 1, 'quote': TEXT}]}],
            'actions': list(actions), 'decisions': [], 'risks': [], 'questions': []}


def action(quote=TEXT, **fields):
    return {'title': TITLE, 'owner': 'Deniz', 'due_text': 'yarın',
            'evidence': [{'segment_id': 1, 'quote': quote, 'source': 'system'}], **fields}


class LearningPreservationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = Store(Path(self.tmp.name) / 'db.sqlite')
        self.addCleanup(self.store.close)
        self.mid = self.store.create_meeting('Synthetic meeting', {})
        self.store.add_segment(self.mid, Segment(0, 8, TEXT, 'system', 'S0', 'Deniz'))
        self.store.status(self.mid, 'complete')
        self.memory = Memory(self.store)

    def save(self, payload, merge=True):
        return self.memory.save_analysis(self.mid, self.memory.current_hash(self.mid), 'synthetic',
                                         merge_records([payload]) if merge else payload)

    def current_task(self):
        tasks = [t for t in self.memory.actions(meeting=self.mid) if t['state'] not in RETIRED]
        self.assertEqual(len(tasks), 1)
        return tasks[0]

    def test_live_merge_then_save_keeps_edit_remove_and_confirm(self):
        for decision in ('edit', 'remove', 'confirm'):
            with self.subTest(decision=decision):
                first = self.save(record(TEXT))
                iid = first['payload']['summary'][0]['item_id']
                insight_layer.record(self.store, self.mid, iid, 'summary', decision,
                                     text='Human wording' if decision == 'edit' else None)
                latest = self.save(record(REWORDED))
                item = latest['payload']['summary'][0]
                self.assertEqual(item['item_id'], iid)
                self.assertFalse(latest['insight_unmatched'])
                self.assertTrue(item.get({'edit': 'user_edited', 'remove': 'removed', 'confirm': 'confirmed'}[decision]))
                insight_layer.undo(self.store, self.mid, iid, decision)

    def test_removal_does_not_hide_an_expanded_or_changed_claim(self):
        first = self.save(record(TEXT))
        iid = first['payload']['summary'][0]['item_id']
        insight_layer.record(self.store, self.mid, iid, 'summary', 'remove')
        for changed in (TEXT + ' Ayrıca yeni müşteri sözleşmesi onaylandı.',
                        TEXT.replace('çalıştıracak', 'çalıştırmayacak'),
                        TEXT.replace('Deniz', 'Ece')):
            with self.subTest(text=changed):
                # Exercise matching itself as well as the production-generated-ID path.
                self.save(record(TEXT))
                latest = self.save(record(changed), merge=False)
                self.assertFalse(latest['payload']['summary'][0].get('removed'))
                self.assertTrue(latest['insight_unmatched'])

    def test_ambiguous_summary_match_does_not_pick_first_item(self):
        first = record()
        first['summary'] = [{'text': t, 'evidence': [{'segment_id': 1, 'quote': TEXT}]}
                            for t in (TEXT, TEXT.replace('düzeltilecek', 'onarılacak'))]
        saved = self.save(first, merge=False)
        iid = saved['payload']['summary'][0]['item_id']
        insight_layer.record(self.store, self.mid, iid, 'summary', 'remove')
        latest = self.save(record(REWORDED), merge=False)
        self.assertFalse(latest['payload']['summary'][0].get('removed'))

    def test_reworded_task_preserves_explicit_fields_and_calendar_date(self):
        self.save(record(actions=[action(due_text=None)]))
        old = self.current_task()
        self.memory.update_action(old['id'], {'owner': 'Ece', 'title': 'Human task title'}, 'inference_error')
        self.memory.set_due_date(old['id'], '2026-09-20')
        self.save(record(actions=[action(TEXT + ' More context', due_text='gelecek hafta')]))
        task = self.current_task()
        self.assertEqual((task['owner'], task['title'], task['payload'].get('due_date')),
                         ('Ece', 'Human task title', '2026-09-20'))
        self.assertEqual(task['due_text'], 'gelecek hafta')  # this field was never edited
        self.assertFalse(task['stale'])

    def test_done_or_dismissed_task_does_not_reopen_on_rewording(self):
        self.save(record(actions=[action()]))
        old = self.current_task()
        for state in ('done', 'dismissed'):
            self.memory.update_action(old['id'], {'state': state})
            self.save(record(actions=[action(TEXT + state)]))
            latest = max(self.memory.actions(meeting=self.mid), key=lambda t: t['analysis'])
            self.assertEqual(latest['state'], state)
            old = latest

    def test_distinct_deadline_does_not_inherit_a_task_correction(self):
        self.save(record(actions=[action(due_text='pazartesi')]))
        old = self.current_task()
        self.memory.update_action(old['id'], {'owner': 'Ece'}, 'inference_error')
        self.save(record(actions=[action(TEXT + ' Separate promise', due_text='cuma')]))
        latest = max(self.memory.actions(meeting=self.mid), key=lambda t: t['analysis'])
        self.assertEqual(latest['owner'], 'Deniz')
        self.assertEqual(self.memory.task_history(latest['id']), [])

    def test_reanalysis_copies_are_not_new_human_error_evidence(self):
        self.save(record(actions=[action()]))
        old = self.current_task()
        self.memory.set_due_date(old['id'], '2026-09-20', 'inference_error')
        for i in range(4):
            self.save(record(actions=[action(TEXT + f' Context {i}')]))
        measured = task_errors.counts(self.store)
        self.assertEqual((measured['total'], measured['tasks'], measured['classes']['date_parse']), (1, 1, 1))
        self.assertEqual(task_errors.review_classes(self.store), ())

    def test_returning_to_an_earlier_wording_keeps_the_latest_human_decision(self):
        self.save(record(actions=[action()]))
        original = self.current_task()
        self.memory.update_action(original['id'], {'owner': 'Ece'}, 'inference_error')
        self.save(record(actions=[action(TEXT + ' Extra context')]))
        rewritten = self.current_task()
        self.memory.update_action(rewritten['id'], {'owner': 'Can'}, 'changed_later')
        self.save(record(actions=[action()]))
        task = self.current_task()
        self.assertEqual((task['id'], task['owner'], task['stale']), (original['id'], 'Can', False))
        self.assertEqual(len(self.memory.task_history(task['id'])), 2)
        self.assertEqual(task_errors.counts(self.store)['total'], 1)

    def test_returning_task_reopens_if_only_the_model_superseded_it(self):
        self.save(record(actions=[action()]))
        original = self.current_task()
        self.save(record(actions=[action('Unrelated evidence', title='Yeni ekip sunumunu hazırla')]))
        self.save(record(actions=[action()]))
        task = self.current_task()
        self.assertEqual((task['id'], task['state'], task['stale']), (original['id'], 'open', False))

    def test_same_task_id_preserves_only_the_field_the_user_edited(self):
        self.save(record(actions=[action()]))
        original = self.current_task()
        self.memory.update_action(original['id'], {'owner': 'Ece'}, 'inference_error')
        self.save(record(actions=[action(due_text='gelecek hafta')]))
        task = self.current_task()
        self.assertEqual((task['id'], task['owner'], task['due_text']), (original['id'], 'Ece', 'gelecek hafta'))

    def test_history_carries_new_edits_when_wordings_repeat(self):
        self.save(record(actions=[action()]))
        first = self.current_task()
        self.memory.update_action(first['id'], {'owner': 'Ece'}, 'inference_error')
        self.save(record(actions=[action(TEXT + ' Extra context')]))
        self.save(record(actions=[action()]))
        self.memory.set_due_date(first['id'], '2026-09-20')
        self.save(record(actions=[action(TEXT + ' Extra context')]))
        latest = self.current_task()
        self.assertEqual(len(self.memory.task_history(latest['id'])), 2)
        self.save(record(actions=[action(TEXT + ' Third wording')]))
        self.assertEqual(self.current_task()['payload'].get('due_date'), '2026-09-20')

    def test_same_title_and_quote_keep_distinct_owners_and_deadlines(self):
        for owners in (('Deniz', 'Ece'), ('Deniz', 'Deniz')):
            with self.subTest(owners=owners):
                actions = [action(owner=owners[0], due_text='pazartesi'), action(owner=owners[1], due_text='cuma')]
                saved = self.save(record(actions=actions))
                current = [t for t in self.memory.actions(meeting=self.mid) if t['analysis'] == saved['id']]
                self.assertEqual(len(current), 2)
                self.assertEqual({(t['owner'], t['due_text']) for t in current},
                                 {(owners[0], 'pazartesi'), (owners[1], 'cuma')})
                before = {(t['owner'], t['due_text']): t['id'] for t in current}
                saved = self.save(record(actions=actions[::-1]))
                current = [t for t in self.memory.actions(meeting=self.mid) if t['analysis'] == saved['id']]
                self.assertEqual({(t['owner'], t['due_text']): t['id'] for t in current}, before)

    def test_legacy_collision_keeps_edits_with_the_original_owner(self):
        ece, deniz = action(owner='Ece', due_text='cuma'), action(owner='Deniz', due_text='pazartesi')
        saved = self.save(record(actions=[ece]))
        old = self.current_task()
        # Old releases stored both actions in the analysis, but the shared task ID retained only Ece.
        with self.store.db:
            self.store.db.execute('UPDATE analyses SET payload=? WHERE id=?',
                                  (json.dumps(record(actions=[deniz, ece])), saved['id']))
        self.memory.update_action(old['id'], {'owner': 'Can', 'state': 'done'}, 'changed_later')
        self.memory.set_due_date(old['id'], '2026-09-20')
        saved = self.save(record(actions=[ece, deniz]))
        current = [t for t in self.memory.actions(meeting=self.mid) if t['analysis'] == saved['id']]
        self.assertEqual(len(current), 2)
        ece_task = next(t for t in current if t['payload']['owner'] == 'Ece')
        deniz_task = next(t for t in current if t['payload']['owner'] == 'Deniz')
        self.assertEqual((ece_task['id'], ece_task['owner'], ece_task['state'], ece_task['payload'].get('due_date')),
                         (old['id'], 'Can', 'done', '2026-09-20'))
        self.assertEqual((deniz_task['owner'], deniz_task['state'], deniz_task['payload'].get('due_date')),
                         ('Deniz', 'open', None))
        self.assertFalse(self.memory.task_history(deniz_task['id']))

    def test_collision_ids_survive_single_task_and_return(self):
        ece, deniz = action(owner='Ece', due_text='cuma'), action(owner='Deniz', due_text='pazartesi')
        saved = self.save(record(actions=[deniz, ece]))
        current = [t for t in self.memory.actions(meeting=self.mid) if t['analysis'] == saved['id']]
        self.assertEqual(len(current), 2)
        before = {t['owner']: t['id'] for t in current}
        for only in (ece, deniz):
            self.save(record(actions=[only]))
            self.assertEqual(self.current_task()['id'], before[only['owner']])
        saved = self.save(record(actions=[ece, deniz]))
        current = [t for t in self.memory.actions(meeting=self.mid) if t['analysis'] == saved['id']]
        self.assertEqual({t['owner']: t['id'] for t in current}, before)

    def test_returning_collision_member_does_not_inherit_another_members_edits(self):
        ece, deniz = action(owner='Ece', due_text='cuma'), action(owner='Deniz', due_text='cuma')
        self.save(record(actions=[deniz, ece]))
        old = next(t for t in self.memory.actions(meeting=self.mid) if t['owner'] == 'Deniz')
        self.memory.update_action(old['id'], {'owner': 'Ece', 'state': 'done'}, 'changed_later')
        self.memory.set_due_date(old['id'], '2026-09-20')
        self.save(record(actions=[deniz]))
        saved = self.save(record(actions=[ece]))
        latest = next(t for t in self.memory.actions(meeting=self.mid) if t['analysis'] == saved['id'])
        self.assertEqual((latest['state'], latest['payload'].get('due_date')), ('open', None))
        self.assertFalse(self.memory.task_history(latest['id']))

    def test_reversed_or_expanded_task_does_not_inherit_dismissal(self):
        title = 'Müşterinin yeni ödeme servisindeki kritik güvenlik açığını kapatmak için üretim geçişini onayla'
        for changed in (title[:-6] + 'onaylama', title + ' ve yedekleri sil'):
            with self.subTest(title=changed):
                self.save(record(actions=[action(title=title)]))
                old = max(self.memory.actions(meeting=self.mid), key=lambda t: t['analysis'])
                self.memory.update_action(old['id'], {'state': 'dismissed'})
                saved = self.save(record(actions=[action(title=changed)]))
                latest = next(t for t in self.memory.actions(meeting=self.mid) if t['analysis'] == saved['id'])
                self.assertEqual(latest['state'], 'open')
                self.assertFalse(self.memory.task_history(latest['id']))

    def test_ordinary_task_inflection_keeps_the_human_decision(self):
        title = 'Müşterinin yeni ödeme servisindeki kritik güvenlik açığını kapatmak için üretim geçişini onayla'
        self.save(record(actions=[action(title=title)]))
        self.memory.update_action(self.current_task()['id'], {'state': 'done'})
        saved = self.save(record(actions=[action(title=title[:-6] + 'onaylayın')]))
        latest = next(t for t in self.memory.actions(meeting=self.mid) if t['analysis'] == saved['id'])
        self.assertEqual(latest['state'], 'done')

    def test_another_connection_invalidates_cached_analysis_and_hash(self):
        saved = self.save(record(TEXT))
        other = Store(self.store.path)
        self.addCleanup(other.close)
        insight_layer.record(other, self.mid, saved['payload']['summary'][0]['item_id'], 'summary', 'edit', text='Human wording')
        self.assertEqual(self.memory.latest(self.mid)['payload']['summary'][0]['text'], 'Human wording')
        old_hash = self.memory.current_hash(self.mid)
        payload = json.loads(other.db.execute('SELECT payload FROM segments WHERE id=1').fetchone()[0])
        payload['text'] = 'A changed transcript'
        with other.db:
            other.db.execute('UPDATE segments SET payload=? WHERE id=1', (json.dumps(payload),))
        with self.assertRaisesRegex(ValueError, 'Transkript'):
            self.memory.save_analysis(self.mid, old_hash, 'synthetic', record(TEXT))
        self.assertEqual(self.store.db.execute('SELECT count(*) FROM analyses').fetchone()[0], 1)


if __name__ == '__main__':
    unittest.main()
