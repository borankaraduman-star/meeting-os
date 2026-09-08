"""Bounded read-only inspection of finalized capture headers, not audio quality."""
import json
import math
import os
import stat
from pathlib import Path

MAX_JOURNAL_BYTES=8*1024*1024
MAX_LINE_BYTES=16384
MAX_CHUNKS=10000
MAX_CHUNK_BYTES=64*1024*1024

def _regular_fd(name,directory):
    fd=os.open(name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=directory)
    if not stat.S_ISREG(os.fstat(fd).st_mode):
        os.close(fd);raise ValueError('not_regular')
    return fd

def _wav_bounds(fd):
    """Check RIFF chunk extents with tiny positional reads, never decode PCM."""
    size=os.fstat(fd).st_size
    header=os.pread(fd,12,0)
    if len(header)!=12 or header[:4]!=b'RIFF' or header[8:]!=b'WAVE':raise ValueError('unsupported_container')
    end=int.from_bytes(header[4:8],'little')+8
    if not 12<=end<=size:raise ValueError('truncated_container')
    offset=12;found_data=False
    for _ in range(1024):
        if offset==end:
            if not found_data:raise ValueError('no_data')
            return
        chunk=os.pread(fd,8,offset)
        if len(chunk)!=8 or offset+8>end:raise ValueError('truncated_header')
        length=int.from_bytes(chunk[4:],'little')
        offset+=8+length+(length%2)
        if offset>end:raise ValueError('truncated_chunk')
        if chunk[:4]==b'data' and length>0:found_data=True
    raise ValueError('container_limit')

def inspect_capture(directory):
    report={'status':'unknown','available_chunks':0,'missing_chunks':0,'invalid_chunks':0,
            'sources':{'mic':0,'system':0},'issues':[],'validation':'header_only'}
    issues=set();root_fd=None
    try:
        root=Path(directory).resolve(strict=True)
        root_fd=os.open(root,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        try:journal_fd=_regular_fd('capture-native.jsonl',root_fd)
        except FileNotFoundError:journal_fd=_regular_fd('events.jsonl',root_fd)
        seen={};total=0
        with os.fdopen(journal_fd,'rb') as journal:
            while True:
                if total>=MAX_JOURNAL_BYTES:
                    issues.add('journal_limit');break
                line=journal.readline(min(MAX_LINE_BYTES+1,MAX_JOURNAL_BYTES-total))
                if not line:break
                total+=len(line)
                if len(line)>MAX_LINE_BYTES or total>MAX_JOURNAL_BYTES:
                    issues.add('journal_limit');break
                try:event=json.loads(line)
                except (ValueError,UnicodeError):issues.add('journal_malformed');continue
                if not isinstance(event,dict):issues.add('journal_malformed');continue
                if event.get('event')!='chunk':continue
                if len(seen)>=MAX_CHUNKS:issues.add('journal_limit');break
                try:
                    source=event.get('source');start=event.get('start');raw=event.get('path')
                    if source not in ('mic','system') or type(start) not in (int,float) or not math.isfinite(start) or start<0 or not isinstance(raw,str):raise ValueError
                    path=Path(raw)
                    if not path.is_absolute() or path.parent.resolve()!=root or path.suffix.lower()!='.wav':raise ValueError
                    identity=(source,start)
                    if path.name in seen:
                        if seen[path.name]!=identity:issues.add('chunk_conflict')
                        continue
                    seen[path.name]=identity
                except (ValueError,OSError,RuntimeError):
                    report['invalid_chunks']+=1;issues.add('chunk_metadata_invalid');continue
                fd=None
                try:
                    fd=_regular_fd(path.name,root_fd)
                    if os.fstat(fd).st_size>MAX_CHUNK_BYTES:raise ValueError('chunk_limit')
                    _wav_bounds(fd)
                    import soundfile as sf
                    with sf.SoundFile(fd,mode='r',closefd=False) as audio:
                        if audio.frames<=0 or audio.samplerate<=0 or not 1<=audio.channels<=2:raise ValueError
                    report['available_chunks']+=1;report['sources'][source]+=1
                except FileNotFoundError:
                    report['missing_chunks']+=1;issues.add('chunk_missing')
                except (OSError,ValueError,TypeError,RuntimeError):
                    report['invalid_chunks']+=1;issues.add('chunk_unreadable')
                finally:
                    if fd is not None:os.close(fd)
        report['status']='partial' if report['available_chunks'] and issues else 'available' if report['available_chunks'] else 'unknown' if 'journal_limit' in issues else 'unavailable'
    except (OSError,ValueError,TypeError,RuntimeError):issues.add('journal_unavailable')
    finally:
        if root_fd is not None:os.close(root_fd)
    report['issues']=sorted(issues)
    return report
