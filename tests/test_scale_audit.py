"""Scale audit: what a long meeting on a nearly full disk does to assembly, compaction and the cloud queue."""
import json,os,tempfile,threading,time,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import numpy as np
import soundfile as sf
from meeting_os import audio
from meeting_os.audio import adoptable_full_files,assemble_capture,journal_source_ends
from meeting_os.cloud_finalize import compact_capture,finalize_capture,note_cloud_failure,transcribe_sources
from meeting_os.store import Store


def capture_dir(root,seconds=4,sources=('mic','system'),name='rec'):
    """Two-source capture journal; the mic carries speech-shaped noise so no piece is skipped as silent."""
    d=Path(root)/name;d.mkdir();events=[]
    rng=np.random.default_rng(7)
    for index,source in enumerate(sources):
        t=np.arange(16000*seconds)/16000
        signal=(0.3*np.sin(2*np.pi*(220+110*index)*t)+0.05*rng.standard_normal(len(t))).astype('float32')
        path=d/f'{source}-000000.wav';sf.write(path,signal,16000,subtype='FLOAT')
        events.append({'event':'chunk','source':source,'start':0,'duration':seconds,'path':str(path),'sample_rate':16000,'index':0})
    (d/'capture-native.jsonl').write_text('\n'.join(json.dumps(e) for e in events)+'\n')
    return d


class EchoFreeClient:
    def __init__(self):self.calls=[];self.lock=threading.Lock()
    def transcribe(self,audio,fmt,*,model,consent,diarize=False,timeout=90,**kw):
        with self.lock:self.calls.append(len(audio))
        return {'text':'metin','usage':{'seconds':1,'cost':0.0001}}


