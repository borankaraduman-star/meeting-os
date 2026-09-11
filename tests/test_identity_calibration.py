"""1.2.83 — kişi tanıma: where a voice sample came from, what the team's profiles actually bought, and a
threshold recommendation measured on this Mac's own time-ordered, human-verified evidence.

Nothing here changes IDENTITY_THRESHOLD or IDENTITY_MARGIN. The production constants stay exactly what they
were; the only path that can move them is a user running `quality calibrate --apply`, which is tested too.
"""
import json
import math
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from meeting_os import learning, quality, reports
from meeting_os.cloud_finalize import IDENTITY_MARGIN, IDENTITY_THRESHOLD, identity_bars
from meeting_os.store import Store, team_profile_effect
from meeting_os.types import Segment

FLAGS = ['cloud_transcript', 'cloud_diarization']


def at(similarity):
    """A 2-D unit vector whose cosine against [1,0] is exactly `similarity`."""
    angle = math.acos(similarity)
    return [math.cos(angle), math.sin(angle)]


def cluster(db, mid, vector, speaker, key, name=None, identity=None, seconds=12.0):
    seg = Segment(0, seconds, 'uzun bir konuşma', 'system', speaker,
                  metrics={'cluster': key, 'identity': identity or {}}, flags=FLAGS)
    seg.embedding = vector
    seg.embedding_model = 'm'
    sid = db.add_segment(mid, seg)
    if name:
        db.db.execute('UPDATE segments SET speaker_name=? WHERE id=?', (name, sid))
        db.db.commit()
    return sid


