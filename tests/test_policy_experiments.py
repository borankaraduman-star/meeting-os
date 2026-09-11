"""1.2.85 — Deney ve geri dönüş: a versioned local policy, silent offline experiments, and one step back.

The four questions these tests exist to answer are the four the review made non-negotiable (Codex,
11 Sep 2026, #11 and "kaynak ve saklama sınırı"):

1. Does a promotion actually reach production, and does `rollback` actually undo it — including the FIRST
   one, where there is no earlier policy version to go back to?
2. Is the precedence one order and only one order: policy, then settings, then the shipped constants?
3. Can an experiment run at a moment it must not — while recording, while a job is in flight, twice in a
   day — or on evidence too thin to carry the claim?
4. Does an experiment leave production data exactly as it found it, and is a queue item the user never
   answered kept out of the scoring entirely?
"""
import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from meeting_os import experiments as E
from meeting_os import learning
from meeting_os import policy as P
from meeting_os import quality, reports, review
from meeting_os.cloud_finalize import IDENTITY_MARGIN, IDENTITY_THRESHOLD, identity_bars
from meeting_os.store import Store

NOW = datetime(2026, 9, 11, 9, 0, tzinfo=timezone.utc)


def fresh(tmp):
    data = Path(tmp)
    return data, Store(data/'meeting-os.sqlite')


def meeting(store, mid, created, status='complete'):
    with store.db:
        store.db.execute('INSERT INTO meetings VALUES(?,?,?,?,?)', (mid, mid, created, status, '{}'))


def answer(store, mid, key, kind, result):
    review.ensure_results(store)
    with store.db:
        store.db.execute('INSERT INTO review_results(meeting,item_key,kind,source_version,result,created) VALUES(?,?,?,?,?,?)',
                         (mid, key, kind, 't:v1', result, NOW.isoformat()))


def recency_wins(store):
    """A history where ordering by recency really would have put the work first: two old meetings full of
    easy items the user confirmed, and today's meeting full of low-severity items the user CORRECTED.

    Severity-first buries today's corrections behind 28 answered markers and name suggestions; recency-first
    puts them at the top. The numbers are the point — 36 answered items, well over the n≥20 bar."""
    for index, mid in enumerate(('old-a', 'old-b')):
        meeting(store, mid, f'2026-09-0{index+1}T09:00:00+00:00')
        for i in range(14):
            answer(store, mid, f'marker:{i}', 'marker', 'correct')
    meeting(store, 'today', '2026-09-10T09:00:00+00:00')
    for i in range(8):
        answer(store, 'today', f'asr:{i}', 'asr', 'corrected')


