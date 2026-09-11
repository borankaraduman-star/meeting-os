"""1.2.86 #9 — learn the SHAPE of a task error, never the person it happened to.

What these guard:

1. A correction the user called "çıkarım hatası" lands in one fixed class, read off the task's own
   evidence: reported speech, a conditional, a mic echo, a misread date, an owner attribution.
2. A change with no reason, or one marked "sonradan değişti", is never counted at all.
3. The adaptation needs BOTH bars (≥5 in 30 days AND ≥30 % of them), and its only effect is one more
   `needs_review`: no owner is ever rewritten, and no rule is ever about a named person.
4. The distribution travels as counts — through `learning.summary`, the daily summary and the whitelist.
5. The offline benchmark reports owner/due mismatches AND recall/precision, because the acceptance rule
   for this iteration is the pair, not either one alone.
"""
import importlib.util
import json
import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from meeting_os import learning, quality, telemetry_schema
from meeting_os import task_errors as TE
from meeting_os.intelligence import validate_record
from meeting_os.memory import Memory
from meeting_os.store import Store
from meeting_os.types import Segment

ROOT = Path(__file__).resolve().parents[1]

REPORTED = 'Deniz dedi ki, ben deploy işini üstleneceğim.'
CONDITIONAL = 'Testler geçerse ben raporu cuma günü göndereceğim.'
PLAIN = 'Ben onboarding metinlerini yarın yazacağım.'


def evidence(text, source='system'):
    return [{'segment_id': 1, 'quote': text, 'start': 0.0, 'source': source, 'speaker': 'Boran'}]


class ClassifyTests(unittest.TestCase):
    def test_a_reported_commitment_is_its_own_class(self):
        self.assertEqual(TE.classify('owner', evidence(REPORTED)), 'reported_speech')
        self.assertEqual(TE.classify('due_text', evidence('Ece söyledi, raporu perşembe göndereceğim.')), 'reported_speech')

    def test_a_conditional_promise_reuses_the_existing_doubt_test(self):
        self.assertEqual(TE.classify('owner', evidence(CONDITIONAL)), 'conditional')
        self.assertEqual(TE.classify('owner', evidence('Bu işi Deniz yapsın.')), 'conditional')

    def test_a_microphone_row_is_an_echo_only_when_the_owner_moved(self):
        self.assertEqual(TE.classify('owner', evidence(PLAIN, source='mic')), 'mic_echo')
        self.assertEqual(TE.classify('owner,due_text', evidence(PLAIN, source='mic')), 'mic_echo')
        # a misread date on a mic-recorded task is a date error, not an echo
        self.assertEqual(TE.classify('due_date', evidence(PLAIN, source='mic')), 'date_parse')
        self.assertEqual(TE.classify('owner', evidence(PLAIN), flags=['possible_echo']), 'mic_echo')

    def test_the_date_and_owner_fields_name_their_own_classes(self):
        self.assertEqual(TE.classify('due_date', evidence(PLAIN)), 'date_parse')
        self.assertEqual(TE.classify('due_text', evidence(PLAIN)), 'date_parse')
        self.assertEqual(TE.classify('owner', evidence(PLAIN)), 'owner_attribution')
        self.assertEqual(TE.classify('title', evidence(PLAIN)), 'other')
        self.assertEqual(TE.classify('', []), 'other')

    def test_a_new_item_belongs_to_every_class_its_evidence_exposes_it_to(self):
        item = {'title': 'Raporu gönder', 'owner': 'Deniz', 'due_text': 'cuma günü', 'evidence': evidence(REPORTED)}
        self.assertEqual(TE.item_classes(item), {'reported_speech', 'date_parse', 'owner_attribution'})
        bare = {'title': 'Raporu gönder', 'owner': None, 'due_text': None, 'evidence': evidence(PLAIN)}
        self.assertEqual(TE.item_classes(bare), set())


