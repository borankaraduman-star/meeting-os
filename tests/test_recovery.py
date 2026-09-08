import json, os, tempfile, unittest
from pathlib import Path
from unittest.mock import patch

class RecoveryTests(unittest.TestCase):
    identity={'pid':123,'started_us':1000001,'boot':'boot-a'}
    def test_identity_states_and_legacy_are_conservative(self):
        from meeting_os.recovery import classify
        for observed,expected in [(self.identity,'active'),({**self.identity,'started_us':1000002},'interrupted'),(None,'unknown')]:
            self.assertEqual(classify(self.identity,lambda pid:observed),expected)
        def gone(pid):raise ProcessLookupError
        self.assertEqual(classify(self.identity,gone),'interrupted')
        self.assertEqual(classify({'pid':123},gone),'unknown')
        def denied(pid):raise PermissionError
        self.assertEqual(classify(self.identity,denied),'unknown')
    def test_listing_never_mutates_and_recheck_protects_changed_identity(self):
        from meeting_os.store import Store
        from meeting_os.recovery import list_recovery,mark_interrupted
        with tempfile.TemporaryDirectory() as t:
            db=Store(Path(t)/'db')
            mid=db.create_meeting('fictional',{'worker_identity':self.identity})
            other={**self.identity,'started_us':2000000}
            self.assertEqual(list_recovery(db,lambda pid:other)[0]['recovery_state'],'interrupted')
            self.assertEqual(db.meetings()[0]['status'],'processing')
            self.assertFalse(mark_interrupted(db,mid,lambda pid:self.identity))
            self.assertTrue(mark_interrupted(db,mid,lambda pid:other))
            self.assertFalse(mark_interrupted(db,mid,lambda pid:other))
            self.assertEqual(db.meetings()[0]['status'],'incomplete');db.close()
    def test_legacy_corrupt_metadata_and_complete_rows_unchanged(self):
        from meeting_os.store import Store
        from meeting_os.recovery import list_recovery,mark_interrupted
        with tempfile.TemporaryDirectory() as t:
            db=Store(Path(t)/'db');mid=db.create_meeting('legacy',{'worker_pid':123})
            self.assertFalse(mark_interrupted(db,mid,lambda pid:None))
            with db.db:db.db.execute('UPDATE meetings SET metadata=? WHERE id=?',('[]',mid))
            self.assertEqual(list_recovery(db)[0]['recovery_state'],'unknown')
            db.status(mid,'complete');self.assertEqual(list_recovery(db),[]);db.close()
    def test_native_identity_current_process(self):
        import sys
        if sys.platform!='darwin':self.skipTest('Darwin native identity')
        from meeting_os.recovery import process_identity
        first=process_identity(os.getpid());second=process_identity(os.getpid())
        self.assertEqual(first,second);self.assertEqual(first['pid'],os.getpid())
        self.assertGreater(first['started_us'],0);self.assertTrue(first['boot'])
    def test_dead_native_child_is_interrupted(self):
        import subprocess,sys
        if sys.platform!='darwin':self.skipTest('Darwin native identity')
        from meeting_os.recovery import process_identity,classify
        child=subprocess.Popen([sys.executable,'-c','import time;time.sleep(10)'])
        try:
            identity=process_identity(child.pid)
            self.assertEqual(classify(identity),'active')
        finally:child.terminate();child.wait()
        self.assertEqual(classify(identity),'interrupted')
    def test_cli_listing_and_mark_use_only_temporary_database(self):
        import contextlib,io
        from meeting_os.cli import main
        from meeting_os.store import Store
        with tempfile.TemporaryDirectory() as t:
            path=Path(t)/'db';db=Store(path)
            mid=db.create_meeting('fictional',{'worker_pid':123});db.close()
            for extra in [[],['--mark-interrupted',mid]]:
                stream=io.StringIO()
                with patch('sys.argv',['meeting_os','--db',str(path),'recovery',*extra]),contextlib.redirect_stdout(stream):main()
                value=json.loads(stream.getvalue())
                if extra:self.assertFalse(value['marked_interrupted'])
                else:self.assertEqual(value[0]['recovery_state'],'unknown')
    def test_transition_holds_write_lock_while_rechecking(self):
        import sqlite3
        from meeting_os.store import Store
        from meeting_os.recovery import mark_interrupted
        with tempfile.TemporaryDirectory() as t:
            path=Path(t)/'db';db=Store(path)
            mid=db.create_meeting('fictional',{'worker_identity':self.identity})
            other=sqlite3.connect(path,timeout=0)
            def inspect(pid):
                with self.assertRaisesRegex(sqlite3.OperationalError,'locked'):
                    other.execute("UPDATE meetings SET metadata='{}' WHERE id=?",(mid,))
                other.rollback()
                return {**self.identity,'started_us':2000000}
            try:self.assertTrue(mark_interrupted(db,mid,inspect))
            finally:other.close();db.close()
    def test_inspection_exception_rolls_back(self):
        from meeting_os.store import Store
        from meeting_os.recovery import mark_interrupted
        with tempfile.TemporaryDirectory() as t:
            db=Store(Path(t)/'db');mid=db.create_meeting('fictional',{'worker_identity':self.identity})
            def interrupted(pid):raise KeyboardInterrupt
            with self.assertRaises(KeyboardInterrupt):mark_interrupted(db,mid,interrupted)
            self.assertFalse(db.db.in_transaction)
            self.assertEqual(db.meetings()[0]['status'],'processing');db.close()
    def test_native_permission_denial_returns_unknown(self):
        import errno
        from unittest.mock import Mock
        from meeting_os.recovery import process_identity
        lib=Mock();lib.proc_pidinfo.return_value=0
        with patch('meeting_os.recovery.sys.platform','darwin'),patch('meeting_os.recovery.boot_identity',return_value='boot-a'),patch('meeting_os.recovery.ctypes.CDLL',return_value=lib),patch('meeting_os.recovery.ctypes.get_errno',return_value=errno.EPERM):
            self.assertIsNone(process_identity(123))