class PolicyPrecedenceTests(unittest.TestCase):
    """Codex #11: one order, written down once. Anything else and two files quietly disagree about what the
    app is doing, which is the state this whole version exists to end."""

    def test_no_policy_and_no_settings_is_the_shipped_constant(self):
        with tempfile.TemporaryDirectory() as tmp:
            data, _ = fresh(tmp)
            self.assertEqual(P.current(data)['source'], 'default')
            self.assertEqual(identity_bars(data), (IDENTITY_THRESHOLD, IDENTITY_MARGIN))
            self.assertEqual(P.review_order(data), 'severity')
            self.assertEqual(P.hint_ranking(data), 'ranked')

    def test_settings_beat_the_constant_and_the_policy_beats_the_settings(self):
        with tempfile.TemporaryDirectory() as tmp:
            data, store = fresh(tmp)
            reports.save_settings(data, {'identity_threshold': 0.90, 'identity_margin': 0.06})
            self.assertEqual(identity_bars(data), (0.90, 0.06))
            P.promote(data, {'identity_threshold': 0.85}, {'n': 22}, store=store)
            self.assertEqual(identity_bars(data), (0.85, 0.06))   # the margin the user applied is carried, not reset

    def test_a_promotion_about_the_queue_does_not_freeze_the_bars(self):
        """A review-order promotion says nothing about voice matching, so it must not silently pin whatever
        the bars were — the user's applied calibration has to keep working."""
        with tempfile.TemporaryDirectory() as tmp:
            data, store = fresh(tmp)
            reports.save_settings(data, {'identity_threshold': 0.90, 'identity_margin': 0.06})
            P.promote(data, {'review_order': 'recency'}, {'n': 30}, store=store)
            self.assertEqual(identity_bars(data), (0.90, 0.06))
            self.assertEqual(P.review_order(data), 'recency')

    def test_a_corrupt_or_out_of_range_policy_file_is_simply_the_next_step_down(self):
        with tempfile.TemporaryDirectory() as tmp:
            data, _ = fresh(tmp)
            reports.save_settings(data, {'identity_threshold': 0.90, 'identity_margin': 0.06})
            P.path(data).parent.mkdir(parents=True, exist_ok=True)
            P.path(data).write_text('{ this is not json', encoding='utf-8')
            self.assertEqual(identity_bars(data), (0.90, 0.06))
            P.path(data).write_text(json.dumps({'version': 4, 'identity': {'threshold': 0.99, 'margin': 0.06},
                                                'review_order': 'whatever'}), encoding='utf-8')
            self.assertEqual(identity_bars(data), (0.90, 0.06))      # 0.99 is outside the validated range
            self.assertEqual(P.review_order(data), 'severity')       # an unknown order is the shipped one

    def test_calibrate_apply_promotes_a_policy_so_the_two_files_cannot_disagree(self):
        with tempfile.TemporaryDirectory() as tmp:
            data, store = fresh(tmp)
            report = {'enough': True, 'n': 24, 'recommendation': {'threshold': 0.85, 'margin': 0.04, 'change': True,
                                                                  'correct_gain': 2, 'wrong_delta': 0}}
            out = quality.apply_calibration(store, data, report)
            self.assertTrue(out['applied'])
            self.assertEqual(out['policy_version'], 1)
            self.assertEqual(identity_bars(data), (0.85, 0.04))


class PromoteRollbackTests(unittest.TestCase):
    def test_the_chain_walks_forward_and_all_the_way_back(self):
        with tempfile.TemporaryDirectory() as tmp:
            data, store = fresh(tmp)
            P.promote(data, {'identity_threshold': 0.85}, {'n': 21}, store=store)
            P.promote(data, {'identity_margin': 0.08}, {'n': 22}, store=store)
            P.promote(data, {'review_order': 'recency'}, {'n': 23}, store=store)
            self.assertEqual((identity_bars(data), P.review_order(data)), ((0.85, 0.08), 'recency'))
            self.assertEqual(P.current(data)['version'], 3)

            self.assertTrue(P.rollback(data, store=store)['rolled_back'])
            self.assertEqual((identity_bars(data), P.review_order(data)), ((0.85, 0.08), 'severity'))
            self.assertTrue(P.rollback(data, store=store)['rolled_back'])
            self.assertEqual(identity_bars(data), (0.85, 0.05))
            self.assertTrue(P.rollback(data, store=store)['rolled_back'])
            # …and back at the shipped constants, which is where a first promotion has to be undoable to.
            self.assertEqual(identity_bars(data), (IDENTITY_THRESHOLD, IDENTITY_MARGIN))
            self.assertEqual(P.current(data)['version'], 6)   # history grows forwards even when values go back

            spent = P.rollback(data, store=store)
            self.assertFalse(spent['rolled_back'])
            self.assertEqual(identity_bars(data), (IDENTITY_THRESHOLD, IDENTITY_MARGIN))

    def test_a_promotion_outside_the_validated_range_is_refused_rather_than_clamped(self):
        with tempfile.TemporaryDirectory() as tmp:
            data, store = fresh(tmp)
            for bad in ({'identity_threshold': 0.99}, {'identity_threshold': 0.5}, {'identity_margin': 0.5},
                        {'identity_margin': 0.0}, {'review_order': 'alphabetical'}, {'hint_ranking': 'clever'},
                        {'analysis_model': 'gpt-4.1'}, {}):
                with self.assertRaises(ValueError): P.promote(data, bad, {'n': 40}, store=store)
            self.assertEqual(P.current(data)['source'], 'default')   # nothing was written by any of them

    def test_every_version_keeps_its_evidence_and_the_ones_before_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            data, store = fresh(tmp)
            P.promote(data, {'identity_threshold': 0.85}, {'n': 21, 'correct_gain': 3}, store=store)
            P.promote(data, {'review_order': 'recency'}, {'n': 33}, store=store)
            versions = P.versions(data)
            self.assertEqual([v['version'] for v in versions], [2, 1, 0])
            self.assertEqual(versions[1]['evidence'], {'n': 21, 'correct_gain': 3})
            self.assertIn('politika v2', P.line(data_dir=data))

    def test_both_directions_reach_the_event_log_exactly_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            data, store = fresh(tmp)
            self.assertIn('policy_promote', learning.ACTIONS)
            self.assertIn('policy_rollback', learning.ACTIONS)
            P.promote(data, {'identity_threshold': 0.85}, {'n': 21}, store=store)
            P.rollback(data, store=store)
            events = learning.events(store)
            self.assertEqual([e['action'] for e in events], ['policy_promote', 'policy_rollback'])
            self.assertEqual([e['source'] for e in events], ['auto', 'auto'])
            self.assertEqual([e['object'] for e in events], ['policy:1', 'policy:2'])


