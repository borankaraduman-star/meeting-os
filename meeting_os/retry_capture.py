"""Retry against private source copies; commit only after complete processing."""
import hashlib,json,math,os,shutil,tempfile
from pathlib import Path
from .recovery import metadata
from .recovery_audio import inspect_capture,_regular_fd,MAX_JOURNAL_BYTES,MAX_LINE_BYTES,MAX_CHUNK_BYTES,MAX_CHUNKS

MAX_COPY_BYTES=2*1024**3
RESERVE_BYTES=1024**3

def _identity(fd):
    s=os.fstat(fd);return (s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns)

def _transfer(directory,name,limit,check,target=None):
    fd=_regular_fd(name,directory)
    try:
        before=_identity(fd)
        if before[2]>limit:raise ValueError('Retry source size limit')
        digest=hashlib.sha256();size=0
        while True:
            check();block=os.read(fd,64*1024)
            if not block:break
            size+=len(block)
            if size>limit:raise ValueError('Retry source size limit')
            digest.update(block)
            if target is not None:target.write(block)
        if before!=_identity(fd) or size!=before[2]:raise ValueError('Retry source changed while reading')
        return (before,digest.hexdigest())
    finally:os.close(fd)

def retry_capture(retry,mid,owner,process,cancel_requested=lambda:False):
    def check():
        if cancel_requested():raise RuntimeError('Retry canceled; original transcript preserved')
    check();attempt=retry.begin(mid,owner)
    root_fd=None
    try:
        source=metadata(retry.meeting(mid)).get('capture_dir')
        if not isinstance(source,str):raise ValueError('Retry requires captured audio')
        root=Path(source).resolve(strict=True)
        if inspect_capture(root)['status']!='available':raise ValueError('Capture is incomplete or unavailable; automatic retry refused')
        root_fd=os.open(root,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        root_identity=os.fstat(root_fd)
        try:
            fd=_regular_fd('capture-native.jsonl',root_fd);journal_name='capture-native.jsonl'
        except FileNotFoundError:
            fd=_regular_fd('events.jsonl',root_fd);journal_name='events.jsonl'
        with os.fdopen(fd,'rb') as journal:
            raw=journal.read(MAX_JOURNAL_BYTES+1)
        if len(raw)>MAX_JOURNAL_BYTES:raise ValueError('Retry journal limit')
        journal_hash=hashlib.sha256(raw).hexdigest()
        events=[];seen={}
        for line in raw.splitlines():
            check()
            if len(line)>MAX_LINE_BYTES:raise ValueError('Retry journal line limit')
            event=json.loads(line)
            if not isinstance(event,dict):raise ValueError('Invalid retry journal')
            if event.get('event')!='chunk':continue
            path=Path(event['path']);start=event.get('start');channel=event.get('source')
            if channel not in ('mic','system') or type(start) not in (int,float) or not math.isfinite(start) or not 0<=start<=14400:raise ValueError('Invalid retry timeline')
            if not path.is_absolute() or path.parent.resolve()!=root or path.suffix.lower()!='.wav':raise ValueError('Invalid retry chunk path')
            if path.name in seen:
                if seen[path.name]!=(channel,start):raise ValueError('Conflicting retry chunk')
                continue
            seen[path.name]=(channel,start);events.append({'event':'chunk','source':channel,'start':start,'name':path.name})
            if len(events)>MAX_CHUNKS:raise ValueError('Retry chunk limit')
        if not events:raise ValueError('No retry chunks')
        with tempfile.TemporaryDirectory(prefix=f'meeting-os-retry-{attempt}-') as temp:
            work=Path(temp);manifest={};copies={};used=0;copied_events=[]
            for index,event in enumerate(events):
                check();name=f'{index:06d}.wav';target=work/name
                size=os.stat(event['name'],dir_fd=root_fd,follow_symlinks=False).st_size
                if used+size>MAX_COPY_BYTES or shutil.disk_usage(work).free<size+RESERVE_BYTES:raise ValueError('Insufficient retry disk budget')
                with target.open('xb') as out:
                    limit=min(MAX_CHUNK_BYTES,MAX_COPY_BYTES-used,shutil.disk_usage(work).free-RESERVE_BYTES)
                    identity,digest=_transfer(root_fd,event['name'],limit,check,out)
                    out.flush();os.fsync(out.fileno())
                used+=identity[2];manifest[event['name']]=(identity,digest);copies[name]=digest
                copied_events.append({k:event[k] for k in ('event','source','start')}|{'path':str(target)})
            (work/'events.jsonl').write_text(''.join(json.dumps(e)+'\n' for e in copied_events))
            if inspect_capture(work)['status']!='available':raise ValueError('Retry snapshot unavailable')
            import soundfile as sf
            for event in copied_events:
                info=sf.info(event['path'])
                if event['start']+info.frames/info.samplerate>14400:raise ValueError('Retry timeline exceeds four hours')
            count=0
            for segment in process(work):
                check();retry.stage(attempt,count,segment);count+=1
            check()
            # Detect root replacement, preferred journal changes and content changes.
            current=root.stat()
            if (current.st_dev,current.st_ino)!=(root_identity.st_dev,root_identity.st_ino):raise ValueError('Retry capture directory changed')
            if journal_name=='events.jsonl':
                try:os.stat('capture-native.jsonl',dir_fd=root_fd,follow_symlinks=False)
                except FileNotFoundError:pass
                else:raise ValueError('Retry journal selection changed')
            if _transfer(root_fd,journal_name,MAX_JOURNAL_BYTES,check)[1]!=journal_hash:raise ValueError('Retry journal changed')
            for name,expected in manifest.items():
                if _transfer(root_fd,name,MAX_CHUNK_BYTES,check)!=expected:raise ValueError('Retry audio changed')
            copy_fd=os.open(work,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
            try:
                for name,expected in copies.items():
                    if _transfer(copy_fd,name,MAX_CHUNK_BYTES,check)[1]!=expected:raise ValueError('Retry snapshot changed')
            finally:os.close(copy_fd)
            source_digest=hashlib.sha256(json.dumps({'journal':journal_hash,'chunks':{k:v[1] for k,v in manifest.items()}},sort_keys=True).encode()).hexdigest()
            check();retry.finish(attempt,count,source_digest=source_digest)
            return {'meeting':mid,'segments':count,'status':'complete'}
    except BaseException:
        retry.abort(attempt);raise
    finally:
        if root_fd is not None:os.close(root_fd)
