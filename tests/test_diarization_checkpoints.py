import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
import soundfile as sf
from meeting_os.store import Store
from meeting_os.diarization_checkpoints import CheckpointDiarizer

class Backend:
    mode='sherpa';isolate_sherpa=True;threshold=.9
    def __init__(self,root):self.sherpa_root=root;self.calls=0;self.fail=False
    def turns_file(self,path,source,frames):
        self.calls+=1
        if self.fail:raise RuntimeError('interrupted')
        return [(0.,.8,source+':S0'),(.5,1.,source+':S1')]

class Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.artifact=self.root/'model';self.artifact.write_bytes(b'model')
        self.patch=patch('meeting_os.diarization_checkpoints.artifact_paths',return_value=[self.artifact]);self.patch.start();self.addCleanup(self.patch.stop)
        self.pressure=patch('meeting_os.asr_checkpoints.check_pressure');self.pressure.start();self.addCleanup(self.pressure.stop)
        self.store=Store(self.root/'db');self.addCleanup(self.store.close);self.mid=self.store.create_meeting('test',{})
        self.wav=self.root/'input.wav';sf.write(self.wav,np.zeros(16000,dtype=np.float32),16000,subtype='FLOAT')
        self.backend=Backend(self.root)
    def wrap(self):return CheckpointDiarizer(self.backend,self.store,self.mid)
    def test_completed_turns_survive_new_wrapper_with_overlaps(self):
        expected=self.wrap().turns_file(self.wav,'mic',16000)
        self.backend.fail=True
        self.assertEqual(self.wrap().turns_file(self.wav,'mic',16000),expected)
        self.assertEqual(self.backend.calls,1)
    def test_interruption_not_cached(self):
        w=self.wrap();self.backend.fail=True
        with self.assertRaises(RuntimeError):w.turns_file(self.wav,'mic',16000)
        self.assertEqual(self.store.db.execute('select count(*) from diarization_checkpoints').fetchone()[0],0)
    def test_audio_source_threshold_and_artifact_invalidate(self):
        self.wrap().turns_file(self.wav,'mic',16000)
        sf.write(self.wav,np.ones(16000,dtype=np.float32)*.1,16000,subtype='FLOAT')
        self.wrap().turns_file(self.wav,'mic',16000)
        self.wrap().turns_file(self.wav,'system',16000)
        self.backend.threshold=.8;self.wrap().turns_file(self.wav,'mic',16000)
        self.artifact.write_bytes(b'new model');self.wrap().turns_file(self.wav,'mic',16000)
        self.assertEqual(self.backend.calls,5)
    def test_corruption_recomputed_and_delete_cascades(self):
        self.wrap().turns_file(self.wav,'mic',16000)
        with self.store.db:self.store.db.execute("update diarization_checkpoints set payload='[]'")
        self.wrap().turns_file(self.wav,'mic',16000);self.assertEqual(self.backend.calls,2)
        with self.store.db:self.store.db.execute('delete from meetings where id=?',(self.mid,))
        self.assertEqual(self.store.db.execute('select count(*) from diarization_checkpoints').fetchone()[0],0)
    def test_mid_processing_audio_mutation_not_cached(self):
        def mutate(*args):
            sf.write(self.wav,np.ones(16000,dtype=np.float32),16000,subtype='FLOAT')
            return [(0.,1.,'mic:S0')]
        self.backend.turns_file=mutate
        with self.assertRaises(ValueError):self.wrap().turns_file(self.wav,'mic',16000)
        self.assertEqual(self.store.db.execute('select count(*) from diarization_checkpoints').fetchone()[0],0)
    def test_capacity_and_invalid_timeline(self):
        with patch('meeting_os.diarization_checkpoints.MAX_ENTRIES',1):
            self.wrap().turns_file(self.wav,'mic',16000)
            self.wrap().turns_file(self.wav,'system',16000)
        self.assertEqual(self.store.db.execute('select count(*) from diarization_checkpoints').fetchone()[0],1)
        self.backend.turns_file=lambda *a:[(0.,2.,'mic:S0')]
        with self.assertRaises(ValueError):self.wrap().turns_file(self.wav,'mic',16000)
    def test_mid_processing_model_mutation_rejected(self):
        def mutate(*args):
            self.artifact.write_bytes(b'changed')
            return [(0.,1.,'mic:S0')]
        self.backend.turns_file=mutate
        with self.assertRaises(ValueError):self.wrap().turns_file(self.wav,'mic',16000)
        self.assertEqual(self.store.db.execute('select count(*) from diarization_checkpoints').fetchone()[0],0)
    def test_oversized_result_not_stored_and_empty_turns_reused(self):
        with patch('meeting_os.diarization_checkpoints.MAX_ENTRY',1):
            self.wrap().turns_file(self.wav,'mic',16000)
        self.assertEqual(self.store.db.execute('select count(*) from diarization_checkpoints').fetchone()[0],0)
        self.backend.turns_file=lambda *a:[]
        self.assertEqual(self.wrap().turns_file(self.wav,'mic',16000),[])
        w=self.wrap();self.assertEqual(w.turns_file(self.wav,'mic',16000),[]);self.assertEqual(w.hits,1)
    def test_reassembled_snapshot_timestamp_does_not_recompute(self):
        import struct
        first=self.wrap().turns_file(self.wav,'mic',16000)
        raw=bytearray(self.wav.read_bytes());peak=raw.index(b'PEAK')
        raw[peak+12:peak+16]=struct.pack('<I',123)
        self.wav.write_bytes(raw)
        self.backend.fail=True
        w=self.wrap();self.assertEqual(w.turns_file(self.wav,'mic',16000),first)
        self.assertEqual(w.hits,1);self.assertEqual(self.backend.calls,1)