class GatingTests(unittest.TestCase):
    """"Kayıt sırasında model kıyası çalıştırma" is on the YAPMA list, so it is a rule in code, not a habit
    in the caller."""

    def test_an_experiment_never_runs_while_this_mac_is_recording_or_working(self):
        with tempfile.TemporaryDirectory() as tmp:
            data, store = fresh(tmp)
            recency_wins(store)
            reports.save_settings(data, {'auto_promote_policies': True})

            self.assertEqual(E.run_due(store, data, NOW, recording=True)['reason'], 'recording')
            self.assertEqual(E.run_due(store, data, NOW, job=True)['reason'], 'job')
            with patch.dict(os.environ, {'MEETING_OS_LOW_PRIORITY': '1'}):
                self.assertEqual(E.run_due(store, data, NOW)['reason'], 'job')
            meeting(store, 'in-flight', NOW.isoformat(), status='processing')
            self.assertEqual(E.run_due(store, data, NOW)['reason'], 'job')
            self.assertFalse(E.path(data).exists())            # a blocked run writes no result at all
            self.assertEqual(P.review_order(data), 'severity')  # …and promotes nothing

    def test_a_live_recording_heartbeat_blocks_the_pass_even_when_nobody_passed_a_flag(self):
        with tempfile.TemporaryDirectory() as tmp:
            data, store = fresh(tmp)
            reports.save_settings(data, {'report_dir': str(Path(tmp)/'reports')})
            reports.write_recording_heartbeat(data, {'elapsed_seconds': 30})
            self.assertEqual(E.run_due(store, data, NOW)['reason'], 'recording')

    def test_one_experiment_per_device_per_day(self):
        with tempfile.TemporaryDirectory() as tmp:
            data, store = fresh(tmp)
            recency_wins(store)
            self.assertTrue(E.run_due(store, data, NOW)['ran'])
            self.assertEqual(E.run_due(store, data, NOW+timedelta(hours=6))['reason'], 'daily_cap')
            self.assertTrue(E.run_due(store, data, NOW+timedelta(days=1))['ran'])
            days = {row['day'] for row in E.records(data)}
            self.assertEqual(days, {'2026-09-11', '2026-09-12'})


