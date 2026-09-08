import unittest
import numpy as np
from scipy.signal import butter, sosfilt
from meeting_os.echo import measure_timed_echo, summarize_echo_windows


def speech_shaped(seed, seconds=3):
    rng = np.random.default_rng(seed)
    n = int(seconds*16000)
    noise = sosfilt(butter(3, [180, 2800], fs=16000, btype='bandpass', output='sos'), rng.normal(size=n))
    t = np.arange(n)/16000
    envelope = np.maximum(0, np.sin(2*np.pi*2.7*t))**2
    return noise*envelope*.15


class EchoTimelineTests(unittest.TestCase):
    def test_timestamp_offset_and_common_overlap(self):
        x = speech_shaped(13, 4)
        # Mic starts 0.2s later in the same timeline, acoustic delay is 0.06s.
        mic = .5*x[2240:50240]
        before = x.tobytes(), mic.tobytes()
        row = measure_timed_echo(x, mic, system_start=10., mic_start=10.2)
        self.assertEqual(row['measurement']['status'], 'correlated_copy')
        self.assertAlmostEqual(row['measurement']['lag_seconds'], .06, places=3)
        self.assertAlmostEqual(row['start'], 10.2)
        self.assertAlmostEqual(row['end'], 13.2)
        self.assertEqual(before, (x.tobytes(), mic.tobytes()))

    def test_disjoint_or_short_overlap_abstains(self):
        x = speech_shaped(12)
        for start in (3., 2.8):
            row = measure_timed_echo(x, x, system_start=0., mic_start=start)
            self.assertEqual(row['measurement']['status'], 'insufficient_signal')

    def test_invalid_timestamps(self):
        x = np.zeros(8000)
        for value in (-1, float('nan'), float('inf'), True, '1', 14401):
            with self.assertRaises(ValueError):
                measure_timed_echo(x, x, system_start=value, mic_start=0.)

    def test_known_lag_trend(self):
        rows = []
        for start, delay in [(0, 800), (20, 832), (40, 864)]:
            x = speech_shaped(start+1)
            mic = np.r_[np.zeros(delay), .5*x[:-delay]]
            rows.append(measure_timed_echo(x, mic, system_start=start, mic_start=start))
        result = summarize_echo_windows(rows)
        self.assertEqual(result['status'], 'consistent_lag_trend')
        self.assertAlmostEqual(result['lag_trend_ppm'], 100., delta=1.)
        self.assertEqual(result['accepted_windows'], 3)
        self.assertFalse(result['clock_drift_proven'])

    def test_abstains_on_step_change_and_insufficient_span(self):
        def row(t, lag):
            return dict(start=t, end=t+3, measurement={'status':'correlated_copy', 'lag_seconds':lag})
        for rows in ([row(0,.05), row(4,.05), row(8,.05)],
                     [row(0,.05), row(20,.05), row(40,.1)]):
            result = summarize_echo_windows(rows)
            self.assertEqual(result['status'], 'inconclusive')
            self.assertIsNone(result['lag_trend_ppm'])

    def test_duplicate_overlapping_or_unbounded_rows_rejected(self):
        row = dict(start=0., end=3., measurement={'status':'correlated_copy', 'lag_seconds':.05})
        for rows in ([row,row], [row]*257):
            with self.assertRaises(ValueError):
                summarize_echo_windows(rows)

    def test_near_end_control_and_double_talk_remain_untouched(self):
        x, near = speech_shaped(1), speech_shaped(2)
        self.assertEqual(measure_timed_echo(x, near)['measurement']['status'], 'inconclusive')
        mic = .6*x + .2*near
        before = mic.tobytes()
        row = measure_timed_echo(x, mic)
        self.assertGreater(row['measurement']['residual_energy_ratio'], .02)
        self.assertEqual(mic.tobytes(), before)

    def test_single_impulse_cannot_establish_echo(self):
        system = np.zeros(32000)
        mic = system.copy()
        system[8000] = .5
        mic[8800] = .2
        row = measure_timed_echo(system, mic)
        self.assertEqual(row['measurement']['status'], 'insufficient_signal')

    def test_malformed_summary_rows_raise_value_error(self):
        for row in ({}, None, {'start':0,'end':1,'measurement':None},
                    {'start':0,'end':1,'measurement':{}},
                    {'start':0,'end':1,'measurement':{'status':'correlated_copy'}},
                    {'start':0,'end':1,'measurement':{'status':'made_up'}}):
            with self.assertRaises(ValueError): summarize_echo_windows([row])

    def test_fractional_origin_near_end_keeps_bounds(self):
        x = speech_shaped(21, 1)
        row = measure_timed_echo(x,x, system_start=0., mic_start=.5/16000)
        self.assertLessEqual(row['end'],1.)
        self.assertEqual(row['measurement']['status'],'correlated_copy')
