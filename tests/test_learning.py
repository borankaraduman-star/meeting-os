"""1.2.80 — Güvenilir sinyal: the shared record of what the user actually decided.

Three questions these tests answer, and they are the three the review asked (Codex, 11 Sep 2026, P0 #1/#3):

1. Does every supported user action leave EXACTLY ONE event, and does a retry leave none extra?
2. Is a human decision kept apart from its automatic effects — one taught word against the twenty segments
   that rule rewrites, and an automatic name nobody looked at against one the user confirmed?
3. Does the task history now cover the calendar date, does "why" survive, and does it follow a task whose id
   a re-analysis changed?
"""
import json
import tempfile
import time
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from pathlib import Path

from meeting_os import learning
from meeting_os.desktop import dispatch
from meeting_os.memory import Memory
from meeting_os.store import Store
from meeting_os.types import Segment


def kinds(store):
    return [e['action'] for e in learning.events(store)]


class EventTableTests(unittest.TestCase):
    def store(self, tmp):
        return Store(Path(tmp) / 'meeting-os.sqlite')

    def test_the_table_appears_on_first_use_and_a_bad_action_writes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = self.store(tmp)
            self.assertEqual(learning.events(store), [])          # reading an absent table is not an error
            self.assertIsNone(learning.record_event(store, 'ölçülemez'))
            self.assertEqual(learning.events(store), [])
            eid = learning.record_event(store, 'word_teach', object='trendyol', scope='global')
            self.assertIsInstance(eid, int)
            row = learning.events(store)[0]
            self.assertEqual((row['action'], row['object'], row['scope'], row['source'], row['outcome']),
                             ('word_teach', 'trendyol', 'global', 'human', 'applied'))
            self.assertTrue(row['app_version'])
            store.close()

    def test_a_retry_of_the_same_click_is_one_event(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = self.store(tmp)
            moment = datetime(2026, 9, 11, 10, 30, 5, tzinfo=timezone.utc)
            first = learning.record_event(store, 'export_ok', object='m1', now=moment)
            again = learning.record_event(store, 'export_ok', object='m1', now=moment + timedelta(seconds=40))
            self.assertEqual(first, again)                        # same minute, same object: the same decision
            later = learning.record_event(store, 'export_ok', object='m1', now=moment + timedelta(minutes=2))
            self.assertNotEqual(first, later)                     # two minutes on: the user exported again
            other = learning.record_event(store, 'export_ok', object='m2', now=moment)
            self.assertNotEqual(first, other)
            self.assertEqual(len(learning.events(store)), 3)
            store.close()

    def test_recording_an_event_never_raises_and_never_costs_the_caller_much(self):
        class Broken:
            db = None
        self.assertIsNone(learning.record_event(Broken(), 'record_start', object='m'))
        self.assertEqual(learning.events(Broken()), [])
        with tempfile.TemporaryDirectory() as tmp:
            store = self.store(tmp)
            learning.record_event(store, 'record_start', object='warm')   # the CREATE is not part of the budget
            started = time.perf_counter()
            for i in range(50): learning.record_event(store, 'task_edit', object=f't{i}')
            each = (time.perf_counter() - started) / 50
            self.assertLess(each, 0.010, f'{each*1000:.1f} ms per event')
            store.close()

    def test_ninety_days_and_twenty_megabytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = self.store(tmp)
            old = datetime.now(timezone.utc) - timedelta(days=120)
            for i in range(5): learning.record_event(store, 'task_edit', object=f'old{i}', now=old + timedelta(minutes=i))
            for i in range(3): learning.record_event(store, 'task_edit', object=f'new{i}')
            self.assertEqual(learning.prune(store)['removed'], 5)
            self.assertEqual(len(learning.events(store)), 3)
            # The byte ceiling bites even when nothing is old enough to expire.
            self.assertGreater(learning.prune(store, max_bytes=1)['removed'], 0)
            self.assertEqual(learning.events(store), [])
            store.close()

    def test_the_hourly_housekeeping_prunes(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / 'meeting-os.sqlite'
            store = Store(db)
            learning.record_event(store, 'task_edit', object='x',
                                  now=datetime.now(timezone.utc) - timedelta(days=200))
            store.close()
            result = dispatch({'action': 'storage_housekeeping'}, db)
            self.assertEqual(result['learning']['removed'], 1)


class OneActionOneEventTests(unittest.TestCase):
    """Every wired bridge action, once, and what it leaves behind."""

    def build(self, tmp):
        db = Path(tmp) / 'meeting-os.sqlite'
        store = Store(db)
        mid = store.create_meeting('Bütçe', {'paths': {'system': str(Path(tmp) / 'a.wav')}})
        flags = ['cloud_transcript', 'cloud_diarization']
        first = store.add_segment(mid, Segment(0, 4, 'Trendyoll ile görüştük.', 'system', 'Konuşmacı 1',
                                               metrics={'cluster': '0:0', 'identity': {'name': 'Ayşe'}}, flags=flags))
        second = store.add_segment(mid, Segment(4, 8, 'Trendyoll raporu yarın.', 'system', 'Konuşmacı 2',
                                                metrics={'cluster': '0:1', 'identity': {'name': None, 'suggested': 'Mehmet'}}, flags=flags))
        store.status(mid, 'complete')
        store.close()
        return db, mid, first, second

    def test_naming_says_which_decision_it_was(self):
        with tempfile.TemporaryDirectory() as tmp:
            db, mid, first, second = self.build(tmp)
            dispatch({'action': 'label_speaker', 'meeting': mid, 'speaker': 'Konuşmacı 1', 'name': 'Ali'}, db)
            dispatch({'action': 'label_speaker', 'meeting': mid, 'speaker': 'Konuşmacı 2', 'name': 'Mehmet'}, db)
            store = Store(db)
            self.assertEqual(kinds(store), ['name_correct', 'name_confirm'])
            self.assertEqual([e['scope'] for e in learning.events(store)], ['speaker', 'speaker'])
            store.close()

    def test_a_rejected_suggestion_is_not_a_confirmation(self):
        with tempfile.TemporaryDirectory() as tmp:
            db, mid, first, second = self.build(tmp)
            dispatch({'action': 'label_speaker', 'meeting': mid, 'speaker': 'Konuşmacı 2', 'name': 'Zeynep'}, db)
            store = Store(db); self.assertEqual(kinds(store), ['name_reject']); store.close()

    def test_typing_the_suggestion_without_its_diacritics_still_confirms(self):
        with tempfile.TemporaryDirectory() as tmp:
            db, mid, first, second = self.build(tmp)
            dispatch({'action': 'label_speaker', 'meeting': mid, 'speaker': 'Konuşmacı 1', 'name': 'ayse'}, db)
            store = Store(db); self.assertEqual(kinds(store), ['name_confirm']); store.close()

    def test_undo_points_at_the_naming_it_takes_back(self):
        with tempfile.TemporaryDirectory() as tmp:
            db, mid, first, second = self.build(tmp)
            dispatch({'action': 'label_speaker', 'meeting': mid, 'speaker': 'Konuşmacı 1', 'name': 'Ali'}, db)
            dispatch({'action': 'undo_correction', 'meeting': mid}, db)
            store = Store(db)
            rows = learning.events(store)
            self.assertEqual([r['action'] for r in rows], ['name_correct', 'undo'])
            self.assertEqual(rows[1]['undo_of'], rows[0]['id'])
            self.assertEqual(rows[1]['outcome'], 'reverted')
            store.close()

    def test_teaching_a_word_is_one_event_however_many_segments_it_rewrites(self):
        with tempfile.TemporaryDirectory() as tmp:
            db, mid, first, second = self.build(tmp)
            result = dispatch({'action': 'learn_word', 'meeting': mid, 'original': 'Trendyoll',
                               'replacement': 'Trendyol'}, db)
            self.assertEqual(result['segments'], 2)          # two segments were fixed by the rule…
            store = Store(db)
            self.assertEqual(kinds(store), ['word_teach'])   # …and they are its effects, not two human decisions
            self.assertEqual(learning.events(store)[0]['object'], 'trendyoll')
            store.close()

    def test_the_word_answers_each_leave_their_own_event(self):
        with tempfile.TemporaryDirectory() as tmp:
            db, mid, first, second = self.build(tmp)
            dispatch({'action': 'word_dismiss', 'meeting': mid, 'original': 'Trendyoll'}, db)
            dispatch({'action': 'learn_word', 'meeting': mid, 'original': 'Trendyoll', 'replacement': 'Trendyol'}, db)
            dispatch({'action': 'forget_word', 'original': 'Trendyoll'}, db)
            dispatch({'action': 'accept_rule', 'original': 'Trendyoll'}, db)
            dispatch({'action': 'reject_rule', 'original': 'Trendyoll'}, db)
            store = Store(db)
            self.assertEqual(kinds(store), ['word_dismiss', 'word_teach', 'word_forget', 'review_resolve', 'review_resolve'])
            self.assertEqual([e['outcome'] for e in learning.events(store)][2:],
                             ['reverted', 'applied', 'reverted'])
            store.close()

    def test_the_glossary_answers_are_recorded_once_each(self):
        with tempfile.TemporaryDirectory() as tmp:
            db, mid, first, second = self.build(tmp)
            store = Store(db)
            meta = {'paths': {}, 'glossary_suggestions': [
                {'segment_id': first, 'original': 'görüştük', 'replacement': 'görüştüm', 'source': 'llm'},
                {'segment_id': second, 'original': 'raporu', 'replacement': 'rapor', 'source': 'llm'}]}
            with store.db: store.db.execute('UPDATE meetings SET metadata=? WHERE id=?', (json.dumps(meta), mid))
            store.close()
            dispatch({'action': 'glossary_apply', 'meeting': mid, 'segment': first,
                      'original': 'görüştük', 'replacement': 'görüştüm'}, db)
            dispatch({'action': 'glossary_dismiss', 'meeting': mid, 'segment': second, 'original': 'raporu'}, db)
            store = Store(db)
            self.assertEqual(kinds(store), ['glossary_apply', 'glossary_dismiss'])
            store.close()

    def test_a_written_file_is_an_export_and_a_preview_is_not(self):
        with tempfile.TemporaryDirectory() as tmp:
            db, mid, first, second = self.build(tmp)
            dispatch({'action': 'share_preview', 'meeting': mid}, db)
            store = Store(db); self.assertEqual(kinds(store), []); store.close()
            dispatch({'action': 'share_export', 'meeting': mid, 'path': str(Path(tmp) / 'p.md')}, db)
            dispatch({'action': 'export', 'meeting': mid, 'path': str(Path(tmp) / 'p.json'), 'format': 'json'}, db)
            store = Store(db)
            self.assertEqual(kinds(store), ['export_ok', 'export_ok'])
            self.assertEqual([e['scope'] for e in learning.events(store)], ['meeting', 'meeting'])
            store.close()

    def test_pinning_one_piece_is_a_segment_decision(self):
        with tempfile.TemporaryDirectory() as tmp:
            db, mid, first, second = self.build(tmp)
            dispatch({'action': 'label_segment', 'meeting': mid, 'segment': first, 'name': 'Deniz'}, db)
            store = Store(db)
            row = learning.events(store)[0]
            self.assertEqual((row['action'], row['scope'], row['version']), ('segment_pin', 'segment', str(first)))
            store.close()

    def test_naming_a_plain_segment_is_a_segment_decision_too(self):
        with tempfile.TemporaryDirectory() as tmp:
            db, mid, first, second = self.build(tmp)
            dispatch({'action': 'label', 'meeting': mid, 'segment': second, 'name': 'Deniz'}, db)
            store = Store(db)
            self.assertEqual([(e['action'], e['scope']) for e in learning.events(store)], [('segment_pin', 'segment')])
            store.close()

    def test_joining_a_team_is_recorded_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / 'meeting-os.sqlite'
            Store(db).close()
            token = 'a' * 32
            # No network from a unit test: joining is about the token file and the event, not the first sync.
            with patch('meeting_os.team_cloud.sync', return_value={'error': None}):
                joined = dispatch({'action': 'team_join', 'invite': token}, db)
            self.assertTrue(joined.get('joined'))
            store = Store(db)
            row = learning.events(store)[0]
            self.assertEqual((row['action'], row['scope']), ('team_join', 'global'))
            store.close()

    def test_the_recorder_writes_a_start_and_a_stop(self):
        from meeting_os import live
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / 'meeting-os.sqlite'
            store = Store(db)
            with self.assertRaises(Exception):
                live.record('/nonexistent/capture-binary', Path(tmp) / 'cap', 1, 12, store=store,
                            title='Kayıt', data_dir=Path(tmp))
            rows = learning.events(store)
            self.assertEqual([r['action'] for r in rows], ['record_start', 'record_stop'])
            self.assertEqual(rows[1]['outcome'], 'noop')        # the helper never started: nothing was captured
            self.assertEqual(rows[0]['object'], rows[1]['object'])
            store.close()


class HumanVersusAutomaticTests(unittest.TestCase):
    def test_an_untouched_automatic_name_is_unreviewed_not_a_success(self):
        from meeting_os.quality import identity_report
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / 'db')
            mid = store.create_meeting('Q', {'paths': {}})
            flags = ['cloud_transcript', 'cloud_diarization']
            store.add_segment(mid, Segment(0, 4, 'bir', 'system', 'Konuşmacı 1', 'Ayşe',
                                           metrics={'cluster': '0:0', 'identity': {'name': 'Ayşe'}}, flags=flags))
            store.add_segment(mid, Segment(4, 8, 'iki', 'system', 'Konuşmacı 2', 'Mehmet',
                                           metrics={'cluster': '0:1', 'identity': {'name': 'Mehmet'}}, flags=flags))
            store.add_segment(mid, Segment(8, 12, 'üç', 'system', 'Konuşmacı 3', 'Deniz',
                                           metrics={'cluster': '0:2', 'identity': {'name': 'Deniz'}}, flags=flags))
            store.status(mid, 'complete')
            # Nobody has looked at any of them: three guesses, zero evidence either way.
            first = identity_report(store)
            self.assertEqual((first['auto_verified'], first['auto_falsified'], first['auto_unreviewed']), (0, 0, 3))
            self.assertIsNone(first['auto_precision'])
            store.correct(mid, 'Konuşmacı 1', 'Ayşe')       # confirmed by hand
            store.correct(mid, 'Konuşmacı 2', 'Selin')      # overruled by hand
            second = identity_report(store)
            self.assertEqual((second['auto_verified'], second['auto_falsified'], second['auto_unreviewed']), (1, 1, 1))
            self.assertEqual(second['auto_precision'], 0.5)
            self.assertEqual(second['clusters'], 3)
            store.close()

    def test_a_word_taught_from_the_transcript_reaches_the_quality_set(self):
        from meeting_os import correction_memory as cm
        from meeting_os.quality import reference_set
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / 'db')
            mid = store.create_meeting('Q', {'model': 'microsoft/mai-transcribe-2', 'paths': {}})
            sid = store.add_segment(mid, Segment(0, 4, 'Trendyoll ile görüştük.', 'system', 'S0'))
            store.status(mid, 'complete')
            self.assertEqual(reference_set(store), [])
            cm.teach(store, mid, 'Trendyoll', 'Trendyol', Path(tmp))
            refs = reference_set(store)
            self.assertEqual(len(refs), 1)
            self.assertEqual((refs[0]['segment'], refs[0]['via']), (sid, 'word_teach'))
            self.assertEqual(refs[0]['model_text'], 'Trendyoll ile görüştük.')
            self.assertEqual(refs[0]['reference'], 'Trendyol ile görüştük.')
            self.assertGreater(refs[0]['wer'], 0)
            # The same segment retyped by hand afterwards is still ONE reference: the typed text is the last word.
            store.correct_text(mid, sid, 'Trendyol ile görüştüm.')
            refs = reference_set(store)
            self.assertEqual([(r['segment'], r['via']) for r in refs], [(sid, 'text_edit')])
            store.close()

    def test_the_heartbeat_carries_the_numbers_and_nothing_else(self):
        from meeting_os import reports
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp); store = Store(data / 'meeting-os.sqlite')
            learning.record_event(store, 'word_teach', object='trendyol', scope='global')
            learning.record_event(store, 'task_edit', object='task-1')
            beat = reports.build_heartbeat(store, data, app={'version': '1.2.80'})
            self.assertEqual(beat['learning']['actions'], {'word_teach': 1, 'task_edit': 1})
            self.assertEqual(beat['learning']['events'], 2)
            self.assertEqual(beat['learning']['names'], {'verified': 0, 'falsified': 0, 'unreviewed': 0})
            self.assertNotIn('trendyol', json.dumps(beat['learning'], ensure_ascii=False))
            self.assertNotIn('task-1', json.dumps(beat['learning'], ensure_ascii=False))
            store.close()


