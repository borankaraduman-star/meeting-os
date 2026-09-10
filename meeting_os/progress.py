"""Local job progress; no transcript or audio content is written here."""
import json,os,time
from pathlib import Path
from contextvars import ContextVar

stage_observer = ContextVar("meeting_os_stage_observer", default=None)

def emit(stage,current=0,total=0,source='',**extra):
    observer=stage_observer.get()
    if observer is not None:
        try:observer(stage)
        except Exception:pass  # Optional diagnostics must not fail audio work.
    target=os.environ.get('MEETING_OS_PROGRESS_PATH')
    if not target:return
    path=Path(target); temp=path.with_name(path.name+'.tmp')
    event={'stage':stage,'current':current,'total':total,'source':source,'updated_at':time.time()}
    event.update(extra)   # optional weights (uploaded_seconds/total_seconds); older readers ignore what they do not know
    try:
        path.parent.mkdir(parents=True,exist_ok=True)
        temp.write_text(json.dumps(event));temp.replace(path)
    except OSError:
        # Progress display must never interrupt recording or inference.
        try:temp.unlink(missing_ok=True)
        except OSError:pass
