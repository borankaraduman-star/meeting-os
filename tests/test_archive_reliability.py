"""Archive interruption and recording protection, using only private temporary audio."""
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
import soundfile as sf

from meeting_os import audio_archive as A, desktop as D, reports
from meeting_os.store import Store


class ArchiveReliabilityTests(unittest.TestCase):
    def meeting(self, store, data, name='recording', seconds=2):
        folder=data/'imports'/name
        folder.mkdir(parents=True)
        path=folder/'audio.wav'
        sf.write(path,np.full(16000*seconds,.05,dtype='float32'),16000,subtype='FLOAT')
        mid=store.create_meeting(name,{'cloud_mode':'file','paths':{'system':str(path)}})
        store.status(mid,'complete')
        return mid,path

    def test_metadata_failure_keeps_the_recording_playable_and_retryable(self):
        with tempfile.TemporaryDirectory() as tmp:
            data=Path(tmp);store=Store(data/'meeting-os.sqlite')
            self.addCleanup(store.close)
            mid,path=self.meeting(store,data)
            store.db.executescript("CREATE TRIGGER refuse_archive BEFORE UPDATE OF metadata ON meetings BEGIN SELECT RAISE(ABORT,'disk metadata unavailable'); END;")
            with self.assertRaises(sqlite3.IntegrityError): A.archive_meeting(store,mid)
            self.assertTrue(path.is_file(),'the stored playback path must survive a failed metadata commit')
            self.assertEqual(sf.info(path).frames,32000)
            store.db.execute('DROP TRIGGER refuse_archive')
            A.archive_meeting(store,mid)
            meta=json.loads(store.db.execute('SELECT metadata FROM meetings WHERE id=?',(mid,)).fetchone()[0])
            self.assertEqual(Path(meta['paths']['system']).suffix,'.flac')
            self.assertEqual(sf.info(meta['paths']['system']).frames,32000)
            self.assertFalse(path.exists())

    def test_an_old_interrupted_archive_repairs_its_missing_wav_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            data=Path(tmp);store=Store(data/'meeting-os.sqlite')
            self.addCleanup(store.close)
            mid,path=self.meeting(store,data)
            flac,_=A.archive_file(path)  # old crash window: WAV is gone, DB still points at it
            A.archive_meeting(store,mid)
            meta=json.loads(store.db.execute('SELECT metadata FROM meetings WHERE id=?',(mid,)).fetchone()[0])
            self.assertEqual(meta['paths']['system'],str(flac))
            self.assertEqual(sf.info(meta['paths']['system']).frames,32000)

    def test_source_cleanup_retries_without_reencoding_the_completed_archive(self):
        with tempfile.TemporaryDirectory() as tmp:
            data=Path(tmp);store=Store(data/'meeting-os.sqlite')
            self.addCleanup(store.close)
            mid,path=self.meeting(store,data)
            real=Path.unlink
            def unavailable(target,*args,**kwargs):
                if target==path: raise PermissionError('temporarily unavailable')
                return real(target,*args,**kwargs)
            with patch.object(Path,'unlink',unavailable): A.archive_meeting(store,mid)
            meta=json.loads(store.db.execute('SELECT metadata FROM meetings WHERE id=?',(mid,)).fetchone()[0])
            self.assertEqual(meta['archive_pending_wavs'],[str(path)])
            self.assertTrue(Path(meta['paths']['system']).is_file())
            with patch.object(A,'archive_file') as encode: A.archive_meeting(store,mid)
            encode.assert_not_called()
            self.assertFalse(path.exists())
            meta=json.loads(store.db.execute('SELECT metadata FROM meetings WHERE id=?',(mid,)).fetchone()[0])
            self.assertNotIn('archive_pending_wavs',meta)

    def test_pending_cleanup_never_deletes_the_only_complete_recording(self):
        for damage in ('missing','corrupt','shorter','truncated','wrong_rate','wrong_channels'):
            with self.subTest(damage=damage), tempfile.TemporaryDirectory() as tmp:
                data=Path(tmp);store=Store(data/'meeting-os.sqlite')
                try:
                    mid,path=self.meeting(store,data)
                    original=path.read_bytes();real=Path.unlink
                    def unavailable(target,*args,**kwargs):
                        if target==path: raise PermissionError('temporarily unavailable')
                        return real(target,*args,**kwargs)
                    with patch.object(Path,'unlink',unavailable): A.archive_meeting(store,mid)
                    flac=path.with_suffix('.flac')
                    if damage=='missing': flac.unlink()
                    elif damage=='corrupt': flac.write_bytes(b'broken archive')
                    elif damage=='truncated': flac.write_bytes(flac.read_bytes()[:100])
                    else:
                        frames=16000 if damage=='shorter' else 32000
                        audio=np.full((frames,2) if damage=='wrong_channels' else frames,.05,dtype='float32')
                        sf.write(flac,audio,8000 if damage=='wrong_rate' else 16000,format='FLAC')
                    A.archive_meeting(store,mid)
                    self.assertTrue(path.is_file(),'pending cleanup must retain the sole complete audio source')
                    self.assertEqual(path.read_bytes(),original)
                    meta=json.loads(store.db.execute('SELECT metadata FROM meetings WHERE id=?',(mid,)).fetchone()[0])
                    self.assertEqual(meta['paths']['system'],str(path),'restore playback to the surviving WAV')
                    A.archive_meeting(store,mid)
                    meta=json.loads(store.db.execute('SELECT metadata FROM meetings WHERE id=?',(mid,)).fetchone()[0])
                    self.assertEqual(sf.info(meta['paths']['system']).frames,32000)
                    self.assertFalse(path.exists())
                finally: store.close()

    def test_a_damaged_legacy_flac_is_not_adopted(self):
        with tempfile.TemporaryDirectory() as tmp:
            data=Path(tmp);store=Store(data/'meeting-os.sqlite')
            self.addCleanup(store.close)
            mid,path=self.meeting(store,data)
            path.unlink();path.with_suffix('.flac').write_bytes(b'incomplete archive')
            A.archive_meeting(store,mid)
            meta=json.loads(store.db.execute('SELECT metadata FROM meetings WHERE id=?',(mid,)).fetchone()[0])
            self.assertEqual(meta['paths']['system'],str(path))

    def test_a_path_change_during_cleanup_verification_preserves_the_wav(self):
        with tempfile.TemporaryDirectory() as tmp:
            data=Path(tmp);store=Store(data/'meeting-os.sqlite')
            self.addCleanup(store.close)
            mid,path=self.meeting(store,data)
            real=A._verified_archive
            def switch_playback(*args,**kwargs):
                result=real(*args,**kwargs)
                meta=json.loads(store.db.execute('SELECT metadata FROM meetings WHERE id=?',(mid,)).fetchone()[0])
                meta['paths']['system']=str(path)
                with store.db: store.db.execute('UPDATE meetings SET metadata=? WHERE id=?',(json.dumps(meta),mid))
                return result
            with patch.object(A,'_verified_archive',side_effect=switch_playback):
                with self.assertRaisesRegex(ValueError,'ses yolu'): A.archive_meeting(store,mid)
            self.assertTrue(path.exists())

    def test_path_validation_and_source_deletion_hold_one_database_lock(self):
        with tempfile.TemporaryDirectory() as tmp:
            data=Path(tmp);store=Store(data/'meeting-os.sqlite')
            self.addCleanup(store.close)
            mid,path=self.meeting(store,data)
            other=sqlite3.connect(store.path);other.execute('PRAGMA busy_timeout=0')
            self.addCleanup(other.close)
            real=Path.unlink;checked=[]
            def concurrent_edit(target,*args,**kwargs):
                if target==path:
                    with self.assertRaisesRegex(sqlite3.OperationalError,'locked'):
                        with other: other.execute('UPDATE meetings SET metadata=metadata WHERE id=?',(mid,))
                    checked.append(True)
                return real(target,*args,**kwargs)
            with patch.object(Path,'unlink',concurrent_edit): A.archive_meeting(store,mid)
            self.assertEqual(checked,[True])

    def test_metadata_edits_during_encoding_survive_the_archive_commit(self):
        with tempfile.TemporaryDirectory() as tmp:
            data=Path(tmp);store=Store(data/'meeting-os.sqlite')
            self.addCleanup(store.close)
            mid,path=self.meeting(store,data)
            real=A.archive_file
            def keep_recording(*args,**kwargs):
                result=real(*args,**kwargs)
                meta=json.loads(store.db.execute('SELECT metadata FROM meetings WHERE id=?',(mid,)).fetchone()[0])
                meta['keep']=True
                with store.db: store.db.execute('UPDATE meetings SET metadata=? WHERE id=?',(json.dumps(meta),mid))
                return result
            with patch.object(A,'archive_file',side_effect=keep_recording): A.archive_meeting(store,mid)
            meta=json.loads(store.db.execute('SELECT metadata FROM meetings WHERE id=?',(mid,)).fetchone()[0])
            self.assertTrue(meta.get('keep'),'a Keep Audio choice made during encoding must not be overwritten')
            self.assertTrue(Path(meta['paths']['system']).is_file())

    def test_a_recording_start_during_archive_stops_before_the_next_meeting(self):
        with tempfile.TemporaryDirectory() as tmp:
            data=Path(tmp);db=data/'meeting-os.sqlite';store=Store(db)
            self.meeting(store,data,'one');self.meeting(store,data,'two');store.close()
            reports.save_settings(data,{'share_reports':False,'audio_retention_days':0})
            archived=[];real=A.archive_meeting
            def starts_recording(store,mid,*args,**kwargs):
                result=real(store,mid,*args,**kwargs)
                archived.append(mid)
                reports.write_recording_heartbeat(data,{'meeting':'live','elapsed_seconds':1})
                return result
            with patch.object(A,'archive_meeting',side_effect=starts_recording), patch('meeting_os.team_knowledge.sync') as sync:
                result=D.dispatch({'action':'storage_housekeeping'},db)
            self.assertEqual(len(archived),1,'the remaining library must wait while the new recording runs')
            self.assertEqual(result,{'skipped':'recording','failures':{}})
            sync.assert_not_called()

    def test_a_recording_start_inside_one_large_file_preserves_the_wav(self):
        with tempfile.TemporaryDirectory() as tmp:
            data=Path(tmp);db=data/'meeting-os.sqlite';store=Store(db)
            _,path=self.meeting(store,data,seconds=65);store.close()
            reports.save_settings(data,{'share_reports':False,'audio_retention_days':0})
            real=sf.SoundFile.write;written=[]
            def starts_recording(out,block):
                result=real(out,block);written.append(len(block))
                reports.write_recording_heartbeat(data,{'meeting':'live','elapsed_seconds':1})
                return result
            with patch.object(sf.SoundFile,'write',starts_recording):
                result=D.dispatch({'action':'storage_housekeeping'},db)
            self.assertEqual(result,{'skipped':'recording','failures':{}})
            self.assertEqual(written,[A.BLOCK],'encoding must yield after the current bounded block')
            self.assertTrue(path.exists())
            self.assertFalse(path.with_suffix('.flac.tmp').exists())


