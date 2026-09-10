"""Recorder is independent of inference. Durable finalized-chunk metadata is queued."""
import json
import os
import queue
import shutil
import signal
import subprocess
import tempfile
import threading
import time
from pathlib import Path
from .progress import emit
from .supervisor import open_lifeline,close_lifeline

CAPTURE_STOP_GRACE_SECONDS = 15.0
RELAUNCH_LIMIT = 5                    # per rolling hour: enough for a bad afternoon, never an endless loop
RELAUNCH_WINDOW_SECONDS = 3600.0
RELAUNCH_WAIT_SECONDS = 1.0           # let ScreenCaptureKit release the devices the dead helper held
# A helper that never survived its first seconds is failing at startup — screen-recording permission, a full
# disk, no display. Relaunching repeats the failure and buries the one message the owner needs to read.
RELAUNCH_MIN_UPTIME_SECONDS = 20.0
STALL_MARGIN_SECONDS = 20.0           # added to 2*chunk_seconds before a silent-but-alive helper is replaced
RECORDING_HEARTBEAT_SECONDS = 60.0

def record(binary, directory, seconds, chunk_seconds, pipeline=None, store=None, title='Meeting', pipeline_factory=None, result_path=None, data_dir=None, cloud=False):
    directory=Path(directory).resolve()
    directory.mkdir(parents=True,exist_ok=True,mode=0o700)
    if (directory/'events.jsonl').exists(): raise ValueError('Use a new capture directory; existing recordings are never overwritten')
    # Only the app's own <data>/recordings/<uuid> layout implies a data folder; a private or test capture
    # folder gets no recording heartbeat rather than a guess at somebody else's directory.
    if data_dir is not None: data_dir=Path(data_dir)
    elif directory.parent.name=='recordings': data_dir=directory.parent.parent
    binary=str(Path(binary).resolve())
    pending=queue.Queue(); errors=[]; captured=[0]; preview_failed=0
    capture_failed=threading.Event()
    from .recovery import current_job_metadata
    mid=store.create_meeting(title,{**current_job_metadata(),'capture_dir':str(directory),'provisional':True,
        **({'cloud_intent':'capture'} if cloud else {})}) if store else None   # marker only: finalize still writes cloud_mode
    relaunches=0; relaunched_at=[]; last_end=0.0; last_chunk_at=None; per_source={}
    process=None; guardian=None; lifeline=None; thread=None; launched_at=0.0; error_mark=0; marker=None
    last_beat=0.0   # read by the finally; must exist before the first thing that can fail (model warm-up)
    def completed(status):
        if result_path is not None:
            target=Path(result_path);temp=None
            try:
                with tempfile.NamedTemporaryFile(mode='w',dir=target.parent,prefix='.meeting-os-record-',delete=False) as out:
                    temp=Path(out.name)
                    json.dump({'meeting':mid,'capture_dir':str(directory),'status':status,'finalized_chunks':captured[0],'preview_failed_chunks':preview_failed,'relaunches':relaunches,'errors':errors[:8]},out,ensure_ascii=False)
                    out.flush();os.fsync(out.fileno())
                temp.replace(target)
            finally:
                if temp is not None:temp.unlink(missing_ok=True)
        return mid
    def note(event):
        """One supervisor line into the journals. events.jsonl is this process's log; the app's capture_state
        reads only the helper journal, so a relaunch has to be visible there too — but never create that file,
        or a folder whose helper died before writing it would look like it holds no audio."""
        line=json.dumps(event,ensure_ascii=False)+'\n'
        for name in ('events.jsonl','capture-native.jsonl'):
            path=directory/name
            if name!='events.jsonl' and not path.exists(): continue
            try:
                with path.open('a') as out: out.write(line); out.flush(); os.fsync(out.fileno())
            except OSError: pass
    def reader(child,sentinel):
        nonlocal last_end,last_chunk_at
        try:
            with (directory/'events.jsonl').open('a',buffering=1) as log:
                for line in child.stdout:
                    log.write(line); log.flush(); os.fsync(log.fileno())
                    try: event=json.loads(line)
                    except json.JSONDecodeError: continue
                    if event.get('event')=='chunk':
                        captured[0]+=1; pending.put(event)
                        # The stall watchdog and the relaunch offset must follow the helper, not the live
                        # pipeline: a slow preview pass must never look like a stalled recorder.
                        last_chunk_at=time.monotonic()
                        start,duration=event.get('start'),event.get('duration')
                        if type(start) in (int,float): last_end=max(last_end,float(start)+(float(duration) if type(duration) in (int,float) else 0.0))
                        per_source[event.get('source')]=per_source.get(event.get('source'),0)+1
                    if event.get('event')=='error':
                        errors.append(event.get('message','Capture error'))
                        capture_failed.set()
        except Exception as exc:
            errors.append('Capture log failure: '+str(exc))
            if child.poll() is None: child.send_signal(signal.SIGTERM)
        finally: pending.put(sentinel)
    def attach(offset):
        """`offset is None` is the first launch. Any number — 0.0 included — is a relaunch, and the helper is
        told so by the presence of --start-offset, not by its value: a helper that stalls before its first
        chunk hands back 0.000 seconds, and that meeting must still be recoverable."""
        nonlocal process,guardian,lifeline,thread,launched_at,error_mark,marker
        command=[binary,'--output',str(directory),'--seconds',str(seconds if offset is None else max(1.0,float(seconds)-offset)),'--chunk-seconds',str(chunk_seconds)]
        if offset is not None: command+=['--start-offset',f'{offset:.3f}']
        process=subprocess.Popen(command,stdout=subprocess.PIPE,text=True,start_new_session=True)
        guardian,lifeline=open_lifeline(process)
        launched_at=time.monotonic(); error_mark=len(errors); marker=object()   # end-of-stdout token for this helper only
        thread=threading.Thread(target=reader,args=(process,marker),daemon=True); thread.start()
    def retire():
        nonlocal guardian,lifeline
        if process.poll() is None:
            process.send_signal(signal.SIGTERM)
            try: process.wait(timeout=5)
            except subprocess.TimeoutExpired: process.kill(); process.wait()
        else: process.wait()
        thread.join(timeout=5)
        try: process.stdout.close()
        except Exception: pass
        close_lifeline(guardian,lifeline); guardian=lifeline=None   # the outer cleanup must not close this pipe twice
    try: attach(None)
    except Exception:
        if store: store.status(mid,'failed')
        raise
    started=time.monotonic()
    print(json.dumps({'meeting':mid,'capture_dir':str(directory),'status':'capturing'},ensure_ascii=False),flush=True)
    old_handler=signal.getsignal(signal.SIGINT); stopping=False; stop_deadline=None; reason=None
    def stop(sig,frame):
        nonlocal stopping, stop_deadline
        if not stopping:
            stopping=True
            stop_deadline=time.monotonic()+CAPTURE_STOP_GRACE_SECONDS
            if process.poll() is None: process.send_signal(signal.SIGINT)
            emit("stopping_capture")
            print('Stopping capture; draining finalized chunks...',flush=True)
    def end_helper(why):
        """Wind this helper down so a fresh one can take the meeting over. Whether that actually happens is
        decided once it is gone, by relaunch(); the same bounded grace as a user stop applies either way."""
        nonlocal stop_deadline, reason
        if reason is None: reason=why
        if stop_deadline is None: stop_deadline=time.monotonic()+CAPTURE_STOP_GRACE_SECONDS
        if process.poll() is None: process.send_signal(signal.SIGINT)
    def relaunch():
        """Replace the dead/hung helper, continuing the same timeline in the same folder. True when a new one runs."""
        nonlocal relaunches, stop_deadline, reason
        why=reason or 'exit'; mark=error_mark
        if stopping or time.monotonic()-launched_at < RELAUNCH_MIN_UPTIME_SECONDS: return False
        now=time.time(); relaunched_at[:]=[t for t in relaunched_at if now-t < RELAUNCH_WINDOW_SECONDS]
        if len(relaunched_at) >= RELAUNCH_LIMIT:
            errors.append(f'Kayıt yardımcısı bir saat içinde {RELAUNCH_LIMIT} kez yeniden başlatıldı; ses korundu')
            return False
        retire()
        relaunched_at.append(now); relaunches+=1
        offset=round(max(last_end,0.0),3)
        note({'event':'relaunch','attempt':relaunches,'reason':why,'start_offset':offset})
        time.sleep(RELAUNCH_WAIT_SECONDS)
        del errors[mark:]   # the dead helper's complaints are history: a recording that recovers stays provisional
        capture_failed.clear(); stop_deadline=None; reason=None
        if stopping: return False
        try: attach(offset)
        except Exception as exc:
            errors.append('Kayıt yardımcısı yeniden başlatılamadı: '+str(exc)); return False
        return True
    def beat():
        """Tiny, at most once a minute: proof to the owner (and the other Mac) that the recording is alive."""
        if data_dir is None: return
        from .capture_metrics import capture_health, journal_events
        from .reports import write_recording_heartbeat
        health=capture_health(journal_events(directory/'capture-native.jsonl'))
        try: free=shutil.disk_usage(directory).free
        except OSError: free=None
        write_recording_heartbeat(data_dir,{'meeting':mid,'capture_dir':str(directory),'elapsed_seconds':round(time.monotonic()-started,1),
            'chunks':dict(per_source),'chunks_total':captured[0],'free_disk':free,'relaunches':relaunches,
            'last_chunk_age_seconds':None if last_chunk_at is None else round(time.monotonic()-last_chunk_at,1),
            **{k:health[k] for k in ('restarts','wakes','gap_seconds','wake_gap_seconds')}})
    signal.signal(signal.SIGINT,stop)
    outcome=None   # the receipt status, decided by the normal path and written by the finally whatever happens
    try:
        # Capture and its durable journal start before expensive model warm-up.
        if pipeline_factory is not None: pipeline=pipeline_factory()
        if hasattr(pipeline,"cancel_requested"):pipeline.cancel_requested=lambda:stopping
        while True:
            # A failed helper can leave stdout open. Give it the same bounded
            # shutdown and finalized-chunk drain as an explicit user stop.
            if capture_failed.is_set() and stop_deadline is None: capture_failed.clear(); end_helper('error')
            if os.getppid()==1 and not stopping: errors.append('Uygulama kapandı; kayıt güvenle durduruldu'); stop(None,None)   # orphaned by an app crash: never record for hours unattended
            # Alive but silent for two chunk periods: ScreenCaptureKit is gone and the helper has not noticed.
            if not stopping and stop_deadline is None and process.poll() is None and time.monotonic()-max(launched_at,last_chunk_at or 0.0) > 2*float(chunk_seconds)+STALL_MARGIN_SECONDS:
                end_helper('stall')
            # The reader may never reach EOF if the native helper hangs.
            # Check the deadline before waiting, including when chunks are queued.
            if stop_deadline is not None and time.monotonic() >= stop_deadline:
                if process.poll() is None:
                    process.kill()
                    errors.append('Capture did not exit after stop; recover finalized audio with finalize')
                if stopping or not relaunch(): break
                continue
            if data_dir is not None and not stopping and time.monotonic()-last_beat >= RECORDING_HEARTBEAT_SECONDS:
                last_beat=time.monotonic(); beat()
            try: event=pending.get(timeout=.1)
            except queue.Empty: continue
            if not isinstance(event,dict):
                if event is not marker: continue   # a helper we already replaced; the current one is still running
                if stopping or not relaunch(): break
                continue
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
                    if os.environ.get('MEETING_OS_LIVE_PREVIEW')=='1': print(f'{row.start:8.2f} {row.speaker_name or row.speaker}: {row.text}',flush=True)   # transcript text stays out of last-job.log unless a CLI user opts in
                print(json.dumps({'backlog_chunks':pending.qsize()}),flush=True)
            except Exception as exc:
                if stopping:continue
                from .preview_failures import record_failure
                preview_failed+=1
                if not record_failure(directory,event):
                    message="Canlı metin hata günlüğü yazılamadı; ses arşivini kontrol edin"
                    if message not in errors:errors.append(message)
                # Preview failures do not invalidate captured audio. Keep the
                # normal completion receipt so the UI can run the full final pass.
                print(json.dumps({'error':str(exc),'chunk':event['path'],'recover':'finalize capture directory'}),flush=True)
        try: code=process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            process.kill(); code=process.wait(); errors.append('Capture did not exit')
        if stopping and captured[0]==0 and code in (0,-2,-15,-9):   # a deliberate stop with nothing captured is a cancel even when the helper had to be killed
            if store: store.status(mid,'canceled')
            outcome='canceled'
        else:
            if code: errors.append(f'Capture exited {code}')
            # Audio on disk outranks a supervisor complaint. A recording that produced chunks is provisional and
            # finalizable whatever else went wrong, so it reaches the app as a receipt (with its errors) and a
            # zero exit; only a capture that produced nothing at all is a failure the user has to be told about.
            if store: store.status(mid,'provisional' if captured[0] else 'incomplete')
            outcome='provisional' if captured[0] else 'incomplete'
            if errors and not captured[0]: raise RuntimeError('; '.join(errors))
    except BaseException:
        # Even a supervisor dying mid-loop leaves a meeting that holds audio: provisional, so retry_candidates
        # and the app's finalize path can still reach it. Only an empty capture is incomplete.
        if store and outcome is None: store.status(mid,'provisional' if captured[0] else 'incomplete')
        raise
    finally:
        signal.signal(signal.SIGINT,old_handler)
        if process.poll() is None:
            process.send_signal(signal.SIGTERM)
            try: process.wait(timeout=15)
            except subprocess.TimeoutExpired: process.kill(); process.wait()
        thread.join(timeout=5); process.stdout.close()
        close_lifeline(guardian,lifeline)
        if data_dir is not None and last_beat:
            from .reports import clear_recording_heartbeat
            clear_recording_heartbeat(data_dir)   # never leave a line claiming a meeting is still being taped
        # Leave a receipt whenever there is audio, even when the supervisor is dying: without it the app shows
        # "Kayıt tamamlanamadı", nothing auto-finalizes and retry_candidates never learns the meeting exists.
        # A capture that produced nothing has nothing to hand over and stays a plain error.
        if captured[0] or outcome=='canceled': completed(outcome or 'provisional')
    return mid
