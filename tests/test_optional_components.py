"""The bundle carries no local-model library (docs/BUNDLE.md "Ses izi ve VAD: torch'suz"): choosing one of those
paths must end in a Turkish sentence that says what to do, never a raw ModuleNotFoundError."""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from meeting_os.optional import MissingComponent, require


class OptionalComponents(unittest.TestCase):
    def test_missing_library_is_a_turkish_sentence_pointing_at_the_cloud_mode(self):
        with patch.dict(sys.modules, {'mlx_whisper': None}):
            with self.assertRaises(MissingComponent) as caught: require('mlx_whisper', 'Yerel yazıya çevirme (MLX)')
        text = str(caught.exception)
        self.assertIn('“mlx_whisper” paketi yok', text)
        self.assertIn('OpenRouter (bulut)', text)
        self.assertIsInstance(caught.exception, ValueError)   # the CLI prints ValueErrors as one line, no traceback

    def test_missing_onnxruntime_says_reinstall(self):
        with patch.dict(sys.modules, {'onnxruntime': None}):
            with self.assertRaisesRegex(MissingComponent, 'yeniden indirip kurun'): require('onnxruntime', 'Ses izi')

    def test_local_engines_fail_with_the_sentence_before_any_model_check(self):
        from meeting_os.backends import ASR
        with tempfile.TemporaryDirectory() as tmp:
            model = Path(tmp)/'model'; model.mkdir()
            for engine, module in (('mlx', 'mlx_whisper'), ('whisper', 'whisper')):
                with self.subTest(engine=engine), patch.dict(sys.modules, {module: None}):
                    with self.assertRaisesRegex(MissingComponent, 'OpenRouter'): ASR(engine, model)
        with self.assertRaisesRegex(ValueError, 'Yerel yazıya çevirme modeli bu Mac’te yok'): ASR('cpp', None)

    def test_local_analysis_without_its_model_names_the_cloud_mode(self):
        from meeting_os.llm import LocalLLM
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError, 'OpenRouter'): LocalLLM(tmp)

    def test_auto_engine_never_picks_mlx_when_it_is_not_installed(self):
        from meeting_os.cli import parser, resolve_inference
        a = parser().parse_args(['import', 'audio.wav'])
        with patch('meeting_os.resources.physical_memory', return_value=64*1024**3), \
             patch('importlib.util.find_spec', side_effect=lambda name, *rest: None if name == 'mlx_whisper' else object()):
            resolve_inference(a)
        self.assertEqual(a.engine, 'cpp')

    def test_voice_encoder_refuses_torch_weights_in_a_sentence(self):
        from meeting_os.voice_encoder import VoiceEncoder
        with tempfile.TemporaryDirectory() as tmp:
            weights = Path(tmp)/'pretrained.pt'; weights.write_bytes(b'not onnx')
            with self.assertRaisesRegex(ValueError, 'convert-resemblyzer-onnx'): VoiceEncoder(weights)


if __name__ == '__main__':
    unittest.main()