class InterruptedAssemblyTests(unittest.TestCase):
    """P0-1: a killed assembler used to leave a readable but shorter `*-full.wav` that the next run adopted."""

    def test_assembly_publishes_the_name_only_when_the_file_is_whole(self):
        with tempfile.TemporaryDirectory() as tmp:
            d=capture_dir(tmp,seconds=3)
            real=audio.read_audio
            def read(path):
                # Mic is assembled first: while it is being written only the temporary name may exist.
                if not (d/'mic-full.wav').exists():
                    self.assertTrue((d/'mic-full.wav.tmp').is_file())
                return real(path)
            with patch.object(audio,'read_audio',side_effect=read):
                out=assemble_capture(d)
            self.assertEqual(sorted(Path(p).name for p in out.values()),['mic-full.wav','system-full.wav'])
            self.assertEqual(list(d.glob('*.tmp')),[])

    def test_a_killed_writer_leaves_nothing_that_can_be_adopted(self):
        """The kill: a partial `*-full.wav.tmp` on disk and no rename. Resume must ignore it, and sweep it
        once it is old enough to be nobody's work in progress — a live assembler's file is left alone."""
        with tempfile.TemporaryDirectory() as tmp:
            d=capture_dir(tmp,seconds=3)
            partial=d/'mic-full.wav.tmp'
            sf.write(partial,np.zeros(16000,dtype='float32'),16000,subtype='FLOAT',format='WAV')
            sf.write(d/'system-full.wav',np.zeros(16000*3,dtype='float32'),16000,subtype='FLOAT')
            self.assertEqual(adoptable_full_files(d),{})       # mic never finished
            self.assertTrue(partial.exists())                  # written seconds ago: another assembler may own it
            os.utime(partial,(time.time()-7200,time.time()-7200))
            self.assertEqual(adoptable_full_files(d),{})
            self.assertFalse(partial.exists())                 # an hour on, the leftovers are gone
            rebuilt=assemble_capture(d)
            self.assertEqual(set(rebuilt),{'mic','system'})
            self.assertAlmostEqual(sf.info(rebuilt['mic']).duration,3.0,places=2)

    def test_a_truncated_full_file_is_rebuilt_not_adopted(self):
        with tempfile.TemporaryDirectory() as tmp:
            d=capture_dir(tmp,seconds=6)
            for source in ('mic','system'):   # what an interrupted in-place writer used to leave
                sf.write(d/f'{source}-full.wav',np.zeros(16000*2,dtype='float32'),16000,subtype='FLOAT')
            self.assertEqual(journal_source_ends(d),{'mic':6.0,'system':6.0})
            self.assertEqual(adoptable_full_files(d),{})
            out=assemble_capture(d)
            self.assertAlmostEqual(sf.info(out['system']).duration,6.0,places=2)

    def test_a_finished_pair_is_adopted_without_re_assembling(self):
        with tempfile.TemporaryDirectory() as tmp:
            d=capture_dir(tmp,seconds=3)
            assemble_capture(d)
            adopted=adoptable_full_files(d)
            self.assertEqual(sorted(adopted),['mic','system'])

    def test_finalize_rebuilds_instead_of_transcribing_a_fragment(self):
        with tempfile.TemporaryDirectory() as tmp:
            d=capture_dir(tmp,seconds=6);store=Store(Path(tmp)/'db.sqlite')
            sf.write(d/'mic-full.wav',np.zeros(16000,dtype='float32'),16000,subtype='FLOAT')   # 1 s of a 6 s meeting
            sf.write(d/'system-full.wav',np.zeros(16000,dtype='float32'),16000,subtype='FLOAT')
            mid=store.create_meeting('Yarım',{'capture_dir':str(d)});store.status(mid,'incomplete')
            finalize_capture(store,mid,tmp,consent=True,model='openai/gpt-transcribe',client=EchoFreeClient(),embedder=None)
            meta=json.loads(store.db.execute('SELECT metadata FROM meetings WHERE id=?',(mid,)).fetchone()[0])
            self.assertAlmostEqual(sf.info(meta['paths']['system']).duration,6.0,places=2)
            store.close()

    def test_chunks_are_not_compacted_while_a_source_has_no_full_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            d=capture_dir(tmp,seconds=3);store=Store(Path(tmp)/'db.sqlite')
            sf.write(d/'system-full.wav',np.zeros(16000*3,dtype='float32'),16000,subtype='FLOAT')
            mid=store.create_meeting('Tek kanal',{'capture_dir':str(d),'cloud_mode':'capture',
                'paths':{'system':str(d/'system-full.wav')}})
            store.status(mid,'complete')
            self.assertEqual(compact_capture(store,mid),0)
            self.assertTrue((d/'mic-000000.wav').is_file())   # the only way back to the missing channel
            store.close()


