import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
import soundfile as sf
from meeting_os.audio import assemble_capture,speech_regions
from meeting_os.pipeline import Pipeline
from meeting_os.store import Store
from meeting_os.speakers import speaker_at
import json
class PipelineTests(unittest.TestCase):
    def test_capture_preserves_offsets_and_separate_sources(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); events=[]
            for src,offset,value in [('mic',.25,.1),('system',.5,.2)]:
                path=root/(src+'.wav'); sf.write(path,np.full(16000,value),16000)
                events.append({'event':'chunk','source':src,'path':str(path),'start':offset,'duration':1})
            (root/'events.jsonl').write_text('\n'.join(json.dumps(e) for e in events))
            output=assemble_capture(root)
            mic,_=sf.read(output['mic']); system,_=sf.read(output['system'])
            self.assertEqual(len(mic),20000); self.assertEqual(len(system),24000)
            self.assertTrue(np.all(mic[:4000]==0)); self.assertAlmostEqual(system[-1],.2,places=3)
    def test_silence_skips_models(self): self.assertEqual(speech_regions(np.zeros(16000,dtype=np.float32)),[])
    def test_overlapping_turns_ambiguous(self): self.assertTrue(speaker_at(0,3,[(0,3,'a'),(1,2,'b')])[1])
    def test_timestamps_and_no_training(self):
        class ASR:
            def transcribe(self,x): return [{'start':0,'end':2,'text':'İpek rollout','avg_logprob':-1,'words':[{'word':'İpek','start':0,'end':1}]}]
        class Emb:
            model_id='test'
            def embed(self,x): return [1.,0.]
        class Diar:
            embedder=Emb(); mode='cluster'
            def turns(self,a,s): return [(1,3,s+':S0')]
        with tempfile.TemporaryDirectory() as tmp:
            wav=Path(tmp)/'a.wav'; sf.write(wav,np.ones(64000)*.1,16000); db=Store(Path(tmp)/'db')
            with patch('meeting_os.pipeline.speech_regions',return_value=[(16000,48000)]):
                rows,_,_=Pipeline(ASR(),Diar(),db).process(wav,offset=12)
            self.assertEqual((rows[0].start,rows[0].end),(13,15)); self.assertEqual(rows[0].words[0]['start'],13)
            self.assertIn('low_asr_confidence',rows[0].flags); self.assertEqual(db.profiles(),[]); db.close()