class EvidenceTests(unittest.TestCase):
    def test_thin_evidence_is_recorded_and_never_applied(self):
        with tempfile.TemporaryDirectory() as tmp:
            data, store = fresh(tmp)
            reports.save_settings(data, {'auto_promote_policies': True})
            meeting(store, 'today', '2026-09-10T09:00:00+00:00')
            for i in range(6): answer(store, 'today', f'asr:{i}', 'asr', 'corrected')
            out = E.run_due(store, data, NOW)
            order = [r for r in out['results'] if r['candidate'] == 'review_order'][0]
            self.assertLess(order['n'], E.MIN_SAMPLES)
            self.assertFalse(order['meets_goal'])
            self.assertEqual(order['verdict'], 'insufficient')
            self.assertEqual(out['promoted'], [])
            self.assertEqual(P.review_order(data), 'severity')

    def test_a_measured_win_is_a_recommendation_until_the_user_turns_promotion_on(self):
        with tempfile.TemporaryDirectory() as tmp:
            data, store = fresh(tmp)
            recency_wins(store)
            out = E.run_due(store, data, NOW)
            order = [r for r in out['results'] if r['candidate'] == 'review_order'][0]
            self.assertTrue(order['meets_goal'])
            self.assertGreaterEqual(order['proposal']['gain'], E.ORDER_MIN_GAIN)
            self.assertEqual(order['verdict'], 'recommended')
            self.assertEqual(out['promoted'], [])
            self.assertEqual(P.review_order(data), 'severity')      # measured, written down, NOT applied
            self.assertFalse(E.auto_promote(data))

    def test_with_promotion_on_the_same_win_becomes_a_policy_version_that_rolls_back(self):
        with tempfile.TemporaryDirectory() as tmp:
            data, store = fresh(tmp)
            recency_wins(store)
            reports.save_settings(data, {'auto_promote_policies': True})
            out = E.run_due(store, data, NOW)
            self.assertEqual(out['promoted'], ['review_order'])
            self.assertEqual(P.review_order(data), 'recency')
            record = P.current(data)
            self.assertEqual(record['evidence']['experiment'], 'review_order')
            self.assertEqual(record['evidence']['n'], 36)
            self.assertIn('policy_promote', [e['action'] for e in learning.events(store)])
            P.rollback(data, store=store)
            self.assertEqual(P.review_order(data), 'severity')

    def test_an_item_the_user_skipped_or_confirmed_is_a_position_and_never_an_approval(self):
        """Codex #11's own risk line: silence about the unseen alternative is not consent. 'geç' says nothing
        and 'bu doğru' says the item was fine — neither is evidence that an ordering saved anybody work."""
        with tempfile.TemporaryDirectory() as tmp:
            data, store = fresh(tmp)
            for index, mid in enumerate(('old-a', 'old-b')):
                meeting(store, mid, f'2026-09-0{index+1}T09:00:00+00:00')
                for i in range(14): answer(store, mid, f'marker:{i}', 'marker', 'correct')
            meeting(store, 'today', '2026-09-10T09:00:00+00:00')
            for i in range(8): answer(store, 'today', f'asr:{i}', 'asr', 'skipped')   # same shape, no decision
            result = E._order_candidate(store, data)
            self.assertEqual(result['n'], 36)
            self.assertEqual(result['corrected'], 0)
            self.assertFalse(result['meets_goal'])
            self.assertEqual(result['changes'], {})

    def test_the_hint_ranking_candidate_says_unmeasured_rather_than_no_good(self):
        with tempfile.TemporaryDirectory() as tmp:
            data, store = fresh(tmp)
            result = E._hint_candidate(store, data)
            if hasattr(quality, 'replay_rules'):
                self.assertTrue(result['available'])
            else:
                self.assertFalse(result['available'])
                self.assertEqual(E._verdict(result, True), 'unavailable')
                self.assertEqual(result['changes'], {})

    def test_a_promotion_whose_numbers_left_the_range_is_refused_at_the_policy_door(self):
        """Bounds are checked twice on purpose: the experiment decides a number is inside the range, and
        `policy.promote` decides whether it actually is."""
        with tempfile.TemporaryDirectory() as tmp:
            data, store = fresh(tmp)
            forged = {'candidate': 'identity_bars', 'goal': 'x', 'n': 99,
                      'changes': {'identity_threshold': 0.99, 'identity_margin': 0.05}}
            self.assertIsNone(E._promote(store, data, forged, NOW))
            self.assertEqual(P.current(data)['source'], 'default')


