import tempfile,unittest
from pathlib import Path
import numpy as np
from meeting_os.store import Store
from meeting_os.asr_checkpoints import CheckpointASR

class Backend:
    engine='cpp';language='tr';prompt='';cpp_threads=2;flash_attention=True;use_gpu=False
    def __init__(self,root):
        self.model=str(root/'model');self.cpp_bin=str(root/'binary');self.calls=[];self.fail=False
    def transcribe(self,a):
        self.calls.append(float(a[0]))
        if self.fail:raise RuntimeError('interrupted')
        return [{'start':0.,'end':1.,'text':'test','words':[]}]

class CheckpointTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        for f in ('model','binary'):(self.root/f).write_bytes(b'fixture')
        (self.root/'binary').chmod(0o700)
        self.store=Store(self.root/'db');self.mid=self.store.create_meeting('test');self.backend=Backend(self.root)
        self.a=np.zeros(16000,dtype=np.float32);self.b=np.ones(16000,dtype=np.float32)*.1
    def tearDown(self):self.store.close();self.temp.cleanup()
    def test_resume_reuses_only_completed_exact_region(self):
        cache=CheckpointASR(self.backend,self.store,self.mid)
        first=cache.transcribe(self.a);self.backend.fail=True
        with self.assertRaises(RuntimeError):cache.transcribe(self.b)
        resumed_backend=Backend(self.root);resumed=CheckpointASR(resumed_backend,self.store,self.mid)
        self.assertEqual(resumed.transcribe(self.a),first);resumed.transcribe(self.b)
        self.assertEqual(resumed_backend.calls,[float(self.b[0])])
        self.assertEqual((resumed.hits,resumed.misses),(1,1))
    def test_changed_prompt_and_model_invalidate(self):
        CheckpointASR(self.backend,self.store,self.mid).transcribe(self.a)
        self.backend.prompt='Boran';CheckpointASR(self.backend,self.store,self.mid).transcribe(self.a)
        (self.root/'model').write_bytes(b'changed');CheckpointASR(self.backend,self.store,self.mid).transcribe(self.a)
        self.assertEqual(len(self.backend.calls),3)
    def test_midcall_model_change_rejects_output(self):
        cache=CheckpointASR(self.backend,self.store,self.mid)
        def changed(a):
            (self.root/'model').write_bytes(b'changed');return [{'start':0,'end':1,'text':'wrong'}]
        self.backend.transcribe=changed
        with self.assertRaises(ValueError):cache.transcribe(self.a)
        self.assertEqual(self.store.db.execute('select count(*) from asr_checkpoints').fetchone()[0],0)
    def test_meeting_deletion_cascades_and_does_not_change_transcript(self):
        CheckpointASR(self.backend,self.store,self.mid).transcribe(self.a)
        self.assertEqual(self.store.segments(self.mid),[])
        with self.store.db:self.store.db.execute('delete from meetings where id=?',(self.mid,))
        self.assertEqual(self.store.db.execute('select count(*) from asr_checkpoints').fetchone()[0],0)

    def test_corrupt_entry_recomputed_and_empty_result_is_valid(self):
        cache=CheckpointASR(self.backend,self.store,self.mid);cache.transcribe(self.a)
        with self.store.db:self.store.db.execute("update asr_checkpoints set payload='not json'")
        cache.transcribe(self.a);self.assertEqual(len(self.backend.calls),2)
        self.backend.transcribe=lambda a:[]
        self.assertEqual(cache.transcribe(self.b),[])
        self.backend.transcribe=lambda a:(_ for _ in ()).throw(AssertionError('must hit empty'))
        self.assertEqual(cache.transcribe(self.b),[])
    def test_payload_budget_evicts_oldest_and_oversized_entry_not_stored(self):
        from unittest.mock import patch
        cache=CheckpointASR(self.backend,self.store,self.mid)
        with patch('meeting_os.asr_checkpoints.MAX_BYTES',100):
            cache.transcribe(self.a);cache.transcribe(self.b)
            self.assertLessEqual(self.store.db.execute('select coalesce(sum(bytes),0) from asr_checkpoints').fetchone()[0],100)
            cache.transcribe(self.a);self.assertEqual(len(self.backend.calls),3)
        with patch('meeting_os.asr_checkpoints.MAX_ENTRY',1):
            cache.transcribe(self.b)
        self.assertEqual(self.store.db.execute('select count(*) from asr_checkpoints').fetchone()[0],1)

    def test_valid_json_payload_corruption_does_not_change_transcript(self):
        cache=CheckpointASR(self.backend,self.store,self.mid);cache.transcribe(self.a)
        with self.store.db:self.store.db.execute("update asr_checkpoints set payload=replace(payload,'test','fake')")
        self.assertEqual(cache.transcribe(self.a)[0]['text'],'test')
        self.assertEqual(len(self.backend.calls),2)

    def test_empty_rows_still_obey_entry_count_cap(self):
        from unittest.mock import patch
        self.backend.transcribe=lambda a:[]
        cache=CheckpointASR(self.backend,self.store,self.mid)
        with patch('meeting_os.asr_checkpoints.MAX_ENTRIES',1):
            cache.transcribe(self.a);cache.transcribe(self.b)
        self.assertEqual(self.store.db.execute('select count(*) from asr_checkpoints').fetchone()[0],1)

    def test_cached_text_still_recomputes_identity_and_offsets(self):
        import soundfile as sf
        from unittest.mock import patch
        from meeting_os.pipeline import Pipeline
        class Emb:
            model_id='fixture'
            def embed(self,a):return [1.,0.]
        class Diar:
            mode='cluster';embedder=Emb()
            def turns(self,a,s):return [(0,1,s+':S0')]
        wav=self.root/'audio.wav';sf.write(wav,self.a,16000,subtype='FLOAT')
        cache=CheckpointASR(self.backend,self.store,self.mid)
        with patch('meeting_os.pipeline.speech_regions',new=lambda a:[(0,16000)]):
            first,_,_=Pipeline(cache,Diar(),self.store).process(wav,offset=4)
            self.store.enroll('Boran',[1.,0.],'fixture',3,'test')
            second,_,_=Pipeline(cache,Diar(),self.store).process(wav,offset=4)
        self.assertIsNone(first[0].speaker_name)
        self.assertEqual(second[0].speaker_name,'Boran')
        self.assertEqual((second[0].start,second[0].end),(4,5))
        self.assertEqual(second[0].text,first[0].text)
        self.assertEqual(len(self.backend.calls),1)

    def test_retargeted_binary_symlink_cannot_hit_old_checkpoint(self):
        link=self.root/'link';link.symlink_to(self.root/'binary');self.backend.cpp_bin=str(link)
        cache=CheckpointASR(self.backend,self.store,self.mid);cache.transcribe(self.a)
        other=self.root/'other';other.write_bytes(b'other');other.chmod(0o700)
        link.unlink();link.symlink_to(other)
        with self.assertRaises(ValueError):cache.transcribe(self.a)
