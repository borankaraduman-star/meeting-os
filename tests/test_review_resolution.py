"""1.2.81 — a Kontrol item can be closed, and closing it means something.

Every queue item carries the version of the source it was derived from. An answer is stored against that
version: answered → never asked again; the transcript or the analysis changes underneath → asked again,
because it is genuinely a new question. "Geç" hides an item for one version and is counted on its own — a
queue made shorter by skipping has not got better, and these tests are what keeps the two apart.
"""
import tempfile
import unittest
from pathlib import Path

from meeting_os.desktop import dispatch
from meeting_os.memory import Memory
from meeting_os.review import queue_key, resolve_review, review_debt, review_queue
from meeting_os.store import Store
from meeting_os.types import Segment

FLAGS = ['cloud_transcript', 'cloud_diarization']


def meeting(tmp):
    """Two voices the queue has questions about: one it can suggest a name for, one it cannot."""
    store = Store(Path(tmp) / 'meeting-os.sqlite')
    mid = store.create_meeting('Sprint', {})
    ident = {'name': None, 'candidate': 'Ayşe', 'similarity': 0.85, 'suggested': 'Ayşe'}
    store.add_segment(mid, Segment(0, 20, 'uzun bir açılış', 'system', 'Konuşmacı 1', metrics={'cluster': '0:0', 'identity': ident}, flags=FLAGS))
    store.add_segment(mid, Segment(25, 40, 'isimsiz konuşma', 'system', 'Konuşmacı 2', metrics={'cluster': '0:1', 'identity': {'name': None, 'candidate': 'Mehmet', 'similarity': 0.7, 'suggested': None}}, flags=FLAGS))
    store.status(mid, 'complete')
    return store, mid


def kinds(queue):
    return [i['kind'] for i in queue['items']]


class ResolutionTests(unittest.TestCase):
    def test_an_answered_item_does_not_come_back_for_the_same_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            store, mid = meeting(tmp)
            first = review_queue(store, mid)
            item = first['items'][0]
            self.assertTrue(item['key'] and item['source_version'])
            resolve_review(store, mid, item['key'], item['kind'], item['source_version'], 'correct')
            after = review_queue(store, mid)
            self.assertNotIn(item['key'], [i['key'] for i in after['items']])
            self.assertEqual(after['count'], first['count'] - 1)
            self.assertEqual(after['resolved'], 1)
            self.assertEqual(after['skipped'], 0)
            store.close()

    def test_a_changed_source_asks_again(self):
        with tempfile.TemporaryDirectory() as tmp:
            store, mid = meeting(tmp)
            item = review_queue(store, mid)['items'][0]
            resolve_review(store, mid, item['key'], item['kind'], item['source_version'], 'correct')
            self.assertNotIn(item['key'], [i['key'] for i in review_queue(store, mid)['items']])
            seg = store.display_segments(mid)[1]['id']
            store.correct_text(mid, seg, 'isimsiz konuşma düzeltildi')   # the transcript is not what it was
            back = review_queue(store, mid)
            self.assertIn(item['key'], [i['key'] for i in back['items']])
            self.assertEqual(back['resolved'], 0)   # the old answer belongs to the old text, and says so
            store.close()

    def test_skipped_hides_the_item_but_is_never_counted_as_confirmation(self):
        with tempfile.TemporaryDirectory() as tmp:
            store, mid = meeting(tmp)
            items = review_queue(store, mid)['items']
            resolve_review(store, mid, items[0]['key'], items[0]['kind'], items[0]['source_version'], 'skipped')
            resolve_review(store, mid, items[1]['key'], items[1]['kind'], items[1]['source_version'], 'correct')
            queue = review_queue(store, mid)
            self.assertEqual(queue['count'], 0)
            self.assertEqual(queue['skipped'], 1)
            self.assertEqual(queue['resolved'], 1)   # counted apart: passing on an item is not an approval
            store.close()

    def test_an_answer_can_be_changed_and_taken_back(self):
        with tempfile.TemporaryDirectory() as tmp:
            store, mid = meeting(tmp)
            db = Path(store.path)
            item = review_queue(store, mid)['items'][0]
            store.close()
            dispatch({'action': 'review_resolve', 'meeting': mid, 'key': item['key'], 'kind': item['kind'], 'source_version': item['source_version'], 'result': 'skipped'}, db)
            dispatch({'action': 'review_resolve', 'meeting': mid, 'key': item['key'], 'kind': item['kind'], 'source_version': item['source_version'], 'result': 'corrected'}, db)
            queue = dispatch({'action': 'review_queue', 'meeting': mid}, db)
            self.assertEqual(queue['skipped'], 0)
            self.assertEqual(queue['resolved'], 1)
            dispatch({'action': 'review_reopen', 'meeting': mid, 'key': item['key']}, db)
            self.assertIn(item['key'], [i['key'] for i in dispatch({'action': 'review_queue', 'meeting': mid}, db)['items']])

    def test_only_the_three_results_are_accepted(self):
        with tempfile.TemporaryDirectory() as tmp:
            store, mid = meeting(tmp)
            item = review_queue(store, mid)['items'][0]
            with self.assertRaises(ValueError): resolve_review(store, mid, item['key'], item['kind'], item['source_version'], 'belki')
            with self.assertRaises(ValueError): resolve_review(store, mid, '', item['kind'], item['source_version'], 'correct')
            store.close()

    def test_the_key_ignores_the_wording_of_the_reason(self):
        base = {'kind': 'unnamed_speaker', 'speaker_key': 'Konuşmacı 2', 'segment_id': 4, 'reason': 'İsimsiz konuşmacı, toplam 15 sn'}
        self.assertEqual(queue_key(base), queue_key({**base, 'reason': 'İsimsiz konuşmacı, toplam 16 sn', 'severity': 1}))
        self.assertNotEqual(queue_key(base), queue_key({**base, 'speaker_key': 'Konuşmacı 3'}))

    def test_the_weekly_debt_reports_what_was_answered(self):
        with tempfile.TemporaryDirectory() as tmp:
            store, mid = meeting(tmp)
            item = review_queue(store, mid)['items'][0]
            resolve_review(store, mid, item['key'], item['kind'], item['source_version'], 'correct')
            debt = review_debt(store, days=7)
            self.assertEqual(debt['resolved'], 1)
            self.assertNotIn(item['key'], [i['key'] for i in debt['items']])
            store.close()