class SourceClassTests(unittest.TestCase):
    """Codex #6: a score has to say WHAT kind of evidence produced it."""

    def test_every_provenance_shape_maps_to_one_of_three_classes(self):
        self.assertEqual(Store.sample_class('manual'), 'human_local')
        self.assertEqual(Store.sample_class('abc123:44'), 'human_local')
        self.assertEqual(Store.sample_class('abc123:speaker:system:S1'), 'human_local')
        self.assertEqual(Store.sample_class('auto:abc123:0:S1'), 'auto_local')
        self.assertEqual(Store.sample_class('team:Mac-Ayse:deadbeef'), 'team')
        self.assertEqual(Store.sample_class(None), 'human_local')

    def test_scores_report_the_class_breakdown_and_the_class_of_the_best_sample(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Store(Path(tmp)/'db')
            db.enroll('Ali', [1.0, 0.0], 'm', 10, 'manual')
            db.enroll('Ali', at(0.99), 'm', 10, 'auto:mid:0:S1')
            db.enroll('Ali', at(0.95), 'm', 10, 'team:Mac-Ayse:abc')
            db.enroll('Veli', at(0.40), 'm', 10, 'team:Mac-Ayse:def')
            ali = [s for s in db._scores([1.0, 0.0], 'm') if s['name'] == 'Ali'][0]
            veli = [s for s in db._scores([1.0, 0.0], 'm') if s['name'] == 'Veli'][0]
            self.assertEqual(ali['by_class'], {'human_local': 1, 'auto_local': 1, 'team': 1})
            self.assertEqual(ali['best_class'], 'human_local')   # the exact vector, enrolled by hand
            self.assertFalse(ali['team_only'])
            self.assertEqual(veli['by_class'], {'human_local': 0, 'auto_local': 0, 'team': 1})
            self.assertTrue(veli['team_only'])
            db.close()

    def test_a_class_can_be_dropped_from_the_pool_which_is_what_the_counterfactual_needs(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Store(Path(tmp)/'db')
            db.enroll('Ali', [1.0, 0.0], 'm', 10, 'team:Mac-Ayse:abc')
            self.assertEqual([s['name'] for s in db._scores([1.0, 0.0], 'm')], ['Ali'])
            self.assertEqual(db._scores([1.0, 0.0], 'm', drop_classes=('team',)), [])
            db.close()


class TeamOnlyAcceptanceTests(unittest.TestCase):
    """A person only the team knows is suggested, not named — unless the match is very strong."""

    def test_a_team_only_match_over_the_bar_is_a_suggestion_and_not_a_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Store(Path(tmp)/'db')
            db.enroll('Ayşe', [1.0, 0.0], 'm', 10, 'team:Mac-Ayse:abc')
            out = db.identify(at(0.88), 'm', IDENTITY_THRESHOLD, IDENTITY_MARGIN)
            self.assertIsNone(out['name'])              # 0.88 clears 0.87 and would have been a name
            self.assertEqual(out['candidate'], 'Ayşe')  # …so the app offers it instead
            self.assertTrue(out['team_only'])
            self.assertEqual(out['best_class'], 'team')
            self.assertAlmostEqual(out['threshold_used'], IDENTITY_THRESHOLD + Store.TEAM_EXTRA_MARGIN)
            db.close()

    def test_a_team_only_match_that_clears_the_extra_margin_is_named(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Store(Path(tmp)/'db')
            db.enroll('Ayşe', [1.0, 0.0], 'm', 10, 'team:Mac-Ayse:abc')
            out = db.identify(at(0.95), 'm', IDENTITY_THRESHOLD, IDENTITY_MARGIN)
            self.assertEqual(out['name'], 'Ayşe')
            db.close()

    def test_one_local_sample_of_the_same_person_removes_the_extra_bar(self):
        """The higher bar is about evidence nobody here has checked, not about the person."""
        with tempfile.TemporaryDirectory() as tmp:
            db = Store(Path(tmp)/'db')
            db.enroll('Ayşe', [1.0, 0.0], 'm', 10, 'team:Mac-Ayse:abc')
            db.enroll('Ayşe', [1.0, 0.0], 'm', 10, 'manual')
            out = db.identify(at(0.88), 'm', IDENTITY_THRESHOLD, IDENTITY_MARGIN)
            self.assertEqual(out['name'], 'Ayşe')
            self.assertFalse(out['team_only'])
            self.assertAlmostEqual(out['threshold_used'], IDENTITY_THRESHOLD)
            db.close()


class PersonThresholdAfterWrongTests(unittest.TestCase):
    """Codex #5: "bir yanlış otomatik isim, eşiği düşürmeyi durdursun"."""

    def test_confirmations_no_longer_discount_below_the_base_once_a_name_was_wrong(self):
        self.assertAlmostEqual(Store.personal_bar(0.87, 3, 0), 0.84)   # no mistake: the discount stands
        self.assertAlmostEqual(Store.personal_bar(0.87, 0, 1), 0.89)
        self.assertAlmostEqual(Store.personal_bar(0.87, 3, 1), 0.89)   # the three confirmations no longer pay for it
        self.assertAlmostEqual(Store.personal_bar(0.87, 3, 2), 0.91)
        self.assertAlmostEqual(Store.personal_bar(0.87, 0, 0), 0.87)

    def test_the_stored_counters_follow_the_same_rule(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Store(Path(tmp)/'db')
            db.enroll('Ali', [1.0, 0.0], 'm', 10, 'manual')
            for i in range(3):   # three confirmed suggestions
                mid = db.create_meeting(f't{i}')
                cluster(db, mid, [1.0, 0.0], 'system:S1', '0:S1', identity={'name': None, 'suggested': 'Ali'})
                db.correct(mid, 'system:S1', 'Ali')
            self.assertAlmostEqual(db.person_threshold('Ali', 0.87), 0.84)
            wrong = db.create_meeting('yanlış')   # then one automatic name the user overruled
            cluster(db, wrong, [0.0, 1.0], 'system:S1', '0:S1', name='Ali', identity={'name': 'Ali', 'suggested': None})
            db.correct(wrong, 'system:S1', 'Kaya')
            self.assertAlmostEqual(db.person_threshold('Ali', 0.87), 0.89)   # never below the base again
            db.undo_correction(wrong)
            self.assertAlmostEqual(db.person_threshold('Ali', 0.87), 0.84)   # ⌘Z takes the evidence back too
            db.close()


def timeline_store(tmp, *, team=False, days=4):
    """A small dated history: one person known from day 1, one voice nobody could have known."""
    store = Store(Path(tmp)/'meeting-os.sqlite')

    def meeting(title, day, clusters):
        mid = store.create_meeting(title, {'model': 'm'})
        t = 0
        for speaker, vector in clusters:
            cluster(store, mid, vector, speaker, f'0:{t//10}')
            t += 10
        store.status(mid, 'complete')
        with store.db:
            store.db.execute('UPDATE meetings SET created=? WHERE id=?', (f'2026-01-{day:02d}T09:00:00+00:00', mid))
        return mid

    def date_samples(day):
        stamp = f'2026-01-{day:02d}T18:00:00+00:00'
        with store.db:
            store.db.execute('UPDATE samples SET created=? WHERE created IS NULL OR created>?', (stamp, stamp))

    ids = []
    for day in range(1, days+1):
        mid = meeting(f'M{day}', day, [('K1', [1.0, 0.0, 0.0]), ('K2', [0.0, 1.0, 0.0])])
        store.enroll_speaker(mid, 'K1', 'Ayşe')
        store.enroll_speaker(mid, 'K2', 'Burak')
        date_samples(day)
        ids.append(mid)
    if team:
        store.enroll('Ceren', [0.0, 0.0, 1.0], 'm', 12, 'team:Mac-Ayse:abc')
        with store.db:
            store.db.execute("UPDATE samples SET created='2026-01-01T00:00:00+00:00' WHERE provenance LIKE 'team:%'")
    return store, ids


class TeamProfileEffectTests(unittest.TestCase):
    """"8 profil indi" is a download. This is the benefit, counted."""

    def test_a_mac_with_no_team_samples_answers_without_running_a_replay(self):
        with tempfile.TemporaryDirectory() as tmp:
            store, _ = timeline_store(tmp)
            effect = team_profile_effect(store)
            self.assertEqual((effect['right'], effect['wrong'], effect['team_samples'], effect['line']), (0, 0, 0, ''))
            store.close()

    def test_a_name_only_the_team_sample_could_have_produced_counts_as_one_right(self):
        with tempfile.TemporaryDirectory() as tmp:
            store, _ = timeline_store(tmp)
            # Ceren speaks on day 5 and the team's sample of her is the only evidence there is — strong enough
            # to clear the extra team bar, so the app names her and nothing local could have.
            mid = store.create_meeting('M5', {'model': 'm'})
            cluster(store, mid, [0.0, 0.0, 1.0], 'K1', '0:0', name='Ceren')
            store.status(mid, 'complete')
            with store.db:
                store.db.execute('UPDATE meetings SET created=? WHERE id=?', ('2026-01-05T09:00:00+00:00', mid))
            store.enroll('Ceren', [0.0, 0.0, 1.0], 'm', 12, 'team:Mac-Ayse:abc')
            with store.db:
                store.db.execute("UPDATE samples SET created='2026-01-02T00:00:00+00:00' WHERE provenance LIKE 'team:%'")
            effect = team_profile_effect(store)
            self.assertEqual(effect['right'], 1)
            self.assertEqual(effect['wrong'], 0)
            self.assertIn('+1 doğru', effect['line'])
            self.assertIn('−0 yanlış', effect['line'])
            store.close()

    def test_a_wrong_name_only_the_team_sample_could_have_produced_counts_as_one_wrong(self):
        with tempfile.TemporaryDirectory() as tmp:
            store, _ = timeline_store(tmp)
            mid = store.create_meeting('M5', {'model': 'm'})
            cluster(store, mid, [0.0, 0.0, 1.0], 'K1', '0:0', name='Deniz')   # really Deniz…
            store.status(mid, 'complete')
            with store.db:
                store.db.execute('UPDATE meetings SET created=? WHERE id=?', ('2026-01-05T09:00:00+00:00', mid))
            store.enroll('Ceren', [0.0, 0.0, 1.0], 'm', 12, 'team:Mac-Ayse:abc')   # …but a teammate calls that voice Ceren
            with store.db:
                store.db.execute("UPDATE samples SET created='2026-01-02T00:00:00+00:00' WHERE provenance LIKE 'team:%'")
            effect = team_profile_effect(store)
            self.assertEqual((effect['right'], effect['wrong']), (0, 1))
            self.assertIn('−1 yanlış', effect['line'])
            store.close()


class TeamTimeToValueTests(unittest.TestCase):
    """Join → knowledge available → first verified benefit, as three stamps and two durations."""

    def test_the_two_durations_are_reported_when_both_ends_exist(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp)/'db')
            base = datetime(2026, 1, 1, 9, 0, tzinfo=timezone.utc)
            learning.record_event(store, 'team_join', object='t1', scope='global', now=base)
            learning.record_event(store, 'team_knowledge_ready', object='3', scope='global', source='auto', now=base+timedelta(seconds=45))
            learning.record_event(store, 'team_first_value', scope='global', now=base+timedelta(hours=2))
            out = learning.summary(store)['team']
            self.assertEqual(out['join_to_ready_seconds'], 45.0)
            self.assertEqual(out['join_to_first_value_seconds'], 7200.0)
            self.assertEqual(out['team_join'], base.isoformat())
            store.close()

    def test_without_a_join_there_is_no_duration_and_no_guess(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp)/'db')
            learning.record_event(store, 'team_knowledge_ready', object='3', scope='global', source='auto')
            out = learning.summary(store)['team']
            self.assertIsNone(out['team_join'])
            self.assertIsNone(out['join_to_ready_seconds'])
            store.close()

    def test_record_once_never_writes_a_second_stopwatch_mark(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp)/'db')
            base = datetime(2026, 1, 1, 9, 0, tzinfo=timezone.utc)
            first = learning.record_once(store, 'team_first_value', scope='global', now=base)
            again = learning.record_once(store, 'team_first_value', scope='global', now=base+timedelta(days=3))
            self.assertEqual(first, again)
            self.assertEqual(len([e for e in learning.events(store) if e['action'] == 'team_first_value']), 1)
            store.close()

    def test_verifying_a_name_a_team_sample_produced_marks_the_first_benefit(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp)/'db')
            mid = store.create_meeting('t')
            cluster(store, mid, [1.0, 0.0], 'system:S1', '0:S1', name='Ayşe',
                    identity={'name': 'Ayşe', 'suggested': None, 'best_class': 'team', 'team_only': True})
            self.assertIsNone(learning.last_event(store, 'team_first_value'))
            store.correct(mid, 'system:S1', 'Ayşe')   # the user confirms what the team's sample said
            self.assertIsNotNone(learning.last_event(store, 'team_first_value'))
            store.close()

    def test_a_locally_learned_name_is_not_the_teams_first_benefit(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp)/'db')
            mid = store.create_meeting('t')
            cluster(store, mid, [1.0, 0.0], 'system:S1', '0:S1', name='Ayşe',
                    identity={'name': 'Ayşe', 'suggested': None, 'best_class': 'human_local'})
            store.correct(mid, 'system:S1', 'Ayşe')
            self.assertIsNone(learning.last_event(store, 'team_first_value'))
            store.close()