class ProductionDataTests(unittest.TestCase):
    """"Üretim dışı sonuçlar görev, profil veya kelime öğrenimine yazılmasın." The test is a census: every
    table the learning loop writes to, counted before and after a full experiment pass."""

    TABLES = ('samples', 'rejections', 'taught_words', 'tasks', 'text_edits', 'corrections', 'profile_stats')

    def census(self, store):
        out = {}
        for name in self.TABLES:
            try: out[name] = store.db.execute(f'SELECT count(*) FROM {name}').fetchone()[0]
            except Exception: out[name] = None
        return out

    def test_an_experiment_pass_changes_no_production_row(self):
        with tempfile.TemporaryDirectory() as tmp:
            data, store = fresh(tmp)
            from meeting_os.memory import Memory
            Memory(store)                               # the tasks/analyses tables exist from here on
            from meeting_os import correction_memory as CM
            recency_wins(store)
            CM.teach(store, 'today', 'trendyoll', 'Trendyol')
            store.enroll('Ali', [1.0, 0.0], 'm', 10, 'manual')
            reports.save_settings(data, {'auto_promote_policies': True})
            before = self.census(store)
            out = E.run_due(store, data, NOW)
            self.assertTrue(out['ran'])
            self.assertEqual(self.census(store), before)

    def test_results_land_in_the_experiments_file_and_nowhere_else(self):
        with tempfile.TemporaryDirectory() as tmp:
            data, store = fresh(tmp)
            recency_wins(store)
            E.run_due(store, data, NOW)
            rows = E.records(data)
            self.assertEqual({row['candidate'] for row in rows}, set(E.CANDIDATES))
            body = E.path(data).read_text(encoding='utf-8')
            for leak in ('old-a', 'today', 'marker:0', 'Trendyol'):
                self.assertNotIn(leak, body)     # counts and verdicts only: no meeting id, no word, no name


class RetentionTests(unittest.TestCase):
    def test_seven_days_and_twenty_megabytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            data, _ = fresh(tmp)
            E.path(data).parent.mkdir(parents=True, exist_ok=True)
            old = (NOW-timedelta(days=9)).isoformat(); recent = (NOW-timedelta(days=1)).isoformat()
            lines = [json.dumps({'time': old, 'day': '2026-09-02', 'candidate': 'review_order'})]*5
            lines += [json.dumps({'time': recent, 'day': '2026-09-10', 'candidate': 'review_order'})]*3
            E.path(data).write_text('\n'.join(lines)+'\n', encoding='utf-8')
            out = E.prune(data, now=NOW)
            self.assertEqual((out['removed'], out['rows']), (5, 3))
            self.assertTrue(all(row['time'] == recent for row in E.records(data)))

            out = E.prune(data, max_bytes=1, now=NOW)
            self.assertEqual(out['rows'], 0)
            self.assertEqual(E.records(data), [])

    def test_a_run_prunes_and_the_file_stays_private(self):
        with tempfile.TemporaryDirectory() as tmp:
            data, store = fresh(tmp)
            recency_wins(store)
            E.run_due(store, data, NOW)
            self.assertEqual(E.path(data).stat().st_mode & 0o777, 0o600)
            E.run_due(store, data, NOW+timedelta(days=30))
            self.assertEqual({row['day'] for row in E.records(data)}, {'2026-10-11'})   # the old day aged out


class QueueOrderingTests(unittest.TestCase):
    def test_the_weekly_debt_reads_its_order_from_the_policy(self):
        with tempfile.TemporaryDirectory() as tmp:
            data, store = fresh(tmp)
            items = [{'severity': 0, 'start': 1.0, 'created': '2026-09-01T09:00:00+00:00', 'key': 'old-easy'},
                     {'severity': 3, 'start': 2.0, 'created': '2026-09-10T09:00:00+00:00', 'key': 'new-hard'}]
            self.assertEqual([i['key'] for i in review.order_debt(items, 'severity')], ['old-easy', 'new-hard'])
            self.assertEqual([i['key'] for i in review.order_debt(items, 'recency')], ['new-hard', 'old-easy'])
            self.assertEqual(review.queue_order(data), 'severity')
            P.promote(data, {'review_order': 'recency'}, {'n': 40}, store=store)
            self.assertEqual(review.queue_order(data), 'recency')

    def test_a_kind_name_always_has_a_severity_even_when_it_arrives_as_an_item_key(self):
        self.assertEqual(review.severity_of('marker'), 0)
        self.assertEqual(review.severity_of('asr:44'), 3)
        self.assertEqual(review.severity_of('something_new'), review.DEFAULT_SEVERITY)


if __name__ == '__main__':
    unittest.main()