class AssemblyReservationTests(unittest.TestCase):
    """P0-2: the recorder stopped at 400 MB while assembly needed a gigabyte."""

    def test_space_is_reserved_for_every_source_before_the_first_is_written(self):
        with tempfile.TemporaryDirectory() as tmp:
            d=capture_dir(tmp,seconds=60)
            one_source=16000*60*4+4096+audio.ASSEMBLY_HEADROOM   # enough for the mic alone, not for both
            with patch('shutil.disk_usage',return_value=SimpleNamespace(free=one_source+1024**2)):
                with self.assertRaises(OSError) as caught: assemble_capture(d)
            self.assertEqual(caught.exception.errno,28)
            self.assertIn('Disk dolu',caught.exception.user_message)
            self.assertIn('MB',caught.exception.user_message)
            self.assertEqual(sorted(p.name for p in d.glob('*-full*')),[])   # neither source was started

    def test_an_out_of_space_write_removes_its_own_temporary(self):
        with tempfile.TemporaryDirectory() as tmp:
            d=capture_dir(tmp,seconds=2)
            import errno as E
            def boom(path):raise OSError(E.ENOSPC,'No space left on device')
            with patch.object(audio,'read_audio',side_effect=boom):
                with self.assertRaises(OSError) as caught: assemble_capture(d)
            self.assertEqual(caught.exception.errno,28)
            self.assertIn('Disk dolu',getattr(caught.exception,'user_message',''))
            self.assertEqual(list(d.glob('*.tmp')),[])
            self.assertFalse((d/'mic-full.wav').exists())

    def test_a_full_disk_does_not_spend_a_cloud_retry(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=Store(Path(tmp)/'db.sqlite')
            mid=store.create_meeting('Disk',{'cloud_retry_attempt':1,'cloud_attempt_open':True})
            error=note_cloud_failure(store,mid,audio.disk_full(1_100_000_000))
            meta=json.loads(store.db.execute('SELECT metadata FROM meetings WHERE id=?',(mid,)).fetchone()[0])
            self.assertEqual(error['kind'],'disk_full')
            self.assertIn('Disk dolu',error['message'])
            self.assertEqual(meta['cloud_retry_attempt'],1)   # not spent — and not given back either
            self.assertNotIn('cloud_attempt_open',meta)
            # A provider failure on the same meeting still counts.
            store.db.execute("UPDATE meetings SET metadata=? WHERE id=?",(json.dumps({'cloud_retry_attempt':1,'cloud_attempt_open':True}),mid));store.db.commit()
            note_cloud_failure(store,mid,ValueError('OpenRouter down'))
            meta=json.loads(store.db.execute('SELECT metadata FROM meetings WHERE id=?',(mid,)).fetchone()[0])
            self.assertEqual(meta['cloud_retry_attempt'],1)
            store.close()


    def test_a_disk_that_stays_full_for_two_days_becomes_an_ordinary_failure(self):
        """A full disk costs nothing while the user can still fix it. Costing nothing forever meant a meeting
        that never fits was offered to the idle queue every half hour for the life of the app."""
        from datetime import datetime,timedelta,timezone
        with tempfile.TemporaryDirectory() as tmp:
            store=Store(Path(tmp)/'db.sqlite')
            mid=store.create_meeting('Disk',{'cloud_retry_attempt':2,'cloud_attempt_open':True})
            note_cloud_failure(store,mid,audio.disk_full(1_100_000_000))
            meta=json.loads(store.db.execute('SELECT metadata FROM meetings WHERE id=?',(mid,)).fetchone()[0])
            self.assertEqual(meta['cloud_retry_attempt'],2);self.assertIn('cloud_disk_full_since',meta)
            meta['cloud_disk_full_since']=(datetime.now(timezone.utc)-timedelta(hours=49)).isoformat()
            store.db.execute("UPDATE meetings SET metadata=? WHERE id=?",(json.dumps(meta),mid));store.db.commit()
            note_cloud_failure(store,mid,audio.disk_full(1_100_000_000))
            meta=json.loads(store.db.execute('SELECT metadata FROM meetings WHERE id=?',(mid,)).fetchone()[0])
            self.assertEqual(meta['cloud_retry_attempt'],3)   # counted like any other failure now
            self.assertNotIn('cloud_disk_full_since',meta)
            store.close()

    def test_a_resumed_job_reports_only_the_seconds_of_this_run(self):
        """55 of 60 minutes were uploaded by an earlier run: the ETA must not claim one minute to go."""
        with tempfile.TemporaryDirectory() as tmp:
            d=capture_dir(tmp,seconds=180,sources=('system',));store=Store(Path(tmp)/'db.sqlite')
            mid=store.create_meeting('Devam',{'capture_dir':str(d)})
            sources=assemble_capture(d)
            progress=Path(tmp)/'progress.json'
            client=EchoFreeClient()
            transcribe_sources(store,mid,sources,client,consent=True,model='openai/gpt-transcribe')
            store.db.execute('DELETE FROM cloud_chunks WHERE meeting=? AND position=?',(mid,0));store.db.commit()
            with patch.dict(os.environ,{'MEETING_OS_PROGRESS_PATH':str(progress)}):
                transcribe_sources(store,mid,sources,client,consent=True,model='openai/gpt-transcribe')
            data=json.loads(progress.read_text())
            self.assertEqual(data['uploaded_seconds'],data['total_seconds'])
            self.assertLess(data['total_seconds'],180.0)   # the resumed baseline is not this run's work
            store.close()

    def test_a_full_disk_during_assembly_is_reported_and_retried_later(self):
        with tempfile.TemporaryDirectory() as tmp:
            d=capture_dir(tmp,seconds=4);store=Store(Path(tmp)/'db.sqlite')
            mid=store.create_meeting('Dolu disk',{'capture_dir':str(d)});store.status(mid,'incomplete')
            with patch('shutil.disk_usage',return_value=SimpleNamespace(free=1024)):
                with self.assertRaises(OSError): finalize_capture(store,mid,tmp,consent=True,model='openai/gpt-transcribe',client=EchoFreeClient())
            meta=json.loads(store.db.execute('SELECT metadata FROM meetings WHERE id=?',(mid,)).fetchone()[0])
            self.assertEqual(meta['cloud_error']['kind'],'disk_full')
            self.assertIn('Disk dolu',meta['cloud_error']['message'])
            self.assertEqual(meta['cloud_retry_attempt'],0)   # none of the thirty retries was spent
            self.assertIn('cloud_retry_after',meta)
            store.close()


class PlanOrderTests(unittest.TestCase):
    """P1-5: all mic pieces before all system pieces made the estimate lie by 8× on a speaker phone."""

    def test_sources_are_interleaved(self):
        with tempfile.TemporaryDirectory() as tmp:
            d=capture_dir(tmp,seconds=90);store=Store(Path(tmp)/'db.sqlite')
            mid=store.create_meeting('Sıra',{'capture_dir':str(d)})
            sources=assemble_capture(d)
            plan=transcribe_sources(store,mid,sources,EchoFreeClient(),consent=True,model='openai/gpt-transcribe')
            self.assertEqual([p[0] for p in plan],['mic','system']*3)
            self.assertEqual([p[3] for p in plan],[0,0,1,1,2,2])
            store.close()

    def test_progress_carries_uploaded_and_total_seconds(self):
        with tempfile.TemporaryDirectory() as tmp:
            d=capture_dir(tmp,seconds=60,sources=('system',));store=Store(Path(tmp)/'db.sqlite')
            mid=store.create_meeting('İlerleme',{'capture_dir':str(d)})
            sources=assemble_capture(d)
            progress=Path(tmp)/'progress.json'
            with patch.dict(os.environ,{'MEETING_OS_PROGRESS_PATH':str(progress)}):
                transcribe_sources(store,mid,sources,EchoFreeClient(),consent=True,model='openai/gpt-transcribe')
            data=json.loads(progress.read_text())
            self.assertEqual((data['stage'],data['current'],data['total']),('transcribing',2,2))   # pieces, as Swift still reads them
            self.assertEqual(data['total_seconds'],60.0)
            self.assertEqual(data['uploaded_seconds'],60.0)
            store.close()

    def test_skipped_windows_shrink_the_total_instead_of_racing_the_progress(self):
        with tempfile.TemporaryDirectory() as tmp:
            d=Path(tmp)/'rec';d.mkdir();store=Store(Path(tmp)/'db.sqlite')
            t=np.arange(16000*60)/16000
            sf.write(d/'system-000000.wav',(0.3*np.sin(2*np.pi*440*t)).astype('float32'),16000,subtype='FLOAT')
            silent=np.zeros(16000*60,dtype='float32');silent[:16000*30]=(0.3*np.sin(2*np.pi*300*t[:16000*30])).astype('float32')
            sf.write(d/'mic-000000.wav',silent,16000,subtype='FLOAT')   # second half of the mic is digital silence
            (d/'capture-native.jsonl').write_text('\n'.join(json.dumps({'event':'chunk','source':s,'start':0,'duration':60,
                'path':str(d/f'{s}-000000.wav'),'sample_rate':16000,'index':0}) for s in ('mic','system'))+'\n')
            mid=store.create_meeting('Sessiz',{'capture_dir':str(d)})
            sources=assemble_capture(d)
            progress=Path(tmp)/'progress.json'
            with patch.dict(os.environ,{'MEETING_OS_PROGRESS_PATH':str(progress)}):
                transcribe_sources(store,mid,sources,EchoFreeClient(),consent=True,model='openai/gpt-transcribe')
            data=json.loads(progress.read_text())
            self.assertLess(data['total_seconds'],120.0)      # the skipped mic window left the estimate
            self.assertEqual(data['uploaded_seconds'],data['total_seconds'])
            store.close()

    def test_a_reordered_plan_resumes_instead_of_refusing(self):
        """An app update changed the plan order; a meeting that was already paying must not have to start over."""
        with tempfile.TemporaryDirectory() as tmp:
            d=capture_dir(tmp,seconds=90);store=Store(Path(tmp)/'db.sqlite')
            mid=store.create_meeting('Devam',{'capture_dir':str(d)})
            sources=assemble_capture(d)
            client=EchoFreeClient()
            plan=transcribe_sources(store,mid,sources,client,consent=True,model='openai/gpt-transcribe')
            grouped=sorted(plan,key=lambda p:(p[0],p[3]))     # the old all-mic-then-all-system order
            position=grouped.index(plan[3])
            with store.db:
                store.db.execute('DELETE FROM cloud_chunks WHERE meeting=?',(mid,))
                store.db.execute('UPDATE cloud_sources SET plan=? WHERE meeting=?',(json.dumps(grouped),mid))
                store.db.execute('INSERT INTO cloud_chunks VALUES(?,?,?)',(mid,position,json.dumps({'seconds':30,'cost':0.001})))
            again=EchoFreeClient()
            transcribe_sources(store,mid,sources,again,consent=True,model='openai/gpt-transcribe')
            self.assertEqual(len(again.calls),5)              # the paid piece was kept, the other five were sent
            done={r[0] for r in store.db.execute('SELECT position FROM cloud_chunks WHERE meeting=?',(mid,))}
            self.assertEqual(done,set(range(6)))
            store.close()


class EncodeOverlapTests(unittest.TestCase):
    """P1-7: ffmpeg used to sit idle for the whole upload and the uploads for the whole encode."""

    def test_the_next_batch_is_encoded_while_this_one_uploads(self):
        with tempfile.TemporaryDirectory() as tmp:
            d=capture_dir(tmp,seconds=180);store=Store(Path(tmp)/'db.sqlite')
            mid=store.create_meeting('Örtüşme',{'capture_dir':str(d)})
            sources=assemble_capture(d)
            ahead=threading.Event();encoded=[];staged=[]
            real=__import__('meeting_os.cloud_finalize',fromlist=['encode_piece']).encode_piece
            def encode(path,a,b,ffmpeg=None):
                encoded.append((a,b))
                if len(encoded)>3: ahead.set()   # a piece past the first batch of three
                return real(path,a,b,ffmpeg)
            class SlowClient(EchoFreeClient):
                def transcribe(self,audio,fmt,**kw):
                    staged.append(ahead.wait(10))
                    return super().transcribe(audio,fmt,**kw)
            with patch('meeting_os.cloud_finalize.encode_piece',side_effect=encode):
                transcribe_sources(store,mid,sources,SlowClient(),consent=True,model='openai/gpt-transcribe')
            self.assertTrue(staged and staged[0],'no piece was encoded while the first batch was uploading')
            store.close()

    def test_encoded_pieces_live_on_disk_and_the_scratch_folder_is_removed(self):
        with tempfile.TemporaryDirectory() as tmp:
            d=capture_dir(tmp,seconds=60);store=Store(Path(tmp)/'db.sqlite')
            mid=store.create_meeting('Disk',{'capture_dir':str(d)})
            sources=assemble_capture(d)
            folders=[]
            class Watching(EchoFreeClient):
                def transcribe(self,audio,fmt,**kw):
                    folders.extend(sorted(Path(tempfile.gettempdir()).glob('meeting-os-pieces-*')))
                    return super().transcribe(audio,fmt,**kw)
            transcribe_sources(store,mid,sources,Watching(),consent=True,model='openai/gpt-transcribe')
            self.assertTrue(folders,'pieces were never staged on disk')
            for folder in folders: self.assertFalse(folder.exists(),f'{folder} survived the job')
            store.close()


class StaleTemporaryTests(unittest.TestCase):
    """P1-8: `*-full.flac.tmp` was recording-sized and nothing ever swept it."""

    def test_compaction_sweeps_an_hour_old_archive_temporary(self):
        with tempfile.TemporaryDirectory() as tmp:
            d=capture_dir(tmp,seconds=3);store=Store(Path(tmp)/'db.sqlite')
            sources=assemble_capture(d)
            mid=store.create_meeting('Artık',{'capture_dir':str(d),'cloud_mode':'capture','paths':sources})
            store.status(mid,'complete')
            old=d/'system-full.flac.tmp';old.write_bytes(b'x'*4096)
            os.utime(old,(time.time()-7200,time.time()-7200))
            fresh=d/'mic-full.flac.tmp';fresh.write_bytes(b'x'*4096)
            freed=compact_capture(store,mid)
            self.assertFalse(old.exists());self.assertTrue(fresh.exists())   # a fresh one may still be being written
            self.assertGreaterEqual(freed,4096)
            meta=json.loads(store.db.execute('SELECT metadata FROM meetings WHERE id=?',(mid,)).fetchone()[0])
            self.assertEqual(meta['stale_temporaries_removed'],1)
            store.close()

    def test_an_unfinished_meeting_still_gets_its_temporaries_swept(self):
        """The sweep sat below three early returns, and a meeting that never reached `complete` — exactly the
        one that leaves a recording-sized `.tmp` behind — never reached it."""
        with tempfile.TemporaryDirectory() as tmp:
            d=capture_dir(tmp,seconds=3);store=Store(Path(tmp)/'db.sqlite')
            mid=store.create_meeting('Yarım',{'capture_dir':str(d),'cloud_mode':'capture'})
            store.status(mid,'incomplete')
            old=d/'system-full.wav.tmp';old.write_bytes(b'x'*8192)
            os.utime(old,(time.time()-7200,time.time()-7200))
            freed=compact_capture(store,mid)
            self.assertFalse(old.exists());self.assertGreaterEqual(freed,8192)
            self.assertTrue((d/'mic-000000.wav').is_file())   # the chunks of an unfinished meeting are untouched
            meta=json.loads(store.db.execute('SELECT metadata FROM meetings WHERE id=?',(mid,)).fetchone()[0])
            self.assertEqual(meta['stale_temporaries_removed'],1)
            store.close()

    def test_a_failed_archive_removes_its_own_temporary(self):
        from meeting_os import audio_archive
        with tempfile.TemporaryDirectory() as tmp:
            src=Path(tmp)/'system-full.wav'
            sf.write(src,np.zeros(16000,dtype='float32'),16000,subtype='FLOAT')
            real=audio_archive.sf.SoundFile
            def explode(path,mode='r',**kw):
                if mode=='w':
                    Path(path).write_bytes(b'partial');raise RuntimeError('disk gitti')
                return real(path,mode,**kw)
            with patch.object(audio_archive.sf,'SoundFile',side_effect=explode):
                with self.assertRaises(RuntimeError): audio_archive.archive_file(src)
            self.assertEqual(list(Path(tmp).glob('*.tmp')),[])
            self.assertTrue(src.is_file())


if __name__=='__main__': unittest.main()
