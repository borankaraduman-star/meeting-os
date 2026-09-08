from pathlib import Path
import runpy
import tempfile
import unittest
import numpy as np
import soundfile as sf

inspect_pair = runpy.run_path(str(Path(__file__).resolve().parents[1]/'scripts/measure-echo.py'))['inspect_pair']


class EchoFilesTests(unittest.TestCase):
    def test_bounded_sampling_of_longer_files_and_preservation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            x = np.random.default_rng(123).uniform(-.2,.2,21*16000)
            y = np.r_[np.zeros(800),x[:-800]*.5]
            a,b = root/'system.wav',root/'mic.wav'
            sf.write(a,x,16000,subtype='FLOAT');sf.write(b,y,16000,subtype='FLOAT')
            before = a.read_bytes(), b.read_bytes()
            result = inspect_pair(a,b,max_windows=3)
            self.assertEqual(len(result['windows']),3)
            self.assertEqual(result['summary']['status'],'consistent_lag_trend')
            self.assertAlmostEqual(result['summary']['lag_trend_ppm'],0.)
            self.assertEqual(before,(a.read_bytes(),b.read_bytes()))
            self.assertNotIn(str(root),str(result))

    def test_rate_rejection_and_no_common_time(self):
        with tempfile.TemporaryDirectory() as tmp:
            a = Path(tmp)/'a.wav'
            sf.write(a,np.zeros(16000),8000)
            with self.assertRaises(ValueError): inspect_pair(a,a)
            sf.write(a,np.zeros(16000),16000)
            result = inspect_pair(a,a,mic_start=2.)
            self.assertEqual(result['windows'],[])
            self.assertEqual(result['summary']['status'],'inconclusive')

    def test_fractional_origins_do_not_create_overlapping_windows(self):
        with tempfile.TemporaryDirectory() as tmp:
            a = Path(tmp)/'a.wav'
            sf.write(a,np.zeros(15*16000),16000)
            for origin in (.001,.37):
                report = inspect_pair(a,a,system_start=origin,mic_start=origin,max_windows=3)
                self.assertEqual(len(report['windows']),3)
                for left,right in zip(report['windows'],report['windows'][1:]):
                    self.assertGreaterEqual(right['start']+1e-9,left['end'])