class TaskHistoryTests(unittest.TestCase):
    def task(self, store, title='Aylık bütçe raporunu müşteriye gönder', owner='Ayşe', quote='raporu yollayacağım'):
        mid = store.create_meeting('T', {'paths': {}})
        sid = store.add_segment(mid, Segment(0, 4, quote, 'system', 'S0'))
        store.status(mid, 'complete')
        memory = Memory(store)
        record = {'summary': [], 'decisions': [], 'risks': [], 'questions': [],
                  'actions': [{'title': title, 'owner': owner, 'due_text': 'yarın',
                               'evidence': [{'segment_id': sid, 'quote': quote, 'start': 0.0}]}]}
        memory.save_analysis(mid, memory.current_hash(mid), 'test-model', record)
        return memory, mid, sid, memory.actions(meeting=mid)[0]['id']

    def test_confirming_a_calendar_date_writes_the_same_history_row_as_every_other_field(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / 'db')
            memory, mid, sid, tid = self.task(store)
            self.assertEqual(memory.task_history(tid), [])
            memory.set_due_date(tid, '2026-09-20')
            memory.set_due_date(tid, '2026-09-25', 'changed_later')
            memory.set_due_date(tid, None, 'inference_error')
            rows = memory.task_history(tid)
            self.assertEqual([r['field'] for r in rows], ['due_date'] * 3)
            self.assertEqual([r['reason'] for r in rows], [None, 'changed_later', 'inference_error'])
            self.assertEqual([json.loads(r['replacement'])['due_date'] for r in rows],
                             ['2026-09-20', '2026-09-25', None])
            self.assertEqual(json.loads(rows[1]['previous'])['due_date'], '2026-09-20')   # what it was before
            store.close()

    def test_the_reason_is_optional_and_only_the_two_answers_are_accepted(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / 'db')
            memory, mid, sid, tid = self.task(store)
            memory.update_action(tid, {'owner': 'Mehmet'}, 'inference_error')
            memory.update_action(tid, {'due_text': 'gelecek hafta'})
            with self.assertRaises(ValueError): memory.update_action(tid, {'owner': 'Ali'}, 'çok geç oldu')
            rows = memory.task_history(tid)
            self.assertEqual([r['reason'] for r in rows], ['inference_error', None])
            self.assertEqual([r['field'] for r in rows], ['owner', 'due_text'])
            store.close()

    def test_the_bridge_carries_the_reason_through(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / 'meeting-os.sqlite'
            store = Store(db)
            memory, mid, sid, tid = self.task(store)
            store.close()
            dispatch({'action': 'action_update', 'task': tid, 'changes': {'owner': 'Mehmet'},
                      'reason': 'inference_error'}, db)
            dispatch({'action': 'task_set_due', 'task': tid, 'due_date': '2026-10-01',
                      'reason': 'changed_later'}, db)
            store = Store(db); memory = Memory(store)
            self.assertEqual([r['reason'] for r in memory.task_history(tid)], ['inference_error', 'changed_later'])
            self.assertEqual(kinds(store), ['task_edit', 'task_due'])
            store.close()

    def test_history_follows_a_task_a_re_analysis_renamed(self):
        """The id is the hash of the title and its quotes, so rewording the same commitment makes a new task.
        The user's edits used to stay behind on an id nobody looks at again."""
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / 'db')
            memory, mid, sid, tid = self.task(store)
            memory.update_action(tid, {'owner': 'Mehmet'}, 'inference_error')
            record = {'summary': [], 'decisions': [], 'risks': [], 'questions': [],
                      'actions': [{'title': 'Aylık bütçe raporunu müşteriye hemen gönder', 'owner': 'Mehmet', 'due_text': 'yarın',
                                   'evidence': [{'segment_id': sid, 'quote': 'raporu yollayacağım', 'start': 0.0}]}]}
            memory.save_analysis(mid, memory.current_hash(mid), 'test-model', record)
            fresh = [t for t in memory.actions(meeting=mid) if t['id'] != tid]
            self.assertEqual(len(fresh), 1)
            carried = memory.task_history(fresh[0]['id'])
            self.assertEqual([r['carried_from'] for r in carried], [tid])
            self.assertEqual(carried[0]['reason'], 'inference_error')
            # Saving the same analysis again must not copy the history a second time.
            memory.save_analysis(mid, memory.current_hash(mid), 'test-model', record)
            self.assertEqual(len(memory.task_history(fresh[0]['id'])), 1)
            store.close()

    def test_a_different_commitment_does_not_inherit_somebody_elses_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / 'db')
            memory, mid, sid, tid = self.task(store)
            memory.update_action(tid, {'owner': 'Mehmet'})
            record = {'summary': [], 'decisions': [], 'risks': [], 'questions': [],
                      'actions': [{'title': 'Sunumu hazırla ve ekiple paylaş', 'owner': 'Mehmet', 'due_text': '',
                                   'evidence': [{'segment_id': sid, 'quote': 'raporu yollayacağım', 'start': 0.0}]}]}
            memory.save_analysis(mid, memory.current_hash(mid), 'test-model', record)
            fresh = [t for t in memory.actions(meeting=mid) if t['id'] != tid]
            self.assertEqual([memory.task_history(t['id']) for t in fresh], [[]] * len(fresh))
            store.close()


if __name__ == '__main__':
    unittest.main()