def meeting_with_task(store, title=None, text=PLAIN, owner='Boran', due='yarın', source='mic'):
    """A complete meeting with exactly one saved task, cited from its own sentence.

    The title is the tail of that sentence so it shares content words with the quote — `validate_record`
    drops an item whose claim appears in none of its evidence, which is its job, not this test's subject."""
    title = title or ' '.join(text.split()[-3:]).rstrip('.')
    mid = store.create_meeting('Sprint', {})
    sid = store.add_segment(mid, Segment(0.0, 8.0, text, source, 'mic:S0' if source == 'mic' else 'S0', 'Boran'))
    store.status(mid, 'complete')
    mem = Memory(store)
    rows = store.display_segments(mid)
    record = validate_record({'summary': [], 'decisions': [], 'risks': [], 'questions': [],
                              'actions': [{'title': title, 'owner': owner, 'due_text': due,
                                           'evidence': [{'segment_id': sid, 'quote': text}]}]}, rows, mic_owner='Boran')
    mem.save_analysis(mid, mem.current_hash(mid), 'test', record)
    return mem, mem.actions()[0]['id']


class CountingTests(unittest.TestCase):
    def test_only_what_the_user_called_a_model_error_is_counted(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / 'meeting-os.sqlite')
            mem, tid = meeting_with_task(store)
            mem.update_action(tid, {'owner': 'Ece'}, reason='inference_error')
            mem.update_action(tid, {'owner': 'Deniz'}, reason='changed_later')
            mem.update_action(tid, {'owner': 'Can'})                      # no reason: never a training label
            counts = TE.counts(store)
            self.assertEqual(counts['total'], 1)
            self.assertEqual(counts['classes']['mic_echo'], 1)
            self.assertEqual(counts['unreasoned'], 1)
            store.close()

    def test_a_calendar_date_correction_is_a_date_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / 'meeting-os.sqlite')
            mem, tid = meeting_with_task(store)
            mem.set_due_date(tid, '2026-09-20', reason='inference_error')
            self.assertEqual(TE.counts(store)['classes']['date_parse'], 1)
            store.close()

    def test_an_old_error_leaves_the_window(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / 'meeting-os.sqlite')
            mem, tid = meeting_with_task(store)
            mem.update_action(tid, {'owner': 'Ece'}, reason='inference_error')
            old = (datetime.now(timezone.utc) - timedelta(days=120)).isoformat()
            with store.db:
                store.db.execute('UPDATE task_edits SET created=?', (old,))
            self.assertEqual(TE.counts(store)['total'], 0)
            self.assertEqual(TE.counts(store, days=200)['total'], 1)
            store.close()

    def test_a_store_without_the_reason_column_counts_nothing_and_does_not_raise(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / 'meeting-os.sqlite')
            self.assertEqual(TE.counts(store)['total'], 0)
            store.close()


def errors(store, mem, tid, n, reason='inference_error'):
    for i in range(n):
        mem.update_action(tid, {'owner': f'Kişi{i}'}, reason=reason)


