import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, Mock

import numpy as np
import soundfile as sf


class SilentLiveTests(unittest.TestCase):
    def probe(self, path):
        spec = importlib.util.find_spec('meeting_os.audio_probe')
        self.assertIsNotNone(spec, 'Missing conservative digital silence probe')
        from meeting_os.audio_probe import digital_silence_duration
        return digital_silence_duration(path)

    def test_only_exact_silence_across_all_channels_can_skip_models(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'audio.wav'
            for subtype in ['PCM_16', 'FLOAT']:
                sf.write(p, np.zeros((4800, 2)), 48000, subtype=subtype)
                self.assertAlmostEqual(self.probe(p), .1)
            sf.write(p, np.full((4800, 2), -0.0), 48000, subtype='FLOAT')
            self.assertAlmostEqual(self.probe(p), .1)
            for values in [np.full((4800, 2), 1e-8), np.tile([.1, -.1], (4800, 1)),
                           np.full((4800, 2), np.nan), np.full((4800, 2), np.inf)]:
                sf.write(p, values, 48000, subtype='FLOAT')
                self.assertIsNone(self.probe(p))
            samples = np.zeros((4800, 2)); samples[-1, 1] = 1e-8
            sf.write(p, samples, 48000, subtype='FLOAT')
            self.assertIsNone(self.probe(p), 'Tail/channel two must not be overlooked')

    def test_double_precision_whisper_quiet_audio_is_not_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'quiet.wav'
            sf.write(p, np.full((1600, 2), 1e-200), 16000, subtype='DOUBLE')
            self.assertIsNone(self.probe(p))

    def test_unknown_empty_and_invalid_files_are_not_silence(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'audio.wav'
            self.assertIsNone(self.probe(p))
            p.write_bytes(b'not a wav')
            self.assertIsNone(self.probe(p))
            sf.write(p, np.zeros(0), 16000)
            self.assertIsNone(self.probe(p))

    def test_silent_worker_returns_duration_without_model_initialization(self):
        from meeting_os.cli import parser
        from meeting_os.live_worker import main
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); audio = root / 'zero.wav'
            sf.write(audio, np.zeros((1600, 2)), 16000, subtype='FLOAT')
            opts = vars(parser().parse_args(['--db', str(root/'test.sqlite'), 'record', str(root), '--live']))
            opts = {k: str(v) if isinstance(v, Path) else v for k,v in opts.items()}
            request = root / 'request.json'; result = root / 'result.json'
            request.write_text(json.dumps({'options':opts, 'path':str(audio), 'source':'system', 'offset':12, 'provisional':True}))
            with patch('sys.argv', ['worker', str(request), str(result)]), patch('meeting_os.cli.make_pipeline', side_effect=AssertionError('silence must not load models')), patch('meeting_os.store.Store', side_effect=AssertionError('silence must not open DB')):
                main()
            self.assertEqual(json.loads(result.read_text()), {'segments':[], 'turns':[], 'duration':.1})

    def test_nonzero_worker_preserves_pipeline_arguments_and_closes_store(self):
        from meeting_os.live_worker import main
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); audio = root/'speech.wav'
            sf.write(audio, np.full(1600, .01), 16000)
            request = root/'request.json'; result = root/'result.json'
            request.write_text(json.dumps({'options':{'db':str(root/'db'), 'vocabulary':str(root/'vocab')}, 'path':str(audio), 'source':'mic', 'offset':24, 'provisional':True}))
            pipeline = Mock(); pipeline.process.return_value = ([], [], .1)
            with patch('sys.argv', ['worker', str(request), str(result)]), patch('meeting_os.cli.make_pipeline', return_value=pipeline), patch('meeting_os.store.Store') as store:
                main()
                pipeline.process.assert_called_once_with(str(audio), 'mic', 24, True)
                store.return_value.close.assert_called_once()
            self.assertEqual(json.loads(result.read_text())['duration'], .1)

    def test_probe_bounds_and_block_tail(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)/'audio.wav'
            samples = np.zeros((32769, 2)); samples[-1, -1] = .1
            sf.write(p, samples, 16000, subtype='FLOAT')
            self.assertIsNone(self.probe(p))
            sf.write(p, np.zeros(16000*66), 16000)
            self.assertIsNone(self.probe(p))

    def test_zero_duration_matches_normal_pipeline_resampling(self):
        from meeting_os.pipeline import Pipeline
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)/'audio.wav'
            for rate in (16000, 44100, 48000):
                sf.write(p, np.zeros((1601, 2)), rate, subtype='FLOAT')
                expected = Pipeline(None,None,None).process(p)[2]
                self.assertEqual(self.probe(p), expected)
