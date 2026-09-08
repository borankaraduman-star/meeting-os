import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
import soundfile as sf
from meeting_os.isolated_diarization import isolated_turns

class IsolatedDiarizationTests(unittest.TestCase):
    def test_exact_samples_and_turns_with_cleanup(self):
        seen=[];audio=np.array([-.001,1.05,.2]*16000,dtype=np.float32)
        def native(cmd,**kwargs):
            inp=Path(cmd[cmd.index('--audio')+1]);out=Path(cmd[cmd.index('--output')+1]);seen.append(inp)
            np.testing.assert_array_equal(sf.read(inp,dtype='float32')[0],audio)
            self.assertEqual(cmd[cmd.index('--threshold')+1],'0.9')
            out.write_text(json.dumps([[.25,2.5,'mic:S0']]))
        with patch('meeting_os.isolated_diarization.run_guarded',side_effect=native):
            self.assertEqual(isolated_turns(audio,'mic',Path('/models'),.9),[(.25,2.5,'mic:S0')])
        self.assertFalse(seen[0].parent.exists())
    def test_malformed_output_cannot_be_used_as_speaker_turns(self):
        for value in ([[0,4,'mic:S0']],[[2,1,'mic:S0']],[[0,1,'system:S0']],[[float('nan'),1,'mic:S0']]):
            def native(cmd,**kwargs):Path(cmd[cmd.index('--output')+1]).write_text(json.dumps(value))
            with self.subTest(value=value),patch('meeting_os.isolated_diarization.run_guarded',side_effect=native):
                with self.assertRaises(ValueError):isolated_turns(np.zeros(16000),'mic',Path('/models'),.9)
    def test_worker_failure_propagates_and_cleans_audio(self):
        seen=[]
        def native(cmd,**kwargs):
            seen.append(Path(cmd[cmd.index('--audio')+1]));raise RuntimeError('worker failure')
        with patch('meeting_os.isolated_diarization.run_guarded',side_effect=native):
            with self.assertRaises(RuntimeError):isolated_turns(np.zeros(16000),'mic',Path('/models'),.9)
        self.assertFalse(seen[0].exists())

    def test_diarizer_opt_in_routes_without_parent_native_model(self):
        from meeting_os.speakers import Diarizer
        diar=object.__new__(Diarizer);diar.mode='sherpa';diar.isolate_sherpa=True;diar.sherpa_root=Path('/models');diar.threshold=.9
        audio=np.zeros(16000,dtype=np.float32)
        with patch('meeting_os.isolated_diarization.isolated_turns',return_value=[(0,1,'mic:S0')]):
            self.assertEqual(diar.turns(audio,'mic'),[(0,1,'mic:S0')])

    def test_factory_enables_isolation_only_for_low_memory_sherpa(self):
        from types import SimpleNamespace
        from meeting_os.cli import make_pipeline,parser
        def diarizer(*args,**kwargs):return SimpleNamespace(isolate_sherpa=kwargs.get('isolate_sherpa',False))
        with tempfile.TemporaryDirectory() as tmp:
            model=Path(tmp)/'model';model.touch()
            for low,mode,expected in ((True,'sherpa',True),(False,'sherpa',False),(True,'cluster',False)):
                args=parser().parse_args(['transcribe','unused.wav','--engine','cpp','--model',str(model),'--diarization',mode])
                with self.subTest(low=low,mode=mode),patch('meeting_os.resources.low_memory_mac',return_value=low),patch('meeting_os.resources.check_pressure'),patch('meeting_os.speakers.Embedder',return_value=SimpleNamespace(model_id='test')),patch('meeting_os.speakers.Diarizer',side_effect=diarizer):
                    pipeline=make_pipeline(args,SimpleNamespace(profiles=lambda:[]))
                    self.assertEqual(pipeline.diarizer.isolate_sherpa,expected)

    def test_overlapping_speakers_are_preserved_in_start_order(self):
        turns=[[0,.8,'mic:S0'],[.4,1,'mic:S1']]
        def native(cmd,**kwargs):Path(cmd[cmd.index('--output')+1]).write_text(json.dumps(turns))
        with patch('meeting_os.isolated_diarization.run_guarded',side_effect=native):
            self.assertEqual(isolated_turns(np.zeros(16000),'mic',Path('/models'),.9),[(0,.8,'mic:S0'),(.4,1,'mic:S1')])

    def test_file_handoff_uses_existing_snapshot_and_rejects_change(self):
        from meeting_os.isolated_diarization import isolated_file_turns
        with tempfile.TemporaryDirectory() as tmp:
            wav=Path(tmp)/'audio.wav';sf.write(wav,np.zeros(16000),16000,subtype='FLOAT')
            for mutate in (False,True):
                def native(cmd,**kwargs):
                    self.assertEqual(Path(cmd[cmd.index('--audio')+1]),wav.resolve())
                    Path(cmd[cmd.index('--output')+1]).write_text('[[0,1,"mic:S0"]]')
                    if mutate:sf.write(wav,np.ones(16000)*.2,16000,subtype='FLOAT')
                with patch('meeting_os.isolated_diarization.run_guarded',side_effect=native):
                    if mutate:
                        with self.assertRaises(ValueError):isolated_file_turns(wav,'mic',Path('/models'),.9,16000)
                    else:self.assertEqual(isolated_file_turns(wav,'mic',Path('/models'),.9,16000),[(0,1,'mic:S0')])
            with self.assertRaises(ValueError):isolated_file_turns(wav,'mic',Path('/models'),.9,32000)
            self.assertTrue(wav.exists())

    def test_owned_worker_audio_avoids_copy_but_default_remains_defensive(self):
        from types import SimpleNamespace
        from meeting_os.speakers import Diarizer
        audio=np.ones(16000,dtype=np.float32);shared=[]
        class Native:
            def __init__(self,cfg):pass
            def process(self,value):
                shared.append(np.shares_memory(value,audio))
                return SimpleNamespace(sort_by_start_time=lambda:[])
        diar=object.__new__(Diarizer);diar.mode='sherpa';diar.isolate_sherpa=False;diar.sherpa_config=None
        with patch.dict('sys.modules',{'sherpa_onnx':SimpleNamespace(OfflineSpeakerDiarization=Native)}):
            diar.turns(audio,'mic')
            diar.turns(audio,'mic',owned_audio=True)
        self.assertEqual(shared,[False,True])