class TaskReviewTests(unittest.TestCase):
    def record(self, needs_review, owner='Deniz'):
        return {'summary': [], 'decisions': [], 'risks': [], 'questions': [], 'dropped_quotes': 0, 'dropped_items': 0,
                'actions': [{'title': 'Fatura ekranını düzelt', 'owner': owner, 'due_text': 'cuma',
                             'needs_review': needs_review, 'evidence': [{'segment_id': 1, 'quote': 'uzun bir açılış', 'start': 0.0}]}]}

    def test_a_flagged_task_with_an_owner_enters_the_queue(self):
        with tempfile.TemporaryDirectory() as tmp:
            store, mid = meeting(tmp)
            mem = Memory(store)
            mem.save_analysis(mid, mem.current_hash(mid), 'test', self.record(True))
            queue = review_queue(store, mid)
            flagged = [i for i in queue['items'] if i['kind'] == 'task_review']
            self.assertEqual(len(flagged), 1)
            self.assertIn('Deniz', flagged[0]['reason'])
            self.assertTrue(flagged[0]['source_version'].startswith('a:'))   # its source is the analysis, not the text
            store.close()

    def test_a_task_nobody_doubts_is_not_a_question(self):
        with tempfile.TemporaryDirectory() as tmp:
            store, mid = meeting(tmp)
            mem = Memory(store)
            mem.save_analysis(mid, mem.current_hash(mid), 'test', self.record(False))
            self.assertNotIn('task_review', kinds(review_queue(store, mid)))
            store.close()

    def test_a_flagged_task_resolves_and_stays_resolved_until_a_new_analysis(self):
        with tempfile.TemporaryDirectory() as tmp:
            store, mid = meeting(tmp)
            mem = Memory(store)
            mem.save_analysis(mid, mem.current_hash(mid), 'test', self.record(True))
            item = [i for i in review_queue(store, mid)['items'] if i['kind'] == 'task_review'][0]
            resolve_review(store, mid, item['key'], item['kind'], item['source_version'], 'correct')
            self.assertNotIn('task_review', kinds(review_queue(store, mid)))
            mem.save_analysis(mid, mem.current_hash(mid), 'test', self.record(True))   # a new analysis is a new source
            self.assertIn('task_review', kinds(review_queue(store, mid)))
            store.close()

    def test_a_task_with_no_owner_stays_the_owner_question_it_was(self):
        with tempfile.TemporaryDirectory() as tmp:
            store, mid = meeting(tmp)
            mem = Memory(store)
            mem.save_analysis(mid, mem.current_hash(mid), 'test', self.record(True, owner=None))
            got = kinds(review_queue(store, mid))
            self.assertIn('task_owner', got)
            self.assertNotIn('task_review', got)
            store.close()


class MetricsHookTests(unittest.TestCase):
    def test_resolving_an_item_is_offered_to_the_metrics_recorder(self):
        import meeting_os.review as R
        seen = []
        with tempfile.TemporaryDirectory() as tmp:
            store, mid = meeting(tmp)
            item = review_queue(store, mid)['items'][0]
            was = R.record_event
            R.record_event = lambda store, action, **fields: seen.append((action, fields.get('object'), fields.get('outcome')))
            try: resolve_review(store, mid, item['key'], item['kind'], item['source_version'], 'skipped')
            finally: R.record_event = was
            self.assertEqual(seen, [('review_resolve', item['key'], 'skipped')])
            store.close()


if __name__ == '__main__':
    unittest.main()
