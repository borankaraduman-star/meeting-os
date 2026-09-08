import tempfile, unittest
from pathlib import Path
from unittest.mock import patch
from meeting_os.cli import parser

class LowMemoryTests(unittest.TestCase):
    def test_small_mac_selects_cpu_quantized_model(self):
        from meeting_os.cli import resolve_inference
        a=parser().parse_args(['import','audio.wav'])
        with patch('meeting_os.resources.physical_memory',return_value=16*1024**3):resolve_inference(a)
        self.assertEqual(a.engine,'cpp')
        self.assertEqual(Path(a.model).name,'ggml-large-v3-turbo-q5_0.bin')
    def test_explicit_engine_keeps_its_matching_model(self):
        from meeting_os.cli import resolve_inference
        a=parser().parse_args(['import','audio.wav','--engine','mlx'])
        resolve_inference(a)
        self.assertEqual(a.engine,'mlx');self.assertEqual(Path(a.model).name,'mlx-turbo')
    def test_explicit_custom_model_requires_engine_with_auto(self):
        from meeting_os.cli import resolve_inference
        a=parser().parse_args(['import','audio.wav','--model','custom'])
        with self.assertRaisesRegex(ValueError,'engine'):resolve_inference(a)
    def test_cpp_is_cpu_only_and_two_threads(self):
        import json,numpy as np
        from meeting_os.backends import ASR
        with tempfile.TemporaryDirectory() as t:
            model=Path(t)/'weights';model.touch()
            def run(command,**kwargs):
                prefix=Path(command[command.index('-of')+1])
                prefix.with_suffix('.json').write_text(json.dumps({'transcription':[]}))
                self.assertIn('-ng',command);self.assertEqual(command[command.index('-t')+1],'2')
            with patch('meeting_os.backends.run_guarded',side_effect=run):
                ASR('cpp',model).transcribe(np.zeros(16000))
