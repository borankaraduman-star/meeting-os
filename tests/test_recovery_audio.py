import json,tempfile,unittest,wave
from pathlib import Path

class RecoveryAudioTests(unittest.TestCase):
    def chunk(self,root,name='system-0.wav'):
        path=root/name
        with wave.open(str(path),'wb') as out:
            out.setnchannels(1);out.setsampwidth(2);out.setframerate(16000);out.writeframes(b'\0\0'*160)
        return {'event':'chunk','source':'system','path':str(path),'start':0,'duration':.01}
    def test_available_deduplicated_and_no_mutation(self):
        from meeting_os.recovery_audio import inspect_capture
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);event=self.chunk(root);journal=root/'capture-native.jsonl'
            journal.write_text(json.dumps(event)+'\n'+json.dumps(event)+'\n');before={p.name:p.read_bytes() for p in root.iterdir()}
            result=inspect_capture(root)
            self.assertEqual(result['available_chunks'],1);self.assertEqual(result['status'],'available')
            self.assertEqual(before,{p.name:p.read_bytes() for p in root.iterdir()});self.assertNotIn(str(root),json.dumps(result))
    def test_missing_and_truncated_journal_are_partial(self):
        from meeting_os.recovery_audio import inspect_capture
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);event=self.chunk(root);missing={**event,'path':str(root/'gone.wav'),'start':1}
            (root/'events.jsonl').write_text(json.dumps(event)+'\n'+json.dumps(missing)+'\n{"event":')
            result=inspect_capture(root)
            self.assertEqual(result['status'],'partial');self.assertEqual(result['missing_chunks'],1)
            self.assertIn('journal_malformed',result['issues'])
    def test_external_symlink_non_audio_and_oversized_lines_rejected(self):
        from meeting_os.recovery_audio import inspect_capture
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);event=self.chunk(root);(root/'link.wav').symlink_to(root/'system-0.wav')
            (root/'bad.wav').write_text('not audio')
            events=[{**event,'path':str(root/'link.wav')},{**event,'path':str(root/'bad.wav')},{**event,'path':'/tmp/external.wav'}]
            (root/'events.jsonl').write_text('\n'.join(map(json.dumps,events))+'\n'+'x'*17000+'\n')
            result=inspect_capture(root)
            self.assertEqual(result['available_chunks'],0);self.assertIn('journal_limit',result['issues'])
    def test_symlink_journal_is_not_followed(self):
        from meeting_os.recovery_audio import inspect_capture
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);(root/'events.jsonl').symlink_to('/dev/zero')
            self.assertEqual(inspect_capture(root)['status'],'unknown')
    def test_listing_skips_live_and_unknown_owners(self):
        from meeting_os.store import Store
        from meeting_os.recovery import list_recovery
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);db=Store(root/'db')
            identity={'pid':123,'started_us':1,'boot':'boot'}
            db.create_meeting('fictional',{'capture_dir':str(root),'worker_identity':identity})
            db.create_meeting('legacy',{'capture_dir':str(root)})
            with patch('meeting_os.recovery_audio.inspect_capture') as inspect:
                values=list_recovery(db,lambda pid:identity,include_audio=True)
                inspect.assert_not_called()
                self.assertTrue(all(r['audio']['status']=='not_checked_owner_uncertain' for r in values))
            db.close()
    def test_incomplete_listing_reports_audio_without_state_change(self):
        from meeting_os.store import Store
        from meeting_os.recovery import list_recovery
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);event=self.chunk(root);(root/'events.jsonl').write_text(json.dumps(event)+'\n')
            db=Store(root/'db');mid=db.create_meeting('fictional',{'capture_dir':str(root)});db.status(mid,'incomplete')
            self.assertEqual(list_recovery(db),[])
            self.assertEqual(list_recovery(db,include_audio=True)[0]['audio']['status'],'available')
            self.assertEqual(db.meetings()[0]['status'],'incomplete');db.close()
    def test_fifo_chunk_does_not_block(self):
        import os
        from meeting_os.recovery_audio import inspect_capture
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);os.mkfifo(root/'pipe.wav')
            (root/'events.jsonl').write_text(json.dumps({'event':'chunk','source':'mic','path':str(root/'pipe.wav'),'start':0})+'\n')
            self.assertEqual(inspect_capture(root)['invalid_chunks'],1)
    def test_oversized_chunk_rejected_before_native_header_parser(self):
        from meeting_os.recovery_audio import inspect_capture
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);event=self.chunk(root)
            with (root/'system-0.wav').open('r+b') as f:f.truncate(64*1024*1024+1)
            (root/'events.jsonl').write_text(json.dumps(event)+'\n')
            with patch('soundfile.SoundFile') as parser:
                result=inspect_capture(root);parser.assert_not_called()
            self.assertEqual(result['invalid_chunks'],1)
    def test_journal_byte_budget_returns_unknown_without_audio_scan(self):
        from meeting_os.recovery_audio import inspect_capture
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);event=self.chunk(root)
            (root/'events.jsonl').write_text(json.dumps(event)+'\n')
            with patch('meeting_os.recovery_audio.MAX_JOURNAL_BYTES',20),patch('soundfile.SoundFile') as parser:
                result=inspect_capture(root);parser.assert_not_called()
            self.assertEqual(result['status'],'unknown');self.assertIn('journal_limit',result['issues'])
    def test_truncated_wav_payload_is_not_available(self):
        from meeting_os.recovery_audio import inspect_capture
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);event=self.chunk(root);audio=root/'system-0.wav'
            audio.write_bytes(audio.read_bytes()[:-10])
            (root/'events.jsonl').write_text(json.dumps(event)+'\n')
            result=inspect_capture(root)
            self.assertEqual(result['available_chunks'],0);self.assertEqual(result['invalid_chunks'],1)
