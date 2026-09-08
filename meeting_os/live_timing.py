"""Bounded local phase timings, never meeting text or audio. One file per source."""
from contextlib import contextmanager
from pathlib import Path
import json,os,time
from .progress import stage_observer

@contextmanager
def observe_worker(data):
    started=last=time.monotonic(); stage='startup'; totals={}; failed=True
    def observe(next_stage):
        nonlocal last,stage
        now=time.monotonic()
        totals[stage]=totals.get(stage,0)+max(0,now-last)
        last=now
        stage=next_stage if next_stage in {'loading_models','reading_audio','vad','diarizing','transcribing','identifying'} else 'other'
    token=stage_observer.set(observe)
    try:
        yield
        failed=False
    finally:
        stage_observer.reset(token)
        observe('done')
        source=data.get('source')
        root=Path(data['path']).parent
        try:
            enabled=source in ('mic','system') and (root/'capture-native.jsonl').is_file()
        except OSError:
            enabled=False
        if enabled:
            target=root/f'live-{source}-timing.json'
            temp=target.with_name(target.name+f'.{os.getpid()}.tmp')
            row={'stages':totals,'elapsed_seconds':max(0,last-started),'source':source,
                 'offset':data.get('offset',0),'updated_at':time.time(),'failed':failed,
                 'cpp_threads':data.get('_cpp_threads',2),'batch_used':data.get('_batch_used',False),
                 'batch_clip_count':data.get('_batch_clip_count',0),'flash_attention':data.get('_flash_attention',True),'gpu_requested':data.get('_gpu_requested',False)}
            try:
                temp.write_text(json.dumps(row));temp.replace(target)
            except OSError:
                try:temp.unlink(missing_ok=True)
                except OSError:pass
