"""Recorder is independent of inference. Durable finalized-chunk metadata is queued."""
import json
import os
import queue
import signal
import subprocess
import threading
import time
from pathlib import Path
from .progress import emit

def record(binary, directory, seconds, chunk_seconds, pipeline=None, store=None, title='Meeting', pipeline_factory=None):
    directory=Path(directory).resolve()
    directory.mkdir(parents=True,exist_ok=True,mode=0o700)
    if (directory/'events.jsonl').exists(): raise ValueError('Use a new capture directory; existing recordings are never overwritten')
    pending=queue.Queue(); errors=[]; captured=[0]
    mid=store.create_meeting(title,{'capture_dir':str(directory),'provisional':True}) if store else None
    try:
        process=subprocess.Popen([str(Path(binary).resolve()),'--output',str(directory),'--seconds',str(seconds),'--chunk-seconds',str(chunk_seconds)],stdout=subprocess.PIPE,text=True,start_new_session=True)
    except Exception:
        if store: store.status(mid,'failed')
        raise
    started=time.monotonic()
    def reader():
        try:
            with (directory/'events.jsonl').open('a',buffering=1) as log:
                for line in process.stdout:
                    log.write(line); log.flush(); os.fsync(log.fileno())
                    try: event=json.loads(line)
                    except json.JSONDecodeError: continue
                    if event.get('event')=='chunk':
                        captured[0]+=1; pending.put(event)
                    if event.get('event')=='error': errors.append(event.get('message','Capture error'))
        except Exception as exc:
            errors.append('Capture log failure: '+str(exc))
            if process.poll() is None: process.send_signal(signal.SIGTERM)
        finally: pending.put(None)
    thread=threading.Thread(target=reader,daemon=True); thread.start()
    print(json.dumps({'meeting':mid,'capture_dir':str(directory),'status':'capturing'},ensure_ascii=False),flush=True)
    old_handler=signal.getsignal(signal.SIGINT); stopping=False
    def stop(sig,frame):
        nonlocal stopping
        if not stopping:
            stopping=True
            if process.poll() is None: process.send_signal(signal.SIGINT)
            emit("stopping_capture")
            print('Stopping capture; draining finalized chunks...',flush=True)
    signal.signal(signal.SIGINT,stop)
    try:
        # Capture and its durable journal start before expensive model warm-up.
        if pipeline_factory is not None: pipeline=pipeline_factory()
        while True:
            event=pending.get()
            if event is None: break
            if pipeline is None: print(json.dumps(event),flush=True); continue
            if stopping:
                # Completed chunks are already durable in the capture journal.
                # Finalize processes all audio, so do not redo a queued live pass.
                emit("stopping_capture")
                continue
            try:
                rows,_,_=pipeline.process(event['path'],event['source'],event['start'],True)
                for row in rows:
                    row.metrics['live_lag_seconds']=max(0,time.monotonic()-started-row.end)
                    store.add_segment(mid,row)
                    print(f'{row.start:8.2f} {row.speaker_name or row.speaker}: {row.text}',flush=True)
                print(json.dumps({'backlog_chunks':pending.qsize()}),flush=True)
            except Exception as exc:
                errors.append(str(exc))
                print(json.dumps({'error':str(exc),'chunk':event['path'],'recover':'finalize capture directory'}),flush=True)
        try: code=process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            process.kill(); code=process.wait(); errors.append('Capture did not exit')
        if stopping and captured[0]==0 and code in (0,-2,-15):
            if store: store.status(mid,'canceled')
            return mid
        if code: errors.append(f'Capture exited {code}')
        if store: store.status(mid,'incomplete' if errors else 'provisional')
        if errors: raise RuntimeError('; '.join(errors))
    except BaseException:
        if store: store.status(mid,'incomplete')
        raise
    finally:
        signal.signal(signal.SIGINT,old_handler)
        if process.poll() is None:
            process.send_signal(signal.SIGTERM)
            try: process.wait(timeout=15)
            except subprocess.TimeoutExpired: process.kill(); process.wait()
        thread.join(timeout=5); process.stdout.close()
    return mid
