import unittest
from meeting_os.speaker_windows import group_regions

class SpeakerWindowTests(unittest.TestCase):
    def test_same_speaker_keeps_real_gap_and_sample_coordinates(self):
        self.assertEqual(group_regions([(0,16000),(20000,40000)],[(0,2.5,'system:S0')]),[(0,40000)])
    def test_other_speaker_inside_gap_or_region_blocks_merge(self):
        regions=[(0,16000),(20000,40000)]
        for turn in ((1.05,1.15,'system:S1'),(.4,.5,'system:S1')):
            with self.subTest(turn=turn):
                self.assertEqual(group_regions(regions,[(0,2.5,'system:S0'),turn]),regions)
    def test_unknown_labels_missing_coverage_and_distant_speech_stay_separate(self):
        regions=[(0,16000),(20000,40000)]
        for turns in ([],[(0,2.5,'unknown')],[(0,2.5,'system:unknown')],[(.5,.6,'system:S0'),(1.5,1.6,'system:S0')]):
            with self.subTest(turns=turns):self.assertEqual(group_regions(regions,turns),regions)
        far=[(0,16000),(48000,64000)]
        self.assertEqual(group_regions(far,[(0,4,'S0')]),far)
    def test_window_limit_and_input_boundaries(self):
        regions=[(0,96000),(100000,196000)]
        self.assertEqual(group_regions(regions,[(0,13,'S0')]),regions)
        for regions in ([(5,2)],[(3,7),(1,2)],[(0,16000),(15000,17000)]):
            with self.assertRaises(ValueError):group_regions(regions,[(0,2,'S0')])
    def test_short_uncovered_edges_only_allow_bounded_padding(self):
        regions=[(0,16000),(20000,40000)]
        self.assertEqual(group_regions(regions,[(.1,.9,'S0'),(1.35,2.4,'S0')]),[(0,40000)])
        self.assertEqual(group_regions(regions,[(.4,.9,'S0'),(1.35,2.4,'S0')]),regions)

    def test_pipeline_opt_in_reduces_calls_without_stitching_or_offset_shift(self):
        import tempfile
        from pathlib import Path
        from unittest.mock import patch
        import numpy as np
        import soundfile as sf
        from meeting_os.pipeline import Pipeline
        from meeting_os.store import Store
        class Asr:
            engine='cpp'
            def __init__(self,enabled):self.same_speaker_windows=enabled;self.calls=[]
            def transcribe(self,a):
                self.calls.append(a.copy())
                return [{'start':0,'end':len(a)/16000,'text':'test','words':[]}]
        class Emb:
            model_id='fixture'
            def embed(self,a):return None
        class Diar:
            mode='sherpa';embedder=Emb()
            def turns(self,a,s):return [(0,2.5,'system:S0')]
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);x=np.linspace(-.1,.1,40000,dtype=np.float32);wav=root/'a.wav';sf.write(wav,x,16000,subtype='FLOAT')
            for enabled,live,count in ((False,True,2),(True,True,1),(True,False,2)):
                with self.subTest(enabled=enabled,live=live):
                    asr=Asr(enabled);store=Store(root/f'{enabled}-{live}.sqlite')
                    try:
                        with patch('meeting_os.pipeline.speech_regions',return_value=[(0,16000),(20000,40000)]):
                            rows,turns,duration=Pipeline(asr,Diar(),store).process(wav,offset=7,provisional=live)
                        self.assertEqual(len(asr.calls),count)
                        self.assertEqual(rows[0].start,7)
                        if count==1:
                            np.testing.assert_array_equal(asr.calls[0],x)
                            self.assertEqual(rows[0].end,9.5)
                            self.assertEqual(rows[0].metrics['asr_window_regions'],2)
                    finally:store.close()
