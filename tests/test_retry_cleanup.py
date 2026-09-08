import tempfile,unittest,os
from pathlib import Path
from meeting_os.store import Store
from meeting_os.retry import RetryStore

class RetryCleanupTests(unittest.TestCase):
    owner={'pid':123,'started_us':1,'boot':'a'}
    def setup_attempt(self,root):
        db=Store(root/'db');mid=db.create_meeting('fictional');db.status(mid,'incomplete')
        retry=RetryStore(db,inspect=lambda pid:self.owner);attempt=retry.begin(mid,self.owner)
        work=root/f'meeting-os-retry-{attempt}-abcdefgh';work.mkdir(mode=0o700);(work/'000000.wav').write_bytes(b'fictional copy')
        return db,retry,attempt,work
    def test_dead_registered_workspace_removed_without_touching_raw(self):
        from meeting_os.retry_workspaces import register_workspace,cleanup_workspaces
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);db,retry,attempt,work=self.setup_attempt(root);raw=root/'raw.wav';raw.write_bytes(b'KEEP')
            register_workspace(retry,attempt,work,root=root)
            result=cleanup_workspaces(retry,root=root,inspect=lambda pid:{**self.owner,'started_us':2})
            self.assertEqual(result['removed'],1);self.assertFalse(work.exists());self.assertEqual(raw.read_bytes(),b'KEEP')
            self.assertEqual(db.meetings()[0]['status'],'incomplete');db.close()
    def test_live_unknown_unregistered_and_foreign_files_preserved(self):
        from meeting_os.retry_workspaces import register_workspace,cleanup_workspaces
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);db,retry,attempt,work=self.setup_attempt(root);register_workspace(retry,attempt,work,root=root)
            for observed in (self.owner,None):
                result=cleanup_workspaces(retry,root=root,inspect=lambda pid:observed)
                self.assertEqual(result['removed'],0);self.assertTrue(work.exists())
            (work/'personal.txt').write_text('KEEP')
            result=cleanup_workspaces(retry,root=root,inspect=lambda pid:{**self.owner,'started_us':2})
            self.assertEqual(result['removed'],0);self.assertTrue((work/'000000.wav').exists())
            db.close()
    def test_replaced_directory_or_symlink_is_preserved(self):
        from meeting_os.retry_workspaces import register_workspace,cleanup_workspaces
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);db,retry,attempt,work=self.setup_attempt(root);register_workspace(retry,attempt,work,root=root)
            work.rename(root/'original');work.mkdir(mode=0o700);(work/'000000.wav').write_bytes(b'KEEP')
            result=cleanup_workspaces(retry,root=root,inspect=lambda pid:{**self.owner,'started_us':2})
            self.assertEqual(result['removed'],0);self.assertEqual((work/'000000.wav').read_bytes(),b'KEEP');db.close()
    def test_symlink_hardlink_and_unregistered_directory_are_preserved(self):
        from meeting_os.retry_workspaces import register_workspace,cleanup_workspaces
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);db,retry,attempt,work=self.setup_attempt(root);register_workspace(retry,attempt,work,root=root)
            raw=root/'raw.wav';raw.write_bytes(b'KEEP');link=work/'000001.wav';link.symlink_to(raw)
            unregistered=root/('meeting-os-retry-'+'a'*32+'-unregistered');unregistered.mkdir();(unregistered/'000000.wav').write_bytes(b'KEEP')
            dead=lambda pid:{**self.owner,'started_us':2}
            self.assertEqual(cleanup_workspaces(retry,root=root,inspect=dead)['removed'],0)
            self.assertTrue((work/'000000.wav').exists());link.unlink();os.link(raw,link)
            self.assertEqual(cleanup_workspaces(retry,root=root,inspect=dead)['removed'],0)
            self.assertEqual(raw.read_bytes(),b'KEEP');self.assertTrue(unregistered.exists());db.close()
    def test_missing_workspace_reconciles_attempt_without_deleting_other_files(self):
        from meeting_os.retry_workspaces import register_workspace,cleanup_workspaces
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);db,retry,attempt,work=self.setup_attempt(root);register_workspace(retry,attempt,work,root=root)
            (work/'000000.wav').unlink();work.rmdir()
            report=cleanup_workspaces(retry,root=root,inspect=lambda pid:{**self.owner,'started_us':2})
            self.assertEqual(report['already_missing'],1);self.assertEqual(db.meetings()[0]['status'],'incomplete')
            self.assertEqual(db.db.execute('SELECT COUNT(*) FROM retry_workspaces').fetchone()[0],0);db.close()
    def test_foreign_temp_root_refused(self):
        from meeting_os.retry_workspaces import register_workspace,cleanup_workspaces
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);db,retry,attempt,work=self.setup_attempt(root);register_workspace(retry,attempt,work,root=root)
            foreign=root/'other';foreign.mkdir()
            self.assertEqual(cleanup_workspaces(retry,root=foreign,inspect=lambda pid:{**self.owner,'started_us':2})['removed'],0)
            self.assertTrue(work.exists());db.close()
    def test_abrupt_worker_exit_leaves_only_registered_copies_eligible(self):
        import subprocess,sys
        if sys.platform!='darwin':self.skipTest('Native process identity')
        from meeting_os.retry_workspaces import cleanup_workspaces
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);db=Store(root/'db');mid=db.create_meeting('fictional');db.status(mid,'incomplete');db.close()
            code='''import sys,tempfile,os
from pathlib import Path
from meeting_os.store import Store
from meeting_os.retry import RetryStore
from meeting_os.retry_workspaces import register_workspace
from meeting_os.recovery import current_job_metadata
root=Path(sys.argv[1]);db=Store(root/'db');retry=RetryStore(db)
attempt=retry.begin(sys.argv[2],current_job_metadata()['worker_identity'])
work=Path(tempfile.mkdtemp(prefix='meeting-os-retry-'+attempt+'-',dir=root))
register_workspace(retry,attempt,work,root=root)
(work/'000000.wav').write_bytes(b'fictional copy')
os._exit(7)
'''
            result=subprocess.run([sys.executable,'-c',code,str(root),mid],timeout=5,capture_output=True,text=True)
            self.assertEqual(result.returncode,7,result.stderr)
            db=Store(root/'db');report=cleanup_workspaces(RetryStore(db),root=root)
            self.assertEqual(report['removed'],1);self.assertEqual(len(db.meetings()),1);self.assertEqual(db.meetings()[0]['status'],'incomplete');db.close()
    def test_cli_cleanup_uses_only_registered_temp_root_and_returns_counts(self):
        import contextlib,io,json
        from unittest.mock import patch
        from meeting_os.cli import main
        from meeting_os.retry_workspaces import register_workspace
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);db,retry,attempt,work=self.setup_attempt(root);register_workspace(retry,attempt,work,root=root);db.close()
            stream=io.StringIO()
            with patch('sys.argv',['meeting_os','--db',str(root/'db'),'cleanup-retries']),patch('meeting_os.retry_workspaces.tempfile.gettempdir',return_value=str(root)),patch('meeting_os.retry_workspaces.classify',return_value='interrupted'),contextlib.redirect_stdout(stream):main()
            result=json.loads(stream.getvalue());self.assertEqual(result['removed'],1)
            self.assertNotIn(str(root),stream.getvalue());self.assertNotIn(attempt,stream.getvalue())
    def test_filesystem_cleanup_does_not_block_another_retry_writer(self):
        from unittest.mock import patch
        from meeting_os.types import Segment
        from meeting_os.retry_workspaces import register_workspace,cleanup_workspaces,_remove
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);db,retry,attempt,work=self.setup_attempt(root);register_workspace(retry,attempt,work,root=root)
            other=Store(root/'db');other.db.execute('PRAGMA busy_timeout=0')
            mid=other.create_meeting('another fictional');other.status(mid,'incomplete')
            owner={'pid':456,'started_us':2,'boot':'a'};other_retry=RetryStore(other,inspect=lambda pid:owner);second=other_retry.begin(mid,owner)
            def remove(root_fd,row):
                other_retry.stage(second,0,Segment(0,1,'unrelated active job','mic'))
                return _remove(root_fd,row)
            with patch('meeting_os.retry_workspaces._remove',side_effect=remove):
                report=cleanup_workspaces(retry,root=root,inspect=lambda pid:{**self.owner,'started_us':2})
            self.assertEqual(report['removed'],1)
            self.assertEqual(other.db.execute('SELECT COUNT(*) FROM retry_segments WHERE attempt=?',(second,)).fetchone()[0],1)
            other.close();db.close()
    def test_new_attempt_during_cleanup_keeps_its_ownership(self):
        from unittest.mock import patch
        from meeting_os.retry_workspaces import register_workspace,cleanup_workspaces,_remove
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);db,retry,attempt,work=self.setup_attempt(root);mid=db.meetings()[0]['id'];register_workspace(retry,attempt,work,root=root)
            owner={**self.owner,'started_us':2};other=Store(root/'db');other_retry=RetryStore(other,inspect=lambda pid:owner);new=[]
            def remove(root_fd,row):
                _remove(root_fd,row);new.append(other_retry.begin(mid,owner))
            with patch('meeting_os.retry_workspaces._remove',side_effect=remove):
                report=cleanup_workspaces(retry,root=root,inspect=lambda pid:owner)
            self.assertEqual(report['removed'],1)
            self.assertEqual(other.db.execute('SELECT state FROM retry_attempts WHERE id=?',(new[0],)).fetchone()[0],'running')
            self.assertEqual(other.meetings()[0]['status'],'processing');other.close();db.close()
