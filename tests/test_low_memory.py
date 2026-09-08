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

    def test_four_thread_experiment_preserves_cpu_and_model_settings(self):
        import json,numpy as np
        from meeting_os.backends import ASR
        with tempfile.TemporaryDirectory() as t:
            model=Path(t)/'weights';model.touch()
            def run(command,**kwargs):
                self.assertIn('-ng',command)
                self.assertEqual(command[command.index('-t')+1],'4')
                self.assertEqual(command[command.index('-m')+1],str(model.resolve()))
                Path(command[command.index('-of')+1]).with_suffix('.json').write_text(json.dumps({'transcription':[]}))
            with patch('meeting_os.backends.run_guarded',side_effect=run):
                asr=ASR('cpp',model);asr.cpp_threads=4;asr.transcribe(np.zeros(16000))
    def test_pressure_gate_runs_before_pipeline_or_model_resolution(self):
        from meeting_os.cli import make_pipeline
        from meeting_os.resources import MemoryPressureError
        with patch('meeting_os.resources.check_pressure',side_effect=MemoryPressureError('pressure')),patch('meeting_os.cli.resolve_inference',side_effect=AssertionError('must not resolve or load models')):
            with self.assertRaises(MemoryPressureError):make_pipeline(None,None)
    def test_attention_trial_only_adds_nfa_flag_to_cpu_command(self):
        import json,numpy as np
        from meeting_os.backends import ASR
        with tempfile.TemporaryDirectory() as tmp:
            model=Path(tmp)/'model';model.touch();commands=[]
            def run(command,**kwargs):
                commands.append(command.copy())
                Path(command[command.index('-of')+1]).with_suffix('.json').write_text(json.dumps({'transcription':[]}))
            with patch('meeting_os.backends.run_guarded',side_effect=run):
                asr=ASR('cpp',model);asr.transcribe(np.zeros(16000));asr.flash_attention=False;asr.transcribe(np.zeros(16000))
            self.assertNotIn('-nfa',commands[0]);self.assertIn('-nfa',commands[1])
            for command in commands:
                self.assertIn('-ng',command);self.assertEqual(command[command.index('-t')+1],'2')
    def test_gpu_trial_only_removes_cpu_disable_flag(self):
        import json,numpy as np
        from meeting_os.backends import ASR
        with tempfile.TemporaryDirectory() as tmp:
            model=Path(tmp)/'model';model.touch();commands=[]
            def run(command,**kwargs):
                commands.append(command.copy())
                Path(command[command.index('-of')+1]).with_suffix('.json').write_text(json.dumps({'transcription':[]}))
            with patch('meeting_os.backends.run_guarded',side_effect=run):
                asr=ASR('cpp',model);asr.transcribe(np.zeros(16000));asr.use_gpu=True;asr.transcribe(np.zeros(16000))
            self.assertIn('-ng',commands[0]);self.assertNotIn('-ng',commands[1]);self.assertNotIn('-nfa',commands[1])
            self.assertEqual(commands[1][commands[1].index('-m')+1],str(model.resolve()))
            self.assertEqual(commands[1][commands[1].index('-t')+1],'2')