def verified_store(tmp, people):
    """`people` meetings, each with one cluster the user NAMED, on consecutive days. Every person is heard
    twice, so from the second meeting on there is real earlier evidence to recognise them from."""
    store = Store(Path(tmp)/'meeting-os.sqlite')
    day = 1
    for index in range(people):
        # Two vectors close enough to be the same person, far enough from everybody else.
        base = [0.0]*people
        base[index] = 1.0
        for repeat, vector in enumerate((base, at3(base, 0.995))):
            mid = store.create_meeting(f'M{index}-{repeat}', {'model': 'm'})
            cluster(store, mid, vector, 'K1', '0:0')
            store.status(mid, 'complete')
            with store.db:
                store.db.execute('UPDATE meetings SET created=? WHERE id=?', (f'2026-{1+day//28:02d}-{1+day % 28:02d}T09:00:00+00:00', mid))
            store.enroll_speaker(mid, 'K1', f'Kişi {index}')
            stamp = f'2026-{1+day//28:02d}-{1+day % 28:02d}T18:00:00+00:00'
            with store.db:
                store.db.execute('UPDATE samples SET created=? WHERE created IS NULL OR created>?', (stamp, stamp))
            day += 1
    return store


def at3(base, similarity):
    """A unit vector `similarity` away from `base`, tilted into a dimension nobody else uses."""
    out = [v*similarity for v in base]
    out[-1] = out[-1] + math.sqrt(max(0.0, 1-similarity**2)) if base[-1] == 0 else out[-1]
    norm = math.sqrt(sum(v*v for v in out))
    return [v/norm for v in out]


