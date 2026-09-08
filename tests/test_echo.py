import unittest
import numpy as np
from meeting_os.echo import measure_echo


class EchoTests(unittest.TestCase):
    def setUp(self):
        self.rng = np.random.default_rng(42)
        self.system = self.rng.normal(0, .1, 32000)

    def test_delayed_echo_and_input_preservation(self):
        mic = np.r_[np.zeros(1600), self.system[:-1600] * .4]
        before = (self.system.tobytes(), mic.tobytes())
        result = measure_echo(self.system, mic)
        self.assertEqual(result['status'], 'correlated_copy')
        self.assertAlmostEqual(result['lag_seconds'], .1, places=3)
        self.assertAlmostEqual(result['gain'], .4, places=2)
        self.assertEqual(before, (self.system.tobytes(), mic.tobytes()))

    def test_near_end_and_double_talk_are_never_suppressed(self):
        near = self.rng.normal(0, .1, 32000)
        self.assertEqual(measure_echo(self.system, near)['status'], 'inconclusive')
        mixed = self.system * .8 + near * .3
        original = mixed.tobytes()
        result = measure_echo(self.system, mixed)
        self.assertGreater(result['residual_energy_ratio'], .05)
        self.assertEqual(mixed.tobytes(), original)

    def test_periodic_signal_is_ambiguous(self):
        tone = np.sin(np.arange(32000) * 2 * np.pi * 100 / 16000)
        self.assertEqual(measure_echo(tone, tone)['status'], 'inconclusive')

    def test_silence_and_short_inputs(self):
        for audio in (np.zeros(32000), np.zeros(10)):
            result = measure_echo(audio, audio)
            self.assertEqual(result['status'], 'insufficient_signal')
            self.assertIsNone(result['lag_seconds'])

    def test_invalid_and_oversized_input(self):
        for audio in (np.zeros((10, 2)), np.full(16000, np.nan), np.zeros(80001)):
            with self.assertRaises(ValueError):
                measure_echo(audio, audio)

    def test_negative_lag_and_inverted_polarity(self):
        mic = np.r_[-.5*self.system[800:], np.zeros(800)]
        result = measure_echo(self.system, mic)
        self.assertEqual(result['status'], 'correlated_copy')
        self.assertAlmostEqual(result['lag_seconds'], -.05, places=3)
        self.assertAlmostEqual(result['gain'], -.5, places=2)

    def test_lag_search_boundary_abstains(self):
        mic = np.r_[np.zeros(4000), self.system[:-4000]*.4]
        self.assertEqual(measure_echo(self.system, mic)['status'], 'inconclusive')

    def test_asymmetric_local_dc_does_not_hide_copy(self):
        system = np.r_[self.system[:16000], np.full(16000, .8)]
        mic = self.system[:16000]*.4 + .2
        result = measure_echo(system, mic)
        self.assertEqual(result['status'], 'correlated_copy')
        self.assertAlmostEqual(result['gain'], .4, delta=.01)

    def test_two_separated_copies_abstain(self):
        delayed = np.r_[np.zeros(1600), self.system[:-1600]]
        result = measure_echo(self.system, .4*(self.system+delayed))
        self.assertEqual(result['status'], 'inconclusive')