class AdaptationTests(unittest.TestCase):
    def make(self, tmp, n, text=REPORTED, source='system'):
        store = Store(Path(tmp) / 'meeting-os.sqlite')
        mem, tid = meeting_with_task(store, text=text, source=source, owner=None, due=None)
        errors(store, mem, tid, n)
        return store

    def test_both_bars_have_to_be_cleared(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = self.make(tmp, 4)
            self.assertEqual(TE.review_classes(store), ())      # four is not yet five
            store.close()
        with tempfile.TemporaryDirectory() as tmp:
            store = self.make(tmp, 5)
            self.assertEqual(TE.review_classes(store), ('reported_speech',))
            self.assertEqual(TE.review_classes(store, min_errors=99), ())
            store.close()

    def test_a_class_below_the_share_bar_is_not_a_pattern(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / 'meeting-os.sqlite')
            mem, reported = meeting_with_task(store, text=REPORTED, source='system', owner=None, due=None)
            errors(store, mem, reported, 5)
            _, dated = meeting_with_task(store, text=PLAIN, owner=None, due=None)
            for i in range(15):
                mem.update_action(dated, {'due_text': f'{i}. gün'}, reason='inference_error')
            window = TE.counts(store, days=TE.WINDOW_DAYS)
            self.assertEqual((window['classes']['reported_speech'], window['classes']['date_parse']), (5, 15))
            # five is enough on its own, but a quarter of the errors is not the thing going wrong
            self.assertEqual(TE.review_classes(store), ('date_parse',))
            store.close()

    def test_the_only_effect_is_one_more_review_and_never_a_changed_owner(self):
        rows = [{'id': 1, 'start': 0., 'end': 8., 'source': 'system', 'speaker': 'S0', 'speaker_name': 'Deniz',
                 'text': REPORTED, 'flags': []}]
        claim = {'summary': [], 'decisions': [], 'risks': [], 'questions': [],
                 'actions': [{'title': 'Deploy işini üstlen', 'owner': 'Deniz', 'due_text': None,
                              'evidence': [{'segment_id': 1, 'quote': REPORTED}]}]}
        plain = validate_record(json.loads(json.dumps(claim)), rows)['actions'][0]
        flagged = validate_record(json.loads(json.dumps(claim)), rows, review_classes=('reported_speech',))['actions'][0]
        self.assertEqual(plain['owner'], flagged['owner'])           # the class NEVER moves an owner
        self.assertEqual(plain['title'], flagged['title'])
        self.assertTrue(flagged['needs_review'])
        # an item of another class is untouched by this class being active
        other = {'summary': [], 'decisions': [], 'risks': [], 'questions': [],
                 'actions': [{'title': 'Onboarding metinlerini yaz', 'owner': None, 'due_text': None,
                              'evidence': [{'segment_id': 2, 'quote': 'Ben onboarding metinlerini yazacağım.'}]}]}
        plain_rows = [{'id': 2, 'start': 0., 'end': 8., 'source': 'system', 'speaker': 'S0', 'speaker_name': None,
                       'text': 'Ben onboarding metinlerini yazacağım.', 'flags': []}]
        self.assertFalse(validate_record(other, plain_rows, review_classes=('reported_speech',))['actions'][0]['needs_review'])

    def test_no_rule_is_ever_about_a_person(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = self.make(tmp, 6)
            blob = json.dumps(TE.measure(store), ensure_ascii=False)
            for name in ('Deniz', 'Boran', 'Kişi0', 'Kişi1', 'Raporu'):
                self.assertNotIn(name, blob)
            store.close()


class FileTests(unittest.TestCase):
    def test_the_measurement_is_written_once_a_day_and_only_known_classes_are_obeyed(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / 'meeting-os.sqlite')
            mem, tid = meeting_with_task(store, text=REPORTED, source='system', owner=None, due=None)
            errors(store, mem, tid, 5)
            data = Path(tmp)
            first = TE.refresh(store, data)
            self.assertTrue(first['fresh'])
            self.assertEqual(TE.active_classes(data), ('reported_speech',))
            self.assertFalse(TE.refresh(store, data)['fresh'])
            later = datetime.now(timezone.utc) + timedelta(hours=30)
            self.assertTrue(TE.refresh(store, data, now=later)['fresh'])
            TE.save(data, {**TE.load(data), 'review': ['uydurma_sınıf', 'other']})
            self.assertEqual(TE.active_classes(data), ())   # an unknown name never reaches the analysis
            self.assertIn('başkasının sözünü aktarma', TE.line(TE.load(data)))
            store.close()

    def test_a_missing_file_asks_for_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(TE.active_classes(Path(tmp)), ())
            self.assertIn('kayıtlı çıkarım hatası yok', TE.line(TE.load(Path(tmp))))


class ReportingTests(unittest.TestCase):
    def test_the_distribution_travels_as_counts_and_passes_the_whitelist(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / 'meeting-os.sqlite')
            mem, tid = meeting_with_task(store, text=REPORTED, source='system', owner=None, due=None)
            errors(store, mem, tid, 3)
            summary = learning.summary(store, days=7, data_dir=Path(tmp))
            self.assertEqual(summary['task_errors']['classes']['reported_speech'], 3)
            self.assertEqual(summary['task_errors']['total'], 3)
            cleaned = telemetry_schema.filter('heartbeat', {'learning': summary})
            self.assertEqual(cleaned['learning']['task_errors']['classes']['reported_speech'], 3)
            store.close()

    def test_the_daily_summary_carries_one_rate_per_class(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / 'meeting-os.sqlite')
            mem, tid = meeting_with_task(store, text=REPORTED, source='system', owner=None, due=None)
            errors(store, mem, tid, 2)
            record = quality.daily_summary(store, Path(tmp), save=False)
            metrics = record['metrics']
            self.assertEqual(metrics['task_error_reported_speech'], {'n': 2, 'd': 2, 'rate': 1.0})
            self.assertEqual(metrics['task_error_owner_attribution'], {'n': 0, 'd': 2, 'rate': 0.0})
            store.close()

    def test_a_day_with_no_model_error_claims_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / 'meeting-os.sqlite')
            meeting_with_task(store)
            record = quality.daily_summary(store, Path(tmp), save=False)
            self.assertIsNone(record['metrics']['task_error_other']['rate'])
            store.close()


def bench():
    spec = importlib.util.spec_from_file_location('bench', ROOT / 'scripts/benchmark-analysis-cloud.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


CASE = {'expected_action_fields': [{'title_terms': ['PRD'], 'owner': 'Boran', 'due_text': 'yarın'},
                                   {'title_terms': ['kabul', 'kriter'], 'owner': 'Ece', 'due_text': 'cuma gününe kadar'},
                                   {'title_terms': ['test', 'senaryo'], 'owner': None, 'due_text': None}]}


class BenchmarkOfflineTests(unittest.TestCase):
    """The offline half of the cloud benchmark: no request is made by any of these."""

    def test_owner_and_due_mismatches_are_reported_next_to_recall(self):
        module = bench()
        result = {'actions': [{'title': 'PRD taslağını hazırla', 'owner': 'Boran', 'due_text': 'yarın'},
                              {'title': 'kabul kriterlerini yaz', 'owner': 'Can', 'due_text': 'cuma gününe kadar'},
                              {'title': 'test senaryolarını hazırla', 'owner': None, 'due_text': 'pazartesi'},
                              {'title': 'uydurulmuş bir iş', 'owner': None, 'due_text': None}]}
        stats = module.accuracy(result, CASE)
        self.assertEqual((stats['expected'], stats['found'], stats['recall']), (3, 3, 1.0))
        self.assertEqual(stats['owner_mismatch'], 1)      # Can instead of Ece
        self.assertEqual(stats['due_mismatch'], 1)        # the undated task came back with a date
        self.assertEqual(stats['precision'], 0.75)        # one invented task out of four

    def test_abstaining_from_every_owner_does_not_look_like_accuracy(self):
        module = bench()
        silent = {'actions': [{'title': t, 'owner': None, 'due_text': None}
                              for t in ('PRD taslağı', 'kabul kriterleri', 'test senaryoları')]}
        stats = module.accuracy(silent, CASE)
        self.assertEqual(stats['owner_mismatch'], 2)          # abstention is still a mismatch…
        self.assertEqual(stats['owner_abstained'], 2)         # …and it is counted as its own thing
        self.assertEqual(stats['recall'], 1.0)                # while recall stays visible next to it

    def test_missing_tasks_lower_recall_and_totals_pool_numerators(self):
        module = bench()
        stats = module.accuracy({'actions': [{'title': 'PRD taslağı', 'owner': 'Boran', 'due_text': 'yarın'}]}, CASE)
        self.assertEqual((stats['found'], stats['recall'], stats['owner_mismatch']), (1, 0.333, 0))
        pooled = module.totals([{'accuracy': stats}, {'accuracy': stats}, {'error': 'boom'}])
        self.assertEqual((pooled['expected'], pooled['found'], pooled['recall']), (6, 2, 0.333))
        self.assertEqual((pooled['cases'], pooled['failed_cases']), (2, 1))
        self.assertIsNone(module.totals([])['recall'])

    def test_the_prefs_flag_can_only_inject_the_fixed_template(self):
        module = bench()
        self.assertEqual(module.parse_prefs(None), {})
        self.assertEqual(module.parse_prefs('detail=kısa,bullet_length=uzun'), {'detail': 'kısa', 'bullet_length': 'uzun'})
        self.assertEqual(module.parse_prefs('detail=Gizli müşteri Zebra'), {})   # free text cannot enter a prompt
        self.assertEqual(module.parse_prefs('bilinmeyen=kısa'), {})
        from meeting_os.intelligence import preference_line
        self.assertIn('Kullanıcı tercihi', preference_line(module.parse_prefs(module.PREFS_DEFAULT)))


if __name__ == '__main__':
    unittest.main()