def tilt(dims, base, spare, similarity):
    """A unit vector exactly `similarity` away from e_base, tilted into a dimension nobody else uses."""
    out = [0.0]*dims
    out[base] = similarity
    out[spare] = math.sqrt(max(0.0, 1-similarity**2))
    return out


def grid_store(tmp, *, easy=10, borderline=None, trap=None):
    """A history built to make the grid say something: `easy` people the app gets right at every candidate
    threshold, plus (optionally) one person whose second appearance scores `borderline` — named at 0.85 and
    abstained at 0.87 — and one stranger whose voice scores `trap` against a known person."""
    dims = easy+3
    store = Store(Path(tmp)/'meeting-os.sqlite')
    day = [1]

    def named_meeting(title, vector, person):
        mid = store.create_meeting(title, {'model': 'm'})
        cluster(store, mid, vector, 'K1', '0:0')
        store.status(mid, 'complete')
        stamp = f'2026-{1+day[0]//28:02d}-{1+day[0] % 28:02d}'
        with store.db:
            store.db.execute('UPDATE meetings SET created=? WHERE id=?', (f'{stamp}T09:00:00+00:00', mid))
        store.enroll_speaker(mid, 'K1', person)
        with store.db:
            store.db.execute('UPDATE samples SET created=? WHERE created IS NULL OR created>?',
                             (f'{stamp}T18:00:00+00:00', f'{stamp}T18:00:00+00:00'))
        day[0] += 1
        return mid

    for index in range(easy):
        base = [0.0]*dims
        base[index] = 1.0
        named_meeting(f'M{index}-1', base, f'Kişi {index}')
        named_meeting(f'M{index}-2', base, f'Kişi {index}')
    if borderline is not None:
        base = [0.0]*dims
        base[easy] = 1.0
        named_meeting('B-1', base, 'Sınırdaki')
        named_meeting('B-2', tilt(dims, easy, easy+1, borderline), 'Sınırdaki')
    if trap is not None:
        base = [0.0]*dims
        base[easy+2] = 1.0
        named_meeting('T-1', base, 'Tanıdık')
        named_meeting('T-2', tilt(dims, easy+2, easy+1, trap), 'Yabancı')   # not Tanıdık: a voice nobody here knows
    return store


