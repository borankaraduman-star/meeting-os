"""Recorder is independent of inference. Durable finalized-chunk metadata is queued."""
import json
import os
import queue
import signal
import subprocess
import tempfile
import threading
import time
from pathlib import Path
from .progress import emit
from .supervisor import open_lifeline,close_lifeline

CAPTURE_STOP_GRACE_SECONDS = 15.0

def record(binary, directory, seconds, chunk_seconds, pipeline=None, store=None, title='Meeting', pipeline_factory=None, result_path=None):
    directory=Path(directory).resolve()
    directory.mkdir(parents=True,exist_ok=True,mode=0o700)
    if (directory/'events.jsonl').exists(): raise ValueError('Use a new capture directory; existing recordings are never overwritten')
    pending=queue.Queue(); errors=[]; captured=[0]
    capture_failed=threading.Event()
    from .recovery import current_job_metadata
    mid=store.create_meeting(title,{**current_job_metadata(),'capture_dir':str(directory),'provisional':True}) if store else None
    def completed(status):
        if result_path is not None:
            target=Path(result_path);temp=None
            try:
                with tempfile.NamedTemporaryFile(mode='w',dir=target.parent,prefix='.meeting-os-record-',delete=False) as out:
                    temp=Path(out.name)
                    json.dump({'meeting':mid,'capture_dir':str(directory),'status':status,'finalized_chunks':captured[0]},out)
                    out.flush();os.fsync(out.fileno())
                temp.replace(target)
            finally:
                if temp is not None:temp.unlink(missing_ok=True)
        return mid
    try:
        process=subprocess.Popen([str(Path(binary).resolve()),'--output',str(directory),'--seconds',str(seconds),'--chunk-seconds',str(chunk_seconds)],stdout=subprocess.PIPE,text=True,start_new_session=True)
    except Exception:
        if store: store.status(mid,'failed')
        raise
    guardian,lifeline=open_lifeline(process)
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
                    if event.get('event')=='error':
                        errors.append(event.get('message','Capture error'))
                        capture_failed.set()
        except Exception as exc:
            errors.append('Capture log failure: '+str(exc))
            if process.poll() is None: process.send_signal(signal.SIGTERM)
        finally: pending.put(None)
    thread=threading.Thread(target=reader,daemon=True); thread.start()
    print(json.dumps({'meeting':mid,'capture_dir':str(directory),'status':'capturing'},ensure_ascii=False),flush=True)
    old_handler=signal.getsignal(signal.SIGINT); stopping=False; stop_deadline=None
    def stop(sig,frame):
        nonlocal stopping, stop_deadline
        if not stopping:
            stopping=True
            stop_deadline=time.monotonic()+CAPTURE_STOP_GRACE_SECONDS
            if process.poll() is None: process.send_signal(signal.SIGINT)
            emit("stopping_capture")
            print('Stopping capture; draining finalized chunks...',flush=True)
    signal.signal(signal.SIGINT,stop)
    try:
        # Capture and its durable journal start before expensive model warm-up.
        if pipeline_factory is not None: pipeline=pipeline_factory()
        if hasattr(pipeline,"cancel_requested"):pipeline.cancel_requested=lambda:stopping
        while True:
            # A failed helper can leave stdout open. Give it the same bounded
            # shutdown and finalized-chunk drain as an explicit user stop.
            if capture_failed.is_set() and not stopping:stop(None,None)
            # The reader may never reach EOF if the native helper hangs.
            # Check the deadline before waiting, including when chunks are queued.
            if stop_deadline is not None and time.monotonic() >= stop_deadline:
                if process.poll() is None:
                    process.kill()
                    errors.append('Capture did not exit after stop; recover finalized audio with finalize')
                break
            try: event=pending.get(timeout=.1)
            except queue.Empty: continue
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
                if stopping:continue
                errors.append(str(exc))
                print(json.dumps({'error':str(exc),'chunk':event['path'],'recover':'finalize capture directory'}),flush=True)
        try: code=process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            process.kill(); code=process.wait(); errors.append('Capture did not exit')
        if stopping and not errors and captured[0]==0 and code in (0,-2,-15):
            if store: store.status(mid,'canceled')
            return completed('canceled')
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
        close_lifeline(guardian,lifeline)
    return completed('provisional')
