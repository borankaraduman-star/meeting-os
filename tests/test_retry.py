import tempfile,unittest
from pathlib import Path
from meeting_os.store import Store
from meeting_os.types import Segment

class RetryTests(unittest.TestCase):
    owner={'pid':123,'started_us':1,'boot':'a'}
    def setup_db(self,root):
        from meeting_os.retry import RetryStore
        db=Store(root/'db');mid=db.create_meeting('fictional',{'capture_dir':str(root)})
        db.status(mid,'incomplete');db.add_segment(mid,Segment(0,1,'old','mic',flags=['provisional']))
        retry=RetryStore(db,inspect=lambda pid:self.owner)
        return db,mid,retry
    def test_staging_keeps_old_and_commit_is_idempotent(self):
        with tempfile.TemporaryDirectory() as t:
            db,mid,retry=self.setup_db(Path(t));attempt=retry.begin(mid,self.owner)
            retry.stage(attempt,0,Segment(0,1,'new','mic'))
            self.assertEqual(db.segments(mid)[0]['text'],'old')
            self.assertTrue(retry.finish(attempt,1));self.assertFalse(retry.finish(attempt,1))
            self.assertEqual(len(db.meetings()),1);self.assertEqual(len(db.segments(mid)),1)
            self.assertEqual(db.segments(mid)[0]['text'],'new');db.close()
    def test_concurrent_and_unknown_owner_refused(self):
        with tempfile.TemporaryDirectory() as t:
            db,mid,retry=self.setup_db(Path(t));retry.begin(mid,self.owner)
            with self.assertRaises(ValueError):retry.begin(mid,self.owner)
            retry.inspect=lambda pid:None
            with self.assertRaises(ValueError):retry.begin(mid,self.owner)
            self.assertEqual(db.segments(mid)[0]['text'],'old');db.close()
    def test_dead_attempt_replaced_and_old_token_cannot_commit(self):
        with tempfile.TemporaryDirectory() as t:
            db,mid,retry=self.setup_db(Path(t));old=retry.begin(mid,self.owner)
            retry.stage(old,0,Segment(0,1,'stale','mic'))
            retry.inspect=lambda pid:{**self.owner,'started_us':2}
            new=retry.begin(mid,{**self.owner,'started_us':2})
            with self.assertRaises(ValueError):retry.finish(old,1)
            retry.stage(new,0,Segment(0,1,'fresh','mic'));retry.finish(new,1)
            self.assertEqual(db.segments(mid)[0]['text'],'fresh');db.close()
    def test_correction_during_attempt_blocks_replacement(self):
        with tempfile.TemporaryDirectory() as t:
            db,mid,retry=self.setup_db(Path(t));attempt=retry.begin(mid,self.owner)
            retry.stage(attempt,0,Segment(0,1,'new','mic'))
            db.correct_text(mid,db.segments(mid)[0]['id'],'keep my edit')
            with self.assertRaises(ValueError):retry.finish(attempt,1)
            self.assertEqual(db.segments(mid)[0]['text'],'keep my edit');db.close()
    def test_aborted_and_empty_attempt_preserve_rows(self):
        with tempfile.TemporaryDirectory() as t:
            db,mid,retry=self.setup_db(Path(t));attempt=retry.begin(mid,self.owner)
            with self.assertRaises(ValueError):retry.finish(attempt,1)
            self.assertTrue(retry.abort(attempt));self.assertFalse(retry.abort(attempt))
            self.assertEqual(db.segments(mid)[0]['text'],'old');self.assertEqual(db.meetings()[0]['status'],'incomplete');db.close()
    def test_insert_failure_rolls_back_deletion_and_can_finish_afterward(self):
        import sqlite3
        with tempfile.TemporaryDirectory() as t:
            db,mid,retry=self.setup_db(Path(t));attempt=retry.begin(mid,self.owner)
            retry.stage(attempt,0,Segment(0,1,'new','mic'))
            db.db.executescript("CREATE TRIGGER reject_retry BEFORE INSERT ON segments BEGIN SELECT RAISE(ABORT,'synthetic failure'); END;")
            with self.assertRaises(sqlite3.IntegrityError):retry.finish(attempt,1)
            self.assertEqual(db.segments(mid)[0]['text'],'old')
            self.assertEqual(db.meetings()[0]['status'],'processing')
            db.db.execute('DROP TRIGGER reject_retry');retry.finish(attempt,1)
            self.assertEqual(db.segments(mid)[0]['text'],'new');db.close()
    def test_gapped_stage_or_changed_source_cannot_commit(self):
        with tempfile.TemporaryDirectory() as t:
            db,mid,retry=self.setup_db(Path(t));attempt=retry.begin(mid,self.owner)
            retry.stage(attempt,1,Segment(0,1,'new','mic'))
            with self.assertRaises(ValueError):retry.finish(attempt,1)
            retry.stage(attempt,0,Segment(1,2,'first','mic'))
            with db.db:db.db.execute("UPDATE segments SET speaker_name='Changed' WHERE meeting=?",(mid,))
            with self.assertRaises(ValueError):retry.finish(attempt,2)
            self.assertEqual(db.segments(mid)[0]['text'],'old');db.close()
    def test_linked_analysis_and_final_segments_refuse_begin(self):
        with tempfile.TemporaryDirectory() as t:
            db,mid,retry=self.setup_db(Path(t))
            db.db.executescript('CREATE TABLE analyses(meeting TEXT);')
            with db.db:db.db.execute('INSERT INTO analyses VALUES(?)',(mid,))
            with self.assertRaises(ValueError):retry.begin(mid,self.owner)
            with db.db:db.db.execute('DELETE FROM analyses')
            db.add_segment(mid,Segment(1,2,'final','mic'))
            with self.assertRaises(ValueError):retry.begin(mid,self.owner)
            self.assertEqual(db.meetings()[0]['status'],'incomplete');db.close()
    def test_duplicate_stage_is_noop_but_conflicting_stage_refused(self):
        with tempfile.TemporaryDirectory() as t:
            db,mid,retry=self.setup_db(Path(t));attempt=retry.begin(mid,self.owner)
            segment=Segment(0,1,'new','mic');retry.stage(attempt,0,segment);retry.stage(attempt,0,segment)
            with self.assertRaises(ValueError):retry.stage(attempt,0,Segment(0,1,'different','mic'))
            retry.finish(attempt,1);self.assertEqual(len(db.segments(mid)),1);db.close()
    def test_process_exit_during_staging_and_commit_preserves_original(self):
        import subprocess,sys
        if sys.platform!='darwin':self.skipTest('Native process identity required')
        from meeting_os.retry import RetryStore
        from meeting_os.recovery import current_job_metadata
        for crash_at in ('staged','commit'):
            with self.subTest(crash_at=crash_at),tempfile.TemporaryDirectory() as t:
                root=Path(t);db,mid,retry=self.setup_db(root);db.close()
                code='''import os,sys
from meeting_os.store import Store
from meeting_os.retry import RetryStore
from meeting_os.recovery import current_job_metadata
from meeting_os.types import Segment
db=Store(sys.argv[1]);retry=RetryStore(db)
attempt=retry.begin(sys.argv[2],current_job_metadata()['worker_identity'])
retry.stage(attempt,0,Segment(0,1,'child staged','mic'))
if sys.argv[3]=='staged':os._exit(7)
db.db.create_function('crash_now',0,lambda:os._exit(7))
db.db.executescript('CREATE TRIGGER die_before_insert BEFORE INSERT ON segments BEGIN SELECT crash_now(); END;')
retry.finish(attempt,1)
'''
                result=subprocess.run([sys.executable,'-c',code,str(root/'db'),mid,crash_at],timeout=5,capture_output=True,text=True)
                self.assertEqual(result.returncode,7,result.stderr)
                db=Store(root/'db');self.assertEqual(db.segments(mid)[0]['text'],'old')
                db.db.execute('DROP TRIGGER IF EXISTS die_before_insert')
                retry=RetryStore(db);attempt=retry.begin(mid,current_job_metadata()['worker_identity'])
                retry.stage(attempt,0,Segment(0,1,'recovered','mic'));retry.finish(attempt,1)
                self.assertEqual(len(db.meetings()),1);self.assertEqual(len(db.segments(mid)),1)
                self.assertEqual(db.segments(mid)[0]['text'],'recovered');db.close()
    def test_staging_budget_refuses_growth_without_removing_old_result(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as t:
            db,mid,retry=self.setup_db(Path(t));attempt=retry.begin(mid,self.owner)
            retry.stage(attempt,0,Segment(0,1,'new','mic'))
            with patch('meeting_os.retry.MAX_STAGE_BYTES',1,create=True):
                with self.assertRaises(ValueError):retry.stage(attempt,1,Segment(1,2,'more','mic'))
            self.assertEqual(db.segments(mid)[0]['text'],'old');retry.finish(attempt,1);db.close()
    def test_two_connections_racing_for_same_meeting_have_one_winner(self):
        from concurrent.futures import ThreadPoolExecutor
        from threading import Barrier
        from meeting_os.retry import RetryStore
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);db,mid,retry=self.setup_db(root);db.close();barrier=Barrier(2)
            def claim():
                local=Store(root/'db');worker=RetryStore(local,inspect=lambda pid:self.owner)
                try:
                    barrier.wait(timeout=3)
                    try:return worker.begin(mid,self.owner)
                    except ValueError:return None
                finally:local.close()
            with ThreadPoolExecutor(max_workers=2) as pool:
                futures=[pool.submit(claim) for _ in range(2)]
                results=[f.result(timeout=6) for f in futures]
            self.assertEqual(sum(r is not None for r in results),1)
    def test_preexisting_segment_rename_is_protected(self):
        with tempfile.TemporaryDirectory() as t:
            db,mid,retry=self.setup_db(Path(t));sid=db.segments(mid)[0]['id']
            db.correct_segment(mid,sid,'Fictional renamed speaker')
            with self.assertRaisesRegex(ValueError,'corrections'):retry.begin(mid,self.owner)
            self.assertEqual(db.segments(mid)[0]['speaker_name'],'Fictional renamed speaker')
            self.assertEqual(db.meetings()[0]['status'],'incomplete');db.close()