class CalibrationGridTests(unittest.TestCase):
    """The grid has to be able to say "a lower bar would help" — and to refuse when it would not."""

    def test_a_lower_threshold_that_wins_a_name_without_a_wrong_one_is_recommended(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = grid_store(tmp, easy=10, borderline=0.86)   # 0.86: over 0.85, under 0.87
            report = quality.calibrate(store, tmp, save=False)
            self.assertEqual(report['n'], 22)
            self.assertTrue(report['enough'])
            current = [c for c in report['candidates'] if c['current']][0]
            lower = [c for c in report['candidates'] if c['threshold'] == 0.85 and c['margin'] == 0.05][0]
            self.assertEqual(lower['correct'], current['correct']+1)
            self.assertEqual((lower['wrong'], lower['unknown_named']), (0, 0))
            rec = report['recommendation']
            self.assertEqual((rec['threshold'], rec['correct_gain'], rec['change']), (0.85, 1, True))
            self.assertTrue(rec['applicable'])
            self.assertEqual(report['line'], 'kalibrasyon önerisi: eşik 0.85 (+1 doğru, 0 yanlış, n=22)')
            store.close()

    def test_a_lower_threshold_that_also_names_a_stranger_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = grid_store(tmp, easy=10, borderline=0.86, trap=0.86)
            report = quality.calibrate(store, tmp, save=False)
            lower = [c for c in report['candidates'] if c['threshold'] == 0.85 and c['margin'] == 0.05][0]
            current = [c for c in report['candidates'] if c['current']][0]
            self.assertEqual(lower['correct'], current['correct']+1)   # it does win the borderline name…
            self.assertEqual(lower['unknown_named'], 1)                # …and invents one, which is the whole objection
            self.assertEqual(current['unknown_named'], 0)
            self.assertEqual(report['recommendation']['threshold'], IDENTITY_THRESHOLD)
            self.assertFalse(report['recommendation']['change'])
            store.close()

    def test_an_unknown_person_stays_abstained_at_todays_setting(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = grid_store(tmp, easy=10, trap=0.86)
            out = quality.replay_timeline(store, verified_only=True)
            stranger = [i for i in out['items'] if i['name'] == 'Yabancı'][0]
            self.assertEqual(stranger['outcome'], 'abstained_ok')
            self.assertFalse(stranger['known_before'])
            store.close()


class CalibrationTests(unittest.TestCase):
    """Codex #5: a grid, measured on time-ordered human-verified evidence, that recommends and never applies."""

    def test_below_twenty_verified_clusters_there_is_no_recommendation_only_a_count(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = verified_store(tmp, 5)   # 10 clusters
            report = quality.calibrate(store, tmp)
            self.assertEqual(report['n'], 10)
            self.assertFalse(report['enough'])
            self.assertEqual(report['line'], 'kalibrasyon: veri yetersiz (n=10)')
            self.assertFalse(report['recommendation']['applicable'])
            self.assertTrue(quality.calibration_path(tmp).is_file())
            store.close()

    def test_with_enough_verified_clusters_the_grid_is_scored_and_one_candidate_recommended(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = verified_store(tmp, 12)   # 24 clusters
            report = quality.calibrate(store, tmp)
            self.assertGreaterEqual(report['n'], quality.CALIBRATION_MIN_VERIFIED)
            self.assertTrue(report['enough'])
            grid = {(c['threshold'], c['margin']) for c in report['candidates']}
            self.assertEqual(grid, {(t, m) for t in quality.CALIBRATION_THRESHOLDS for m in quality.CALIBRATION_MARGINS})
            for c in report['candidates']:
                self.assertEqual(c['n'], report['n'])
                self.assertEqual(c['correct']+c['wrong']+c['abstained_ok']+c['abstained_wrong'], c['n'])
            current = [c for c in report['candidates'] if c['current']][0]
            self.assertEqual((current['threshold'], current['margin']), (IDENTITY_THRESHOLD, IDENTITY_MARGIN))
            rec = report['recommendation']
            self.assertLessEqual(rec['wrong'], current['wrong'])              # never worse
            self.assertLessEqual(rec['unknown_named'], current['unknown_named'])
            self.assertGreaterEqual(rec['correct'], current['correct'])
            store.close()

    def test_the_recommendation_is_written_but_the_production_constants_are_untouched(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = verified_store(tmp, 12)
            quality.calibrate(store, tmp)
            saved = json.loads(quality.calibration_path(tmp).read_text(encoding='utf-8'))
            self.assertIn('recommendation', saved)
            self.assertEqual(identity_bars(tmp), (IDENTITY_THRESHOLD, IDENTITY_MARGIN))   # nothing applied
            self.assertEqual(reports.load_settings(tmp)['identity_threshold'], None)
            store.close()

    def test_only_clusters_a_human_named_are_judged(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = verified_store(tmp, 5)
            unnamed = store.create_meeting('otomatik', {'model': 'm'})
            cluster(store, unnamed, [1.0, 0.0, 0.0, 0.0, 0.0], 'K9', '0:0', name='Kişi 0')   # the app's own guess, never judged
            store.status(unnamed, 'complete')
            with store.db:
                store.db.execute('UPDATE meetings SET created=? WHERE id=?', ('2026-03-01T09:00:00+00:00', unnamed))
            self.assertEqual(quality.calibrate(store, tmp, save=False)['n'], 10)   # still 10: the untouched cluster is not evidence
            self.assertEqual(quality.replay_timeline(store)['clusters'], 11)       # the full replay still sees it
            store.close()

    def test_an_unknown_person_being_named_disqualifies_a_candidate(self):
        """The constraint, exercised directly: a candidate may not name more unknown people than today's does."""
        rows = [{'threshold': 0.87, 'margin': 0.05, 'n': 30, 'correct': 10, 'wrong': 2, 'auto_wrong': 2,
                 'unknown_named': 0, 'abstained_ok': 18, 'abstained_wrong': 0, 'current': True},
                {'threshold': 0.85, 'margin': 0.05, 'n': 30, 'correct': 14, 'wrong': 2, 'auto_wrong': 0,
                 'unknown_named': 2, 'abstained_ok': 14, 'abstained_wrong': 0, 'current': False}]
        eligible = [r for r in rows if r['wrong'] <= rows[0]['wrong'] and r['unknown_named'] <= rows[0]['unknown_named']]
        self.assertEqual([r['threshold'] for r in eligible], [0.87])

    def test_apply_writes_the_bars_into_settings_and_cloud_finalize_reads_them_back(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = verified_store(tmp, 5)
            refused = quality.apply_calibration(store, tmp)
            self.assertFalse(refused['applied'])
            self.assertIn('veri yetersiz', refused['reason'])
            self.assertEqual(identity_bars(tmp), (IDENTITY_THRESHOLD, IDENTITY_MARGIN))
            # The user applies a calibration by hand: the bars follow, validated.
            reports.save_settings(tmp, {'identity_threshold': 0.85, 'identity_margin': 0.04})
            self.assertEqual(identity_bars(tmp), (0.85, 0.04))
            store.close()

    def test_a_bar_outside_the_validated_range_is_refused_and_the_constant_stands(self):
        with tempfile.TemporaryDirectory() as tmp:
            reports.save_settings(tmp, {'identity_threshold': 0.10, 'identity_margin': 9.0})
            self.assertEqual(identity_bars(tmp), (IDENTITY_THRESHOLD, IDENTITY_MARGIN))
            reports.save_settings(tmp, {'identity_threshold': 0.85})
            self.assertEqual(identity_bars(tmp)[0], 0.85)
            reports.save_settings(tmp, {'identity_threshold': None})   # cleared: the constant comes back
            self.assertEqual(identity_bars(tmp), (IDENTITY_THRESHOLD, IDENTITY_MARGIN))

    def test_a_hand_edited_settings_file_with_nonsense_is_ignored(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp)/'settings.json').write_text(json.dumps({'identity_threshold': 'çok', 'identity_margin': True}), encoding='utf-8')
            self.assertEqual(identity_bars(tmp), (IDENTITY_THRESHOLD, IDENTITY_MARGIN))

    def test_the_refresh_answers_from_the_file_until_it_goes_stale(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = verified_store(tmp, 5)
            now = datetime.now(timezone.utc)
            first = quality.calibration_refresh(store, tmp, now=now)
            self.assertFalse(first['fresh'])
            again = quality.calibration_refresh(store, tmp, now=now+timedelta(hours=1))
            self.assertTrue(again['fresh'])
            later = quality.calibration_refresh(store, tmp, now=now+timedelta(hours=30))
            self.assertFalse(later['fresh'])
            store.close()

    def test_the_setup_card_line_says_what_it_can(self):
        self.assertEqual(quality.calibration_line({'n': 7, 'enough': False}), 'kalibrasyon: veri yetersiz (n=7)')
        self.assertEqual(quality.calibration_line({'n': 24, 'enough': True, 'current': {'margin': 0.05},
                                                   'recommendation': {'change': False}}),
                         'kalibrasyon: mevcut eşik en iyisi (n=24)')
        self.assertEqual(quality.calibration_line({'n': 24, 'enough': True, 'current': {'margin': 0.05},
                                                   'recommendation': {'change': True, 'threshold': 0.85, 'margin': 0.05,
                                                                      'correct_gain': 2, 'wrong': 0}}),
                         'kalibrasyon önerisi: eşik 0.85 (+2 doğru, 0 yanlış, n=24)')
        self.assertEqual(quality.calibration_line({}), '')


class SetupCardPayloadTests(unittest.TestCase):
    """The bridge hands the card two lines, read from files and never measured on the spot."""

    def test_the_payload_carries_the_calibration_and_team_effect_lines(self):
        with tempfile.TemporaryDirectory() as tmp:
            from meeting_os.desktop import _identity_learning
            self.assertEqual(_identity_learning(tmp)['calibration']['line'], '')   # nothing measured yet
            folder = Path(tmp)/'quality'
            folder.mkdir(parents=True)
            (folder/'calibration.json').write_text(json.dumps({'n': 24, 'enough': True, 'line': 'kalibrasyon önerisi: eşik 0.85 (+2 doğru, 0 yanlış, n=24)'}), encoding='utf-8')
            (folder/'team-effect.json').write_text(json.dumps({'right': 2, 'wrong': 1, 'clusters': 9, 'team_samples': 4,
                                                               'line': 'ekipten gelen profiller: +2 doğru / −1 yanlış'}), encoding='utf-8')
            payload = _identity_learning(tmp)
            self.assertIn('eşik 0.85', payload['calibration']['line'])
            self.assertIn('+2 doğru', payload['team_profile_effect']['line'])
            self.assertEqual(payload['team_profile_effect']['right'], 2)


if __name__ == '__main__':
    unittest.main()
