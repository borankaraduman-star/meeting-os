import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
import soundfile as sf
from meeting_os.audio import assemble_capture
from meeting_os.backends import ASR

class AudioPrecisionTests(unittest.TestCase):
    def test_assembly_preserves_float_peaks_and_quiet_samples_with_gap(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); raw=root/'system.wav'
            samples=np.array([-1.08,-.000001,0,.000001,1.08],dtype=np.float32)
            sf.write(raw,samples,16000,subtype='FLOAT')
            (root/'events.jsonl').write_text(json.dumps({'event':'chunk','source':'system','path':str(raw),'start':.25}))
            out=assemble_capture(root)
            actual,rate=sf.read(out['system'],dtype='float32')
            self.assertEqual(rate,16000)
            np.testing.assert_array_equal(actual[:4000],np.zeros(4000))
            np.testing.assert_array_equal(actual[4000:],samples)
            np.testing.assert_array_equal(sf.read(raw,dtype='float32')[0],samples)

    def test_cpp_serial_and_batch_receive_unchanged_float_samples(self):
        with tempfile.TemporaryDirectory() as tmp:
            model=Path(tmp)/'model';model.touch();asr=ASR('cpp',model)
            samples=np.array([-1.08,-.000001,0,.000001,1.08],dtype=np.float32)
            def native(command,**kwargs):
                inputs=[command[i+1] for i,x in enumerate(command) if x=='-f']
                outputs=[command[i+1] for i,x in enumerate(command) if x=='-of']
                for inp,out in zip(inputs,outputs):
                    actual,rate=sf.read(inp,dtype='float32')
                    self.assertEqual(rate,16000)
                    np.testing.assert_array_equal(actual,samples)
                    Path(out).with_suffix('.json').write_text('{"transcription":[]}')
            with patch('meeting_os.backends.run_guarded',side_effect=native):
                for batch in (False,True):
                    with self.subTest(batch=batch):
                        if batch:asr.transcribe_batch([samples,samples])
                        else:asr.transcribe(samples)

    def test_assembly_refuses_insufficient_space_before_creating_output(self):
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);raw=root/'system.wav';sf.write(raw,np.zeros(16000),16000,subtype='FLOAT')
            (root/'events.jsonl').write_text(json.dumps({'event':'chunk','source':'system','path':str(raw),'start':0}))
            with patch('shutil.disk_usage',return_value=SimpleNamespace(free=1024)):
                with self.assertRaises(OSError):assemble_capture(root)
            self.assertFalse((root/'system-full.wav').exists())
            self.assertTrue(raw.exists())