class PrivateRecordingHeartbeatTests(unittest.TestCase):
    def test_sharing_off_still_protects_recording_without_touching_the_shared_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            data=Path(tmp);reports.save_settings(data,{'share_reports':False,'report_dir':str(data/'shared')})
            reports.write_recording_heartbeat(data,{'meeting':'live','elapsed_seconds':1})
            self.assertTrue(D.recording_now(data))
            private=data/reports.RECORDING_HEARTBEAT_FILE
            self.assertTrue(private.is_file())
            self.assertEqual(private.stat().st_mode & 0o777,0o600)
            self.assertFalse((data/'shared').exists())
            reports.clear_recording_heartbeat(data)
            self.assertFalse(D.recording_now(data))

    def test_unreachable_report_settings_cannot_hide_the_local_recording(self):
        with tempfile.TemporaryDirectory() as tmp:
            data=Path(tmp)
            with patch.object(reports,'load_settings',side_effect=OSError('report settings unavailable')):
                reports.write_recording_heartbeat(data,{'meeting':'live','elapsed_seconds':1})
                self.assertTrue(D.recording_now(data))
                reports.clear_recording_heartbeat(data)
                self.assertFalse(D.recording_now(data))

    def test_shared_folder_failure_does_not_prevent_the_private_heartbeat(self):
        with tempfile.TemporaryDirectory() as tmp:
            data=Path(tmp);reports.save_settings(data,{'share_reports':True})
            with patch.object(reports,'prepare_folder',side_effect=OSError('share offline')):
                reports.write_recording_heartbeat(data,{'meeting':'live','elapsed_seconds':1})
            self.assertTrue(D.recording_now(data))


if __name__=='__main__': unittest.main()
