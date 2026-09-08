"""Known missing provisional work, separate from durable audio/final transcript."""
import json,os
from pathlib import Path

def record_failure(directory,event):
    try:
        root=Path(directory).resolve();path=Path(event['path']).resolve()
        if path.parent!=root:return False
        with (root/'preview-failures.jsonl').open('a') as f:
            f.write(json.dumps({'chunk':str(path),'error':True})+'\n');f.flush();os.fsync(f.fileno())
        return True
    except (OSError,ValueError,TypeError,KeyError,RuntimeError):return False

def summarize(directory,legacy_log=None):
    root=Path(directory).resolve();paths=[root/'preview-failures.jsonl']
    if legacy_log is not None:paths.append(Path(legacy_log))
    failed=set();truncated=False
    for log in paths:
        try:
            with log.open('rb') as f:
                size=os.fstat(f.fileno()).st_size;offset=max(0,size-65536);truncated|=offset>0
                f.seek(offset)
                if offset:f.readline(65536)  # Discard incomplete first tail line.
                data=f.read(65536).decode(errors='replace')
        except OSError:continue
        for line in data.splitlines():
            try:
                event=json.loads(line)
                if not isinstance(event,dict) or not event.get('error') or not isinstance(event.get('chunk'),str):continue
                path=Path(event['chunk']).resolve()
                if path.parent==root:failed.add(path.name)
            except (ValueError,OSError,RuntimeError):continue
    # Absence of errors is NOT evidence that every speech segment was transcribed.
    return {'has_known_failures':bool(failed),'failed_chunks_at_least':len(failed),'log_tail_truncated':truncated}
