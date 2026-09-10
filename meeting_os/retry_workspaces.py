"""Remove only registered dead-attempt copies, never scan/delete raw captures."""
import json,os,re,stat,tempfile
from pathlib import Path
from .recovery import classify,process_identity

def _root(root):return Path(root if root is not None else tempfile.gettempdir()).resolve(strict=True)
def _name(attempt,name):
    return isinstance(attempt,str) and re.fullmatch(r'[0-9a-f]{32}',attempt) is not None and isinstance(name,str) and re.fullmatch(r'meeting-os-retry-'+attempt+r'-[a-zA-Z0-9_-]{6,64}',name) is not None

def register_workspace(retry,attempt,workspace,root=None):
    root=_root(root);workspace=Path(workspace)
    if workspace.parent.resolve()!=root or not _name(attempt,workspace.name):raise ValueError('Unexpected retry workspace')
    fd=os.open(workspace,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:
        info=os.fstat(fd)
        if info.st_uid!=os.getuid() or stat.S_IMODE(info.st_mode)!=0o700:raise ValueError('Workspace is not private')
        with retry.transaction():
            retry.active(attempt)
            retry.db.execute('INSERT INTO retry_workspaces VALUES(?,?,?,?,?)',(attempt,str(root),workspace.name,info.st_dev,info.st_ino))
    finally:os.close(fd)

def _remove(root_fd,row):
    fd=os.open(row['name'],os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=root_fd)
    try:
        info=os.fstat(fd)
        if (info.st_dev,info.st_ino)!=(row['device'],row['inode']) or info.st_uid!=os.getuid() or stat.S_IMODE(info.st_mode)!=0o700:raise ValueError('Workspace identity changed')
        names=[]
        with os.scandir(fd) as scan:
            for entry in scan:
                if len(names)>=10003:raise ValueError('Workspace entry limit')
                names.append(entry.name)
        entries={}
        for name in names:
            if name not in ('events.jsonl','mic-full.wav','system-full.wav','mic-full.flac','system-full.flac','mic-full.wav.tmp','system-full.wav.tmp','mic-full.flac.tmp','system-full.flac.tmp') and not re.fullmatch(r'[0-9]{6}\.wav',name):raise ValueError('Unexpected workspace contents')
            entry=os.stat(name,dir_fd=fd,follow_symlinks=False)
            if not stat.S_ISREG(entry.st_mode) or entry.st_uid!=os.getuid() or entry.st_nlink!=1:raise ValueError('Unexpected workspace entry')
            entries[name]=(entry.st_dev,entry.st_ino)
        for name,expected in entries.items():
            current=os.stat(name,dir_fd=fd,follow_symlinks=False)
            if (current.st_dev,current.st_ino)!=expected:raise ValueError('Workspace entry changed')
            os.unlink(name,dir_fd=fd)
        current=os.stat(row['name'],dir_fd=root_fd,follow_symlinks=False)
        if (current.st_dev,current.st_ino)!=(info.st_dev,info.st_ino):raise ValueError('Workspace path changed')
        os.rmdir(row['name'],dir_fd=root_fd)
    finally:os.close(fd)

def cleanup_workspaces(retry,root=None,inspect=process_identity,meeting=None):
    if retry.db.in_transaction:raise ValueError('Cleanup requires an idle database connection')
    root=_root(root);report={'removed':0,'already_missing':0,'preserved':0,'state_deferred':0}
    root_fd=os.open(root,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    query='SELECT w.*,a.owner,a.meeting,a.state FROM retry_workspaces w JOIN retry_attempts a ON a.id=w.attempt WHERE w.attempt=?'
    def dead(row):
        try:owner=json.loads(row['owner'])
        except (TypeError,ValueError):owner=None
        return classify(owner,inspect)=='interrupted'
    try:
        ids=[r[0] for r in retry.db.execute('SELECT w.attempt FROM retry_workspaces w JOIN retry_attempts a ON a.id=w.attempt WHERE w.root=? AND (? IS NULL OR a.meeting=?) LIMIT 100',(str(root),meeting,meeting))]
        for attempt in ids:
            row=retry.db.execute(query,(attempt,)).fetchone()
            if row is None:continue
            if row['root']!=str(root) or not _name(attempt,row['name']) or not dead(row):
                report['preserved']+=1;continue
            # Attempt ownership/registration are immutable; a dead process cannot
            # resume. New retries use new tokens. Keep slow file I/O outside SQL.
            outcome='removed'
            try:_remove(root_fd,row)
            except FileNotFoundError:
                try:os.stat(row['name'],dir_fd=root_fd,follow_symlinks=False)
                except FileNotFoundError:outcome='already_missing'
                else:report['preserved']+=1;continue
            except (OSError,ValueError):report['preserved']+=1;continue
            report[outcome]+=1
            with retry.transaction():
                current=retry.db.execute(query,(attempt,)).fetchone()
                if current is None:continue
                keys=('attempt','root','name','device','inode','owner','meeting')
                if any(current[k]!=row[k] for k in keys) or not dead(current):
                    report['state_deferred']+=1;continue
                retry._abort_locked(attempt)
                retry.db.execute('DELETE FROM retry_workspaces WHERE attempt=?',(attempt,))
    finally:os.close(root_fd)
    return report
