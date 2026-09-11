"""Finalize a recorded capture through OpenRouter only: no local STT, diarization or identity models.

Audio assembly is plain file I/O. Each source (mic / system) is encoded with ffmpeg into bounded
Opus pieces and sent to the selected OpenRouter model; diarization-capable models return
speaker-labelled segments. Every finished piece is checkpointed with its transcript in one
transaction, so an interrupted job resumes without re-uploading finished pieces.
"""
import contextlib
import errno
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import subprocess

import numpy as np
import soundfile as sf
from .openrouter import OpenRouterClient, STT_MODEL, _consent, validate_stt_model, diarization_options, error_kind, error_message
from .progress import emit
from .types import Segment

PIECE_SECONDS = 300           # MAI-Transcribe 2 returned HTTP 500 for a 552 s piece and succeeded at 300 s (63 s latency); labels stay consistent inside a piece
FINE_PIECE_SECONDS = 30       # models without diarization get short windows so timing stays useful
MAX_PIECE_BYTES = 24*1024*1024
REQUEST_TIMEOUT = 600
UPLOAD_WORKERS = 3            # pieces in flight at once; MAI answered a 5-minute piece in ~63 s
LOW_PRIORITY_WORKERS = 2      # idle-time retry: one uploader at a time took 51 minutes over a 2 h meeting, and nobody is at the Mac to notice
ENCODE_WORKERS = 2            # ffmpeg runs ahead of the uploads; two is enough to keep the pool fed without competing with a meeting
PREFETCH_PIECES = 3           # pieces encoded ahead of the batch being uploaded; the Opus bytes sit in a scratch file, not in RAM
MIC_FALLBACK = 'Ben'   # nobody's name: what a mic row is called until its owner types one in Settings
SOURCE_LABELS = {'mic':MIC_FALLBACK,'system':'Karşı taraf'}   # 'mic' is only the fallback when user_name is unset; source_labels() is what jobs use


def source_labels(owner=None):
    """Mic audio is always the person who owns this Mac. The name is read from settings once per job, never per segment."""
    return {**SOURCE_LABELS,'mic':owner.strip()} if isinstance(owner,str) and owner.strip() else dict(SOURCE_LABELS)
RETRY_WAITS = (2,8,20)        # a rate limit or a 5xx usually clears in seconds; 30 s of waiting is cheaper than losing the batch
RETRY_JITTER = 0.25           # three workers that failed together must not come back in lockstep
BACKOFF_MINUTES = (10,30,120,360)   # idle-retry spacing after a failed job; every 24 h from then on
DISK_FULL_RETRY_MINUTES = 30        # a full disk is fixed by the user, not by waiting longer and longer
DISK_FULL_GRACE_HOURS = 48          # after two days of "free some space" it is a failure like any other
MAX_CLOUD_RETRIES = 30        # the queue stops asking after this; the audio is still never deleted


def backoff_minutes(attempt):
    """How long the idle queue waits before offering this meeting again. 1-based attempt count."""
    return BACKOFF_MINUTES[attempt-1] if 1<=attempt<=len(BACKOFF_MINUTES) else 24*60


def next_attempt(meta):
    """The 1-based attempt number this meeting is about to spend, capped. Counted when the attempt STARTS: a
    SIGKILL, a power cut or a kernel panic never reaches note_cloud_failure, and a meeting that takes the helper
    down every single time was therefore offered to the queue forever."""
    previous=meta.get('cloud_retry_attempt')
    return min((previous if isinstance(previous,int) and not isinstance(previous,bool) and previous>0 else 0)+1,MAX_CLOUD_RETRIES)


def is_disk_full(exc):
    """A local out-of-space error, whatever raised it. `kind` comes from audio.disk_full so the sidebar shows a
    line the user can act on rather than a provider name."""
    return isinstance(exc,OSError) and getattr(exc,'errno',None)==errno.ENOSPC


def note_cloud_failure(store, mid, exc):
    """Remember why the cloud refused this meeting, and when it is worth asking again. Nothing about the
    audio or the finished pieces changes: this is the one line the sidebar shows and the idle queue reads."""
    from datetime import datetime, timedelta, timezone
    row=store.db.execute('SELECT metadata FROM meetings WHERE id=?',(mid,)).fetchone()
    if not row: return None
    meta=json.loads(row['metadata'] or '{}')
    # The attempt is already counted when it started, unless this failure came from somewhere that never began one.
    open_attempt=meta.pop('cloud_attempt_open',None)
    stored=meta.get('cloud_retry_attempt')
    stored=stored if isinstance(stored,int) and not isinstance(stored,bool) and stored>0 else 0
    now=datetime.now(timezone.utc)
    free_space=is_disk_full(exc)
    if free_space:
        # Two days of the same "free some space" is not a temporary condition, it is a meeting that will never
        # finish this way. Until then the attempt is left exactly as it stands: nothing was asked of
        # OpenRouter, so spending one of the thirty retries would eventually retire a good recording — and
        # GIVING one back (the old `stored-1`) let such a meeting be offered to the queue forever.
        started=meta.get('cloud_disk_full_since')
        try: started=datetime.fromisoformat(started) if isinstance(started,str) else None
        except ValueError: started=None
        if started and started.tzinfo is None: started=started.replace(tzinfo=timezone.utc)
        if started and now-started>timedelta(hours=DISK_FULL_GRACE_HOURS): free_space=False
        else: meta['cloud_disk_full_since']=(started or now).isoformat()
    if free_space:
        attempt=stored
        wait=DISK_FULL_RETRY_MINUTES
    else:
        meta.pop('cloud_disk_full_since',None)
        attempt=(stored or next_attempt(meta)) if open_attempt else next_attempt(meta)
        wait=backoff_minutes(attempt)
    kind='disk_full' if is_disk_full(exc) else error_kind(exc)
    message=error_message(exc) if getattr(exc,'user_message',None) or not is_disk_full(exc) else 'Disk dolu; devam etmek için yer açın.'
    meta['cloud_error']={'kind':kind,'message':message,'at':now.isoformat()}
    meta['cloud_retry_attempt']=attempt
    meta['cloud_retry_after']=(now+timedelta(minutes=wait)).isoformat()
    with store.db: store.db.execute('UPDATE meetings SET metadata=? WHERE id=?',(json.dumps(meta,ensure_ascii=False),mid))
    # The sidebar line is per meeting and the user clears it; the journal is what a second Mac reads next week.
    # The data folder comes from the store, never from a default: a test store must not write to the real one.
    try:
        from .errors import record,meeting_key
        record('cloud',f'{kind}: {message}',data_dir=Path(getattr(store,'path','')).parent,
               context={'meeting':meeting_key(mid),'kind':kind,'attempt':attempt})
    except Exception: pass
    return meta['cloud_error']


def note_cloud_cancel(store, mid):
    """The user stopped this job with ⌘. (quit lets a running job finish). It leaves no `cloud_error`, so without a mark of its own the
    idle queue would read a plain `incomplete` meeting and restart the upload ten minutes later — work the
    user just refused. The mark is cleared the moment they start a finalize by hand."""
    row=store.db.execute('SELECT metadata FROM meetings WHERE id=?',(mid,)).fetchone()
    if not row: return None
    meta=json.loads(row['metadata'] or '{}')
    meta.pop('cloud_attempt_open',None)   # the attempt is over; a later failure must count itself
    meta['cloud_canceled']=True
    with store.db: store.db.execute('UPDATE meetings SET metadata=? WHERE id=?',(json.dumps(meta,ensure_ascii=False),mid))
    return True


def pieces(duration, length):
    if not math.isfinite(duration) or duration<=0: raise ValueError('Ses süresi geçersiz')
    result=[];start=0.0
    while start<duration:
        end=min(start+length,duration);result.append((start,end));start=end
    if len(result)>10000: raise ValueError('Çok fazla ses parçası')
    return result


ECHO_HOP=800            # 50 ms RMS envelope
ECHO_THRESHOLD=0.8      # measured: speaker bleed 0.72–0.88, unrelated speech 0.07

def _envelope(x):
    n=len(x)//ECHO_HOP
    if n==0: return np.zeros(0,dtype='float32')
    return np.sqrt((x[:n*ECHO_HOP].reshape(n,ECHO_HOP)**2).mean(axis=1))

def envelope_correlation(mic, system, max_lag=8):
    """Peak normalized correlation of 50 ms loudness envelopes within ±1 s. Waveform correlation fails
    (room acoustics and clock offsets); loudness envelopes still line up when the mic only hears the speakers."""
    em=_envelope(mic);es=_envelope(system)
    if len(em)<10 or len(es)<10 or em.max()<1e-4 or es.max()<1e-4: return 0.0
    em=(em-em.mean())/(em.std()+1e-9);es=(es-es.mean())/(es.std()+1e-9)
    best=0.0
    for lag in range(-max_lag,max_lag+1):
        a=em[lag:] if lag>=0 else em[:lag];b=es[:len(es)-lag] if lag>0 else (es if lag==0 else es[-lag:])
        n=min(len(a),len(b))
        if n>=10: best=max(best,float((a[:n]*b[:n]).mean()))
    return best

def is_echo(mic_path, system_path, start, end):
    """True when the microphone window is the system audio bleeding through the speakers."""
    with sf.SoundFile(mic_path) as f:
        f.seek(round(start*f.samplerate));m=f.read(round((end-start)*f.samplerate),dtype='float32')
    with sf.SoundFile(system_path) as f:
        if round(start*f.samplerate)>=f.frames: return False
        f.seek(round(start*f.samplerate));s=f.read(round((end-start)*f.samplerate),dtype='float32')
    return envelope_correlation(m,s)>=ECHO_THRESHOLD


def is_silent(path, start, end, threshold=1e-4):
    with sf.SoundFile(path) as f:
        f.seek(round(start*f.samplerate));remaining=round((end-start)*f.samplerate)
        while remaining>0:
            block=f.read(min(remaining,f.samplerate*10),dtype='float32')
            if not len(block): break
            if np.abs(block).max()>threshold: return False
            remaining-=len(block)
    return True


def upload_workers():
    """One piece at a time only while a Zoom meeting is actually on screen — that is what the flag file means,
    and the app drops it for a job that is already running when the next meeting opens. Plain low priority (the
    idle retry queue) still gets two: a single uploader spent 51 minutes on a two-hour meeting for no benefit,
    because nothing is on screen to protect."""
    flag=os.environ.get('MEETING_OS_LOW_PRIORITY_FLAG')
    if flag and os.path.exists(flag): return 1
    if os.environ.get('MEETING_OS_LOW_PRIORITY'): return LOW_PRIORITY_WORKERS
    return UPLOAD_WORKERS


def job_usage(started):
    """CPU seconds, peak memory and wall time of this job, for the shared diagnostics report."""
    import resource, time
    me=resource.getrusage(resource.RUSAGE_SELF); kids=resource.getrusage(resource.RUSAGE_CHILDREN)
    return {'cpu_seconds':round(me.ru_utime+me.ru_stime+kids.ru_utime+kids.ru_stime,1),'peak_rss_mb':round(max(me.ru_maxrss,kids.ru_maxrss)/1e6,1),
            'wall_seconds':round(time.monotonic()-started,1),'low_priority':bool(os.environ.get('MEETING_OS_LOW_PRIORITY')),'upload_workers':upload_workers()}


def encode_piece(path, start, end, ffmpeg=None):
    command=[ffmpeg or shutil.which('ffmpeg') or '/opt/homebrew/bin/ffmpeg','-nostdin','-v','error','-ss',f'{start:.3f}','-t',f'{end-start:.3f}','-i',str(path),
             '-vn','-ac','1','-ar','16000','-c:a','libopus','-b:a','32k','-f','ogg','pipe:1']
    result=subprocess.run(command,capture_output=True,timeout=600)
    if result.returncode or not result.stdout: raise ValueError('Ses parçası sıkıştırılamadı')
    return result.stdout


def digest_files(paths):
    h=hashlib.sha256()
    for path in paths:
        with Path(path).open('rb') as f:
            for chunk in iter(lambda:f.read(1024*1024),b''): h.update(chunk)
    return h.hexdigest()


MERGE_GAP=1.0
MERGE_MAX=30.0

def merge_segments(segments, gap=MERGE_GAP, longest=MERGE_MAX):
    """Join consecutive same-speaker provider phrases so segments read naturally and reach the 3 s voiceprint minimum."""
    out=[]
    for seg in segments:
        if not seg['text']: continue
        last=out[-1] if out else None
        if last and last['speaker']==seg['speaker'] and seg['start']-last['end']<=gap and seg['end']-last['start']<=longest:
            last['end']=max(last['end'],seg['end']);last['text']=(last['text']+' '+seg['text']).strip()
        else: out.append(dict(seg))
    return out


def _tokens(text):
    import re
    return [t for t in re.split(r'[^\wçğıöşüÇĞİÖŞÜ]+',text.lower()) if len(t)>1]


def flag_echo(store, mid, threshold=0.6):
    """A microphone segment whose words largely repeat the system audio of the same interval is speaker bleed, not the user."""
    rows=store.segments(mid);system=[r for r in rows if r['source']=='system'];flagged=0
    for r in rows:
        if r['source']!='mic' or 'possible_echo' in r['flags']: continue
        mine=_tokens(r['text'])
        if len(mine)<4: continue
        overlap=set(_tokens(' '.join(s['text'] for s in system if s['start']<r['end'] and s['end']>r['start'])))
        ratio=sum(1 for t in mine if t in overlap)/len(mine)
        if ratio>=threshold:
            r['flags'].append('possible_echo');r.setdefault('metrics',{})['echo_overlap']=round(ratio,3);flagged+=1
            with store.db: store.db.execute('UPDATE segments SET payload=? WHERE id=? AND meeting=?',(json.dumps(r,ensure_ascii=False),r['id'],mid))
    return flagged


def speaker_label(source, provider_speaker, piece_index, multi_piece, owner=None):
    if source=='mic' or provider_speaker is None: return source_labels(owner).get(source,source)
    try: number=int(provider_speaker)+1
    except ValueError: number=provider_speaker
    return f'Konuşmacı {piece_index+1}-{number}' if multi_piece else f'Konuşmacı {number}'


REORDER_OFFSET = 1_000_000   # positions are a primary key; park them out of the way before renumbering


def _reorder_checkpoints(store, mid, old, plan, plan_json):
    """A stored plan that holds exactly the same pieces in a different order (an app update changed how the
    plan is laid out) is not a changed recording. Renumber the finished pieces instead of refusing to resume
    — otherwise every meeting that was mid-upload during the update would have to be paid for again."""
    try: stored=[tuple(piece) for piece in json.loads(old['plan'])]
    except (ValueError,TypeError): return None
    if sorted(stored)!=sorted(plan): return None
    position_of={piece:index for index,piece in enumerate(plan)}
    with store.db:
        store.db.execute('UPDATE cloud_chunks SET position=position+? WHERE meeting=?',(REORDER_OFFSET,mid))
        for index,piece in enumerate(stored):
            store.db.execute('UPDATE cloud_chunks SET position=? WHERE meeting=? AND position=?',(position_of[piece],mid,index+REORDER_OFFSET))
        store.db.execute('UPDATE cloud_sources SET plan=? WHERE meeting=?',(plan_json,mid))
    return store.db.execute('SELECT * FROM cloud_sources WHERE meeting=?',(mid,)).fetchone()


def transcribe_sources(store, mid, sources, client, *, consent=False, model=STT_MODEL, ffmpeg=None, hint=None, owner=None, mic_windows=None):
    """sources: {'mic': path, 'system': path} of 16 kHz mono files. Returns the plan.

    `mic_windows` is `mic_gate_windows`' answer: the spans where the microphone was part of the meeting.
    None (no gate journal) keeps the old behaviour and transcribes the whole mic track."""
    _consent(consent);validate_stt_model(model)
    labels=source_labels(owner)
    diarize=diarization_options(model) is not None
    length=PIECE_SECONDS if diarize else FINE_PIECE_SECONDS
    per_source={}
    for source in sorted(sources):
        info=sf.info(sources[source])
        if info.samplerate!=16000 or info.channels!=1 or not 0<info.duration<=14400: raise ValueError('Ses mono 16 kHz ve en fazla dört saat olmalı')
        piece_length=length   # the mic gets the same long pieces: 30 s cuts chopped the user's own words 119 times an hour and starved the ASR of context
        per_source[source]=[(source,a,b,index) for index,(a,b) in enumerate(pieces(info.duration,piece_length))]
    # Interleave the sources (mic0, sys0, mic1, sys1…). All-mic-then-all-system meant that on a speaker phone —
    # where every mic piece is echo and is skipped for free — the first half of the job finished in seconds and
    # the progress line promised a finish eight times sooner than the truth.
    plan=[piece for position in range(max((len(v) for v in per_source.values()),default=0))
                for source in sorted(per_source) if position<len(per_source[source])
                for piece in (per_source[source][position],)]
    counts={s:sum(1 for p in plan if p[0]==s) for s in sources}
    signature=digest_files([sources[s] for s in sorted(sources)])
    store.db.executescript('''CREATE TABLE IF NOT EXISTS cloud_sources(meeting TEXT PRIMARY KEY REFERENCES meetings(id), digest TEXT, plan TEXT);
        CREATE TABLE IF NOT EXISTS cloud_chunks(meeting TEXT REFERENCES meetings(id), position INTEGER, usage TEXT, PRIMARY KEY(meeting,position));''')
    if 'model' not in {r[1] for r in store.db.execute('PRAGMA table_info(cloud_sources)')}:
        with store.db:store.db.execute("ALTER TABLE cloud_sources ADD COLUMN model TEXT NOT NULL DEFAULT 'openai/gpt-transcribe'")
    plan_json=json.dumps(plan)
    old=store.db.execute('SELECT * FROM cloud_sources WHERE meeting=?',(mid,)).fetchone()
    if old and old['digest']==signature and old['model']==model and old['plan']!=plan_json:
        old=_reorder_checkpoints(store,mid,old,plan,plan_json) or old   # same pieces in a new order: move the checkpoints, do not throw them away
    if old and (old['digest']!=signature or old['plan']!=plan_json or old['model']!=model):
        paid=[u for (u,) in store.db.execute('SELECT usage FROM cloud_chunks WHERE meeting=?',(mid,)) if u and ('"cost"' in u or '"seconds"' in u)]  # silent/echo windows cost nothing
        if paid or old['digest']!=signature or old['model']!=model: raise ValueError('Kaynak ses veya plan değişti; devam edilmedi')
        with store.db:  # only free (skipped) checkpoints exist: adopt the new piece plan without losing anything
            store.db.execute('DELETE FROM cloud_chunks WHERE meeting=?',(mid,));store.db.execute('UPDATE cloud_sources SET plan=? WHERE meeting=?',(plan_json,mid))
        old=store.db.execute('SELECT * FROM cloud_sources WHERE meeting=?',(mid,)).fetchone()
    if not old:
        with store.db:store.db.execute('INSERT INTO cloud_sources(meeting,digest,plan,model) VALUES(?,?,?,?)',(mid,signature,plan_json,model))
    done={row[0]:(row[1] or '') for row in store.db.execute('SELECT position,usage FROM cloud_chunks WHERE meeting=?',(mid,))}
    # Progress weighted by audio seconds, not by piece count: a skipped echo window finishes instantly and a
    # five-minute upload does not. `total` shrinks as windows turn out to be skippable, `uploaded` only grows
    # when audio really went out, so the remaining-time estimate is built on the rate that is actually running.
    seconds=[max(0.0,b-a) for _,a,b,_ in plan]
    weight={'uploaded':0.0,'total':float(sum(seconds))}
    for position,usage in done.items():
        if 0<=position<len(plan):
            if 'skipped' in usage: weight['total']-=seconds[position]
            else: weight['uploaded']+=seconds[position]
    # What an earlier run already paid for is not this run's speed. Counting it made a resumed job that had
    # uploaded 55 of 60 minutes look one minute from done the second it started, whatever it was doing.
    baseline=weight['uploaded']
    import random, shutil as _shutil, tempfile, time
    from concurrent.futures import ThreadPoolExecutor
    staging=Path(tempfile.mkdtemp(prefix='meeting-os-pieces-'))
    def progress(detail='OpenRouter'):
        done_now=max(0.0,weight['uploaded']-baseline);left=max(weight['total']-baseline,done_now)
        emit('transcribing',finished,len(plan),detail,uploaded_seconds=round(done_now,1),total_seconds=round(left,1))
    def prepare(position):
        """Skip (echo/silent) or encode this piece. Runs on the encode pool one batch ahead of the uploads;
        the Opus bytes land in a scratch file so a prefetched batch never sits in memory."""
        source,a,b,index=plan[position];path=sources[source]
        # The gate first: a piece recorded while the microphone was not part of the meeting is never read,
        # never encoded, never uploaded and never transcribed — the room conversation simply does not exist.
        if source=='mic' and mic_windows is not None and gate_overlap(mic_windows,a,b)<MIC_GATE_MIN_OVERLAP: return ('skip',{'skipped':'mic_gated'})
        silent=is_silent(path,a,b)   # one pass over the window: the echo branch and the silence branch ask the same question
        if source=='mic' and 'system' in sources and not silent and is_echo(path,sources['system'],a,b): return ('skip',{'skipped':'echo'})
        if silent: return ('skip',{'skipped':'silent'})
        audio=encode_piece(path,a,b,ffmpeg)
        if len(audio)>MAX_PIECE_BYTES: raise ValueError('Ses parçası yükleme sınırını aşıyor')
        piece=staging/f'{position:06d}.ogg';piece.write_bytes(audio)
        return ('upload',piece)
    def commit(position,usage,result):
        source,a,b,index=plan[position]
        segments=[]
        if result is not None:
            flags=['cloud_transcript','confidence_unavailable','speaker_unverified']
            multi=counts[source]>1
            provider_segments=merge_segments(result.get('segments') or [])
            if provider_segments:
                for seg in provider_segments:
                    label=speaker_label(source,seg['speaker'],index,multi,owner)
                    segments.append(Segment(a+seg['start'],min(a+seg['end'],b),seg['text'],source,label,
                        metrics={'provider':'openrouter','model':model,'piece':index,'cluster':f'{index}:{seg["speaker"]}'},flags=flags+(['cloud_diarization'] if source!='mic' else [])))
            elif result['text'].strip():
                segments.append(Segment(a,b,result['text'].strip(),source,labels.get(source,source),
                    metrics={'provider':'openrouter','model':model,'piece':index,'usage':usage},flags=flags+['coarse_timing']))
        with store.db:  # transcript and checkpoint land together or not at all
            for segment in segments:
                d=segment.to_dict()
                store.db.execute('INSERT INTO segments(meeting,start,end,source,speaker,speaker_name,payload) VALUES(?,?,?,?,?,?,?)',
                    (mid,segment.start,segment.end,source,segment.speaker,None,json.dumps(d,ensure_ascii=False)))
            store.db.execute('INSERT INTO cloud_chunks VALUES(?,?,?)',(mid,position,json.dumps(usage)))
    pending=[i for i in range(len(plan)) if i not in done]
    finished=len(plan)-len(pending)
    prepared={};cursor=0
    pool=ThreadPoolExecutor(max_workers=UPLOAD_WORKERS)
    encoders=ThreadPoolExecutor(max_workers=ENCODE_WORKERS)
    try:
        def top_up(limit):
            """Keep at most `limit` pieces prepared, so ffmpeg works on the next batch while this one uploads."""
            nonlocal cursor
            while cursor<len(pending) and len(prepared)<limit:
                position=pending[cursor];cursor+=1;prepared[position]=encoders.submit(prepare,position)
        def send(positions,encoded):
            """Upload these pieces, never more than upload_workers() at a time (re-read so a meeting that opens
            mid-job slows the next slice down). Every paid success is checkpointed even when a sibling fails."""
            nonlocal finished
            failures={};queue=list(positions)
            while queue:
                slice_=queue[:max(1,upload_workers())];queue=queue[len(slice_):]
                futures={i:pool.submit(lambda position:client.transcribe(encoded[position].read_bytes(),'ogg',model=model,consent=True,
                    diarize=diarize and plan[position][0]!='mic',timeout=REQUEST_TIMEOUT,hint=hint),i) for i in slice_}
                for position in sorted(futures):
                    try: result=futures[position].result()
                    except Exception as exc: failures[position]=exc;continue
                    commit(position,result['usage'],result);finished+=1;weight['uploaded']+=seconds[position]
                    try: encoded[position].unlink()
                    except OSError: pass
            return failures
        start=0
        while start<len(pending):
            workers=max(1,upload_workers())   # re-read per batch: a meeting may start mid-job
            batch=pending[start:start+workers]; start+=workers
            top_up(len(batch)+min(PREFETCH_PIECES,workers))   # this batch plus one batch of head start, at most three pieces
            progress()
            encoded={}
            for position in batch:
                kind,payload=prepared.pop(position).result()
                if kind=='skip': commit(position,payload,None);finished+=1;weight['total']-=seconds[position];continue
                encoded[position]=payload
            attempt=0;waiting=sorted(encoded)
            while waiting:
                failures=send(waiting,encoded)
                if not failures: break
                # An invalid key or an empty balance cannot be fixed by asking again; a timeout or a 5xx often can.
                fatal=next((e for e in failures.values() if not getattr(e,'retryable',False)),None)
                if fatal is not None or attempt>=len(RETRY_WAITS): raise fatal or failures[min(failures)]
                wait=RETRY_WAITS[attempt]
                progress(f'OpenRouter · yeniden deneme {attempt+1}/{len(RETRY_WAITS)}')
                time.sleep(wait+random.uniform(0,wait*RETRY_JITTER))
                attempt+=1;waiting=sorted(failures)
    finally:
        encoders.shutdown(wait=True,cancel_futures=True)   # a fatal upload error must not keep ffmpeg busy
        pool.shutdown(wait=True)
        _shutil.rmtree(staging,ignore_errors=True)
    finished=len(plan);progress()
    return plan


def import_file_cloud_only(store, path, title, data_dir, *, consent=False, model=None, client=None, ffmpeg=None, embedder=None):
    """Recorded file → OpenRouter transcript with provider diarization. No local model is loaded."""
    _consent(consent)
    if not isinstance(title,str) or not title.strip() or len(title)>200: raise ValueError('Toplantı başlığı gerekli (en fazla 200 karakter)')
    model=validate_stt_model(model or STT_MODEL)
    client=client or OpenRouterClient(max_audio_bytes=MAX_PIECE_BYTES)
    import uuid
    source=Path(path).resolve(strict=True)
    if not source.is_file(): raise ValueError('Ses dosyası bulunamadı')
    data_dir=Path(data_dir);folder=data_dir/'imports'/uuid.uuid4().hex;folder.mkdir(parents=True,mode=0o700)
    target=folder/'audio.wav'
    emit('reading_audio')
    result=subprocess.run([ffmpeg or shutil.which('ffmpeg') or '/opt/homebrew/bin/ffmpeg','-nostdin','-v','error','-i',str(source),'-vn','-ar','16000','-ac','1','-c:a','pcm_f32le',str(target)],capture_output=True,timeout=600)
    if result.returncode or not target.is_file(): raise ValueError('Ses dosyası dönüştürülemedi')
    metadata={'engine':'openrouter','model':model,'cloud_mode':'file','paths':{'system':str(target)},'cloud_upload_authorized':True,'original_name':source.name}
    mid=store.create_meeting(title.strip(),metadata)
    return finalize_capture(store,mid,data_dir,consent=True,model=model,client=client,ffmpeg=ffmpeg,embedder=embedder)


EMBED_WINDOW=30*16000

def embedding_windows(start, end, frames, window=EMBED_WINDOW, minimum=3*16000):
    """Integer sample spans covering [start,end): ≤30 s each, clamped to the file, none shorter than 3 s."""
    a=max(0,round(start*16000));b=min(frames,round(end*16000))
    if b-a<minimum: return []
    out=[]
    while a<b:
        e=min(a+window,b)
        if b-e<minimum: e=b        # fold a short tail into the previous window (≤ 60 s worker cap)
        out.append((a,e));a=e
    return out


def identify_clusters(store, mid, sources, embedder=None):
    """Local, light voiceprint step: one vector per diarized segment; after link_clusters the linked speaker's
    duration-weighted centroid is matched against saved profiles. Never blocks the transcript: caller records failures in metadata."""
    rows=[r for r in store.segments(mid) if 'cloud_diarization' in r['flags'] and r['end']-r['start']>=3 and r.get('embedding') is None and r['source'] in sources]
    if not rows and not any('cloud_diarization' in r['flags'] for r in store.segments(mid)): return {'embedded':0,'named':0}
    if embedder is None:
        from .final_identity import FinalEmbedder
        embedder=FinalEmbedder(light=True)
    emit('identifying')
    by_source={}
    for r in rows: by_source.setdefault(r['source'],[]).append(r)
    embedded=0
    for source,group in by_source.items():
        frames=sf.info(sources[source]).frames
        spans=[];owners=[]
        for r in group:  # long turns are embedded in bounded windows and averaged; the worker caps one span at 60 s
            for a,b in embedding_windows(r['start'],r['end'],frames):
                spans.append((a,b));owners.append(r['id'])
        with contextlib.redirect_stdout(__import__('sys').stderr):
            vectors=embedder.embed_file(sources[source],spans)
        by_row={}
        for rid,vector in zip(owners,vectors):
            if vector is not None: by_row.setdefault(rid,[]).append(vector)
        for r in group:
            parts=by_row.get(r['id'])
            if not parts: continue
            r['embedding']=[sum(col)/len(parts) for col in zip(*parts)];r['embedding_model']=embedder.model_id;embedded+=1
            with store.db: store.db.execute('UPDATE segments SET payload=? WHERE id=? AND meeting=?',(json.dumps(r,ensure_ascii=False),r['id'],mid))
    embedded+=embed_short_clusters(store,mid,sources,embedder)
    link_clusters(store,mid,embedder.model_id)
    named=0
    speakers={}   # the linked speaker label (one person across pieces), not the per-piece provider cluster
    for r in store.segments(mid):
        if (r.get('metrics') or {}).get('cluster') is not None: speakers.setdefault((r['source'],r['speaker']),[]).append(r)
    scored=[]
    threshold,margin=identity_bars(Path(store.path).parent)   # today's constants unless a calibration was applied
    for (source,speaker),members in speakers.items():
        centroid=linked_centroid(members,embedder.model_id)
        if centroid is None: continue
        scored.append((members,store.identify(centroid,embedder.model_id,threshold,margin),centroid))
    assignment=assign_identities([(members,identity) for members,identity,_ in scored])
    suggested=0;fed=0
    for members,identity,centroid in scored:
        name=assignment.get(id(members))
        sim=identity.get('similarity') or 0;gap=identity.get('margin') or 0
        suggestion=identity.get('candidate') if (not name and sim>=SUGGEST_THRESHOLD and gap>=margin) else None
        for r in members:
            r.setdefault('metrics',{})['identity']={**identity,'name':name,'suggested':suggestion}
            with store.db: store.db.execute('UPDATE segments SET speaker_name=?,payload=? WHERE id=? AND meeting=?',(name,json.dumps(r,ensure_ascii=False),r['id'],mid))
        if name: named+=len(members)
        if suggestion: suggested+=len(members)
        total=sum(r['end']-r['start'] for r in members)   # the whole linked speaker, so a colleague split over pieces still feeds
        if name and sim>=FEED_THRESHOLD and gap>=FEED_MARGIN and total>=FEED_MIN_SECONDS:
            cluster=(members[0].get('metrics') or {}).get('cluster')   # first sub-cluster keeps the provenance stable across re-runs
            if store.add_sample_if_new(name,centroid,embedder.model_id,total,f'auto:{mid}:{cluster}',cap=MAX_AUTO_SAMPLES): fed+=1
    return {'embedded':embedded,'named':named,'suggested':suggested,'fed':fed}


CLUSTER_MIN_SECONDS=2.0   # concatenated back-channels; the embedder accepts ≥1 s, the margin rule guards weak vectors
CLUSTER_MAX_SECONDS=60.0

def embed_short_clusters(store, mid, sources, embedder):
    """Back-channel speakers (“hı hı”, “aynen”) never reach 3 s in one turn. Every such cluster's pieces are
    concatenated, all clusters are appended to one private snapshot and embedded in a single guarded child
    (one span per cluster), so Torch is imported and the weights hashed once instead of once per cluster."""
    import tempfile
    clusters={}
    for r in store.segments(mid):
        cl=(r.get('metrics') or {}).get('cluster')
        if cl is not None and 'cloud_diarization' in r['flags'] and r['source'] in sources: clusters.setdefault((r['source'],cl),[]).append(r)
    with tempfile.TemporaryDirectory(prefix='meeting-os-cluster-') as tmp:
        snapshot=Path(tmp)/'cluster.wav';batch=[];offset=0
        with sf.SoundFile(snapshot,'w',samplerate=16000,channels=1,subtype='FLOAT') as out:
            for (source,cl),members in clusters.items():
                if any(r.get('embedding') for r in members): continue
                total=sum(r['end']-r['start'] for r in members)
                if total<CLUSTER_MIN_SECONDS: continue
                with sf.SoundFile(sources[source]) as f:
                    pieces=[];kept=0.0
                    for r in sorted(members,key=lambda r:r['start']):
                        a=max(0,round(r['start']*f.samplerate));b=min(f.frames,round(r['end']*f.samplerate))
                        if b<=a: continue
                        f.seek(a);pieces.append(f.read(b-a,dtype='float32'));kept+=(b-a)/f.samplerate
                        if kept>=CLUSTER_MAX_SECONDS: break
                if not pieces or kept<CLUSTER_MIN_SECONDS: continue
                audio=np.concatenate(pieces);out.write(audio)   # one cluster in memory at a time
                batch.append((members,kept,(offset,offset+len(audio))));offset+=len(audio)
        if not batch: return 0
        with contextlib.redirect_stdout(__import__('sys').stderr):
            vectors=embedder.embed_file(str(snapshot),[span for _,_,span in batch])
    count=0
    for (members,kept,_),vector in zip(batch,vectors):
        if vector is None: continue
        for r in members:
            r['embedding']=vector;r['embedding_model']=embedder.model_id;r.setdefault('metrics',{})['cluster_embedding']=round(kept,2)
            with store.db: store.db.execute('UPDATE segments SET payload=? WHERE id=? AND meeting=?',(json.dumps(r,ensure_ascii=False),r['id'],mid))
        count+=1
    return count


SUGGEST_THRESHOLD=0.83    # below the naming threshold but worth a one-click confirmation ("Sol Üst?")
FEED_THRESHOLD=0.93       # a match this strong adds one more sample to the profile automatically
FEED_MARGIN=0.08          # correct real matches showed margins 0.086–0.144; 0.10 skipped a 0.941 match
FEED_MIN_SECONDS=10.0
MAX_AUTO_SAMPLES=8        # per person; manual samples count too
LINK_THRESHOLD=0.90       # same voice across 5-minute pieces measured 0.991; different people ≤0.85

def link_clusters(store, mid, model_id):
    """Provider speaker numbers restart in every piece. Clusters whose voiceprints agree (≥0.90) get one
    shared label, numbered by first appearance, so a 40-minute meeting reads as N people, not N×pieces."""
    rows=[r for r in store.segments(mid) if 'cloud_diarization' in r['flags'] and (r.get('metrics') or {}).get('cluster') is not None]
    if not rows: return 0
    clusters={}
    for r in rows: clusters.setdefault(r['metrics']['cluster'],[]).append(r)
    if len(clusters)<2: return 0
    order=sorted(clusters,key=lambda k:min(r['start'] for r in clusters[k]))
    centroid={}
    for k,members in clusters.items():
        vs=[r['embedding'] for r in members if r.get('embedding') and r.get('embedding_model')==model_id]
        if vs: centroid[k]=[sum(col)/len(vs) for col in zip(*vs)]
    parent={k:k for k in order}
    def find(k):
        while parent[k]!=k: k=parent[k]
        return k
    def cos(a,b):
        na=math.sqrt(sum(x*x for x in a));nb=math.sqrt(sum(x*x for x in b))
        return sum(x*y for x,y in zip(a,b))/(na*nb) if na and nb else 0.0
    for i,a in enumerate(order):
        for b in order[i+1:]:
            if a in centroid and b in centroid and a.split(':')[0]!=b.split(':')[0] and cos(centroid[a],centroid[b])>=LINK_THRESHOLD:
                parent[find(b)]=find(a)
    label={}
    for k in order:
        root=find(k)
        if root not in label: label[root]=f'Konuşmacı {len(label)+1}'
    changed=0
    for k,members in clusters.items():
        name=label[find(k)]
        for r in members:
            if r['speaker']!=name:
                r['speaker']=name;r['metrics']['linked']=find(k)
                with store.db: store.db.execute('UPDATE segments SET speaker=?,payload=? WHERE id=? AND meeting=?',(name,json.dumps(r,ensure_ascii=False),r['id'],mid))
                changed+=1
    return changed


def linked_centroid(members, model_id):
    """One vector for a linked speaker: each provider sub-cluster (piece:speaker) is averaged on its own, then the
    sub-clusters are blended by speaking time, so a 10 s sub-cluster does not outweigh a 4-minute one."""
    subs={}
    for r in members: subs.setdefault((r.get('metrics') or {}).get('cluster'),[]).append(r)
    parts=[]
    for rows in subs.values():
        vs=[r['embedding'] for r in rows if r.get('embedding') and r.get('embedding_model')==model_id]
        if not vs: continue
        parts.append((sum(r['end']-r['start'] for r in rows) or 1.0,[sum(col)/len(vs) for col in zip(*vs)]))
    if not parts: return None
    total=sum(w for w,_ in parts)
    return [sum(w*v[i] for w,v in parts)/total for i in range(len(parts[0][1]))]


IDENTITY_THRESHOLD=0.87   # real data: different people 0.65–0.853, same person ≥0.878 (a 5 s cluster the user confirmed); margin rule guards the gap
IDENTITY_MARGIN=0.05


def identity_bars(data_dir=None):
    """(threshold, margin) for this Mac: the shipped constants, unless the user has applied a calibration.

    `quality calibrate` measures a small grid against this Mac's own time-ordered, human-verified evidence and
    writes a recommendation; it changes nothing. Only `quality calibrate --apply` puts the two numbers into
    settings.json, and only a value inside the validated range is read back — anything else, an unreadable
    settings file included, is simply the constant. Nobody's recognition silently changes because a file got
    edited by hand (Codex #5: "veri yetersizse aday etkinleşmez")."""
    threshold, margin = IDENTITY_THRESHOLD, IDENTITY_MARGIN
    if data_dir is None: return threshold, margin
    try:
        from .reports import load_settings
        from .store import IDENTITY_MARGIN_RANGE, IDENTITY_THRESHOLD_RANGE
        settings = load_settings(data_dir)
    except Exception: return threshold, margin
    for key, low, high, index in (('identity_threshold', *IDENTITY_THRESHOLD_RANGE, 0), ('identity_margin', *IDENTITY_MARGIN_RANGE, 1)):
        value = settings.get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool) and low <= float(value) <= high:
            if index == 0: threshold = float(value)
            else: margin = float(value)
    return threshold, margin
OVERSPLIT_THRESHOLD=0.93  # a second cluster may share a name only when it is nearly as close as the best one

def assign_identities(scored):
    """One person per meeting: a profile names only its best-scoring cluster, unless another cluster is clearly the same voice."""
    best={}
    for members,identity in scored:
        name,sim=identity.get('name'),identity.get('similarity') or 0
        if name and (name not in best or sim>best[name][1]): best[name]=(id(members),sim)
    assignment={}
    for members,identity in scored:
        name,sim=identity.get('name'),identity.get('similarity') or 0
        if not name: continue
        top_id,top_sim=best[name]
        if id(members)==top_id or (sim>=OVERSPLIT_THRESHOLD and top_sim-sim<=0.03): assignment[id(members)]=name
    return assignment


MARKER_DRIFT_FLOOR=1.0   # under a second is launch jitter and write latency, not a clock that ran away

def wall_audio_drift(capture_dir, journal='capture-native.jsonl'):
    """How far the wall clock has run ahead of the recording's audio timeline, sampled at every finalized chunk.

    Chunk `start` values are elapsed audio on the capture host clock. That clock stops while the Mac sleeps, and
    a relaunched helper splices its own timeline onto the last finalized chunk (`--start-offset`), so the retire
    grace and the relaunch wait are compressed out of it as well. Every journal line also carries the wall clock
    it was written on, so the difference between the two clocks is measured here, not inferred from event counts.

    Returns (origin_wall, [(wall_elapsed, drift)]) in journal order. A journal from a build that did not stamp
    `wall`, or one that does not begin with its own `started` line, returns (None, []) — then nothing is
    corrected and markers stay exactly as the app wrote them."""
    try: lines=(Path(capture_dir)/journal).read_text(encoding='utf-8',errors='replace').splitlines()
    except OSError: return None,[]
    origin=None;base=None;out=[]
    for line in lines:
        try: event=json.loads(line)
        except ValueError: continue
        if not isinstance(event,dict): continue
        wall=event.get('wall')
        stamped=type(wall) in (int,float) and math.isfinite(wall)
        if origin is None:
            # The first line of a capture folder is the first helper's `started`; a relaunched helper appends to
            # the same file, so this stays the origin of the one meeting even across relaunches. A journal that
            # opens any other way (an older build, a helper that died before starting) is not measurable.
            if not stamped or event.get('event')!='started': return None,[]
            origin=float(wall);continue
        if not stamped: continue
        if event.get('event')!='chunk': continue
        start,duration=event.get('start'),event.get('duration')
        if type(start) not in (int,float) or type(duration) not in (int,float): continue
        if not (math.isfinite(start) and math.isfinite(duration)): continue
        measured=(float(wall)-origin)-(float(start)+float(duration))
        # The audio timeline's origin is set before `started` reaches the journal, and a chunk is announced a
        # moment after its last sample: the first chunk carries both constants, so it is the zero of the curve.
        if base is None: base=measured
        out.append((float(wall)-origin,max(0.0,measured-base)))
    return origin,out


def drift_before(samples, seconds):
    """Drift accumulated by the time the wall clock read `seconds`. Each chunk is an independent measurement, so
    a single slow fsync moves one marker slightly instead of poisoning every later one."""
    value=0.0
    for wall_elapsed,drift in samples:
        if wall_elapsed>seconds: break
        value=drift
    return round(value,1) if value>=MARKER_DRIFT_FLOOR else 0.0


def read_markers(capture_dir, limit=200):
    """Moments the user marked with ⌘M while recording: {seconds, kind, created}. The app stamps them on the wall
    clock; the transcript runs on the audio timeline, which sleep freezes and a relaunch splices. The measured
    difference is subtracted here, so a marker pressed after a five-minute lid-close still lands on the sentence
    it was meant for instead of five minutes past it. `wall_seconds` keeps the uncorrected value when it moved."""
    path=Path(capture_dir)/'markers.jsonl'
    if not path.is_file(): return []
    origin,samples=wall_audio_drift(capture_dir)
    out=[]
    for line in path.read_text(encoding='utf-8').splitlines()[:limit]:
        try: d=json.loads(line)
        except ValueError: continue
        secs=d.get('seconds');kind=d.get('kind')
        if isinstance(secs,(int,float)) and math.isfinite(secs) and secs>=0 and kind in ('important','decision','task','later'):
            wall=round(float(secs),1)
            # `seconds` counts from the app's record start; the drift curve counts from the helper's. When the
            # marker carries its absolute moment, both are put on the helper's origin first.
            stamp=d.get('wall')
            if origin is not None and type(stamp) in (int,float) and math.isfinite(stamp) and stamp>=origin: wall=round(float(stamp)-origin,1)
            shift=drift_before(samples,wall)
            marker={'seconds':round(max(0.0,wall-shift),1),'kind':kind,'created':d.get('created')}
            if shift: marker['wall_seconds']=wall
            out.append(marker)
    return out


MIC_GATE_MIN_OVERLAP = 1.0   # a piece that touches an open gate for less than a second is room noise, not the meeting


def mic_gate_windows(capture_dir):
    """The spans of the recording during which the owner's microphone counted as meeting audio.

    Boran, 11 Eyl 2026: "Mikrofondan gelen her sesi almak yerine sadece toplantıda unmute edince … alsın."
    The app journals one `mic_gate` line per state change — the first at second zero — and this turns them
    into [start,end) windows on the audio timeline. `None` means the recording carries no gate at all (it was
    made before the gate existed, or the journal is unreadable): then nothing is skipped and the whole
    microphone track is transcribed exactly as before.

    The app stamps `t` on its own record start and the transcript runs on the capture helper's audio clock,
    which sleep freezes and a relaunch splices — the same two clocks `read_markers` reconciles, with the same
    measured correction, so a gate opened after a five-minute lid-close does not open five minutes late."""
    try: from .audio import gate_events
    except Exception: return None
    try: events=gate_events(capture_dir)
    except OSError: return None
    if not events: return None
    origin,samples=wall_audio_drift(capture_dir)
    stamped=[]
    for e in events:
        state=e.get('state')
        if state not in ('on','off'): continue
        t=e.get('t')
        if type(t) not in (int,float) or isinstance(t,bool) or not math.isfinite(t) or t<0: continue
        wall=round(float(t),1)
        mark=e.get('wall')
        if origin is not None and type(mark) in (int,float) and math.isfinite(mark) and mark>=origin: wall=round(float(mark)-origin,1)
        stamped.append((max(0.0,round(wall-drift_before(samples,wall),1)),state))
    if not stamped: return None
    stamped.sort(key=lambda pair:pair[0])   # ties keep the order they were written in
    windows=[];open_at=None
    for seconds,state in stamped:
        if state=='on':
            if open_at is None: open_at=seconds
        elif open_at is not None:
            if seconds>open_at: windows.append((open_at,seconds))
            open_at=None
    if open_at is not None: windows.append((open_at,math.inf))   # the gate was still open when the recording ended
    return windows


def gate_overlap(windows, start, end):
    """Seconds of [start,end) that fall inside an open gate."""
    if windows is None: return max(0.0,float(end)-float(start))
    total=0.0
    for a,b in windows:
        low=max(float(start),a);high=min(float(end),b)
        if high>low: total+=high-low
    return total


def compact_capture(store, mid):
    """After a cloud transcript is complete the assembled *-full.wav files carry everything playback and
    identity need; the 12-second capture chunks (48 kHz float, several times larger) are removed. The
    journal stays so the capture history remains readable. Returns bytes freed."""
    row=store.db.execute('SELECT status,metadata FROM meetings WHERE id=?',(mid,)).fetchone()
    if not row: return 0
    meta=json.loads(row['metadata'] or '{}');capture=meta.get('capture_dir');paths=meta.get('paths') or {}
    if not capture or meta.get('cloud_mode')!='capture': return 0
    directory=Path(capture)
    freed=0;removed=0;stale=0
    def record():
        if stale: meta['stale_temporaries_removed']=meta.get('stale_temporaries_removed',0)+stale
        if removed: meta['chunks_removed']=removed;meta['chunks_freed_bytes']=freed
        if removed or stale:
            with store.db: store.db.execute('UPDATE meetings SET metadata=? WHERE id=?',(json.dumps(meta),mid))
        return freed
    # Orphan `*-full.wav.tmp` / `*-full.flac.tmp`: an assembler or an archiver that was killed mid-write. They
    # are never adopted, nothing else sweeps them, and they are the size of the recording. An hour of grace
    # keeps this away from anything still being written. This runs BEFORE every other test in this function:
    # the meetings that leave such a file behind are exactly the ones that never reach `complete`, and the
    # sweep used to be unreachable for them.
    import time
    from .audio import TEMPORARY_GRACE_SECONDS
    for pattern in ('*-full.wav.tmp','*-full.flac.tmp'):
        for orphan in directory.glob(pattern):
            try:
                if time.time()-orphan.stat().st_mtime<TEMPORARY_GRACE_SECONDS: continue
                freed+=orphan.stat().st_size;orphan.unlink();stale+=1
            except OSError: pass
    if row['status']!='complete': return record()
    full={k:Path(v) for k,v in paths.items() if isinstance(v,str)}
    if not full or not all(f.is_file() and f.stat().st_size>0 for f in full.values()): return record()
    # Both requested sources or nothing: the chunks are the only way back if one channel never got assembled.
    from .audio import journal_source_ends
    expected=journal_source_ends(directory)
    if expected and set(expected)-set(full): return record()
    # `*.partial.wav` is a chunk the helper was still writing when it was killed. It never announced a chunk
    # event, so the assembler skipped it and those seconds are NOT in *-full.wav — but neither is the file
    # usable, nothing else ever sweeps it, and it stayed on disk for the life of the meeting.
    for pattern in ('*-[0-9][0-9][0-9][0-9][0-9][0-9].wav','*-[0-9][0-9][0-9][0-9][0-9][0-9].partial.wav'):
        for chunk in directory.glob(pattern):
            if chunk.resolve() in {f.resolve() for f in full.values()}: continue
            try: freed+=chunk.stat().st_size;chunk.unlink();removed+=1
            except OSError: pass
    return record()


def finalize_capture(store, mid, data_dir, *, consent=False, model=None, client=None, ffmpeg=None, embedder=None):
    """Capture-directory recordings and cloud-only file imports share this resumable path."""
    _consent(consent)
    import time; job_started=time.monotonic()
    row=store.db.execute('SELECT * FROM meetings WHERE id=?',(mid,)).fetchone()
    if not row: raise ValueError('Toplantı bulunamadı')
    from .recovery import classify, current_job_metadata, metadata as read_metadata
    metadata=read_metadata(row)
    mode=metadata.get('cloud_mode')
    if row['status']=='complete' and mode in ('capture','file'): return {'meeting':mid,'segments':len(store.segments(mid)),'model':metadata.get('model')}
    if row['status'] in ('processing','provisional') and classify(metadata.get('worker_identity'))=='active': raise ValueError('Bu toplantı üzerinde iş sürüyor; önce durdurun')
    capture=metadata.get('capture_dir')
    if mode!='file' and (not capture or not Path(capture).is_dir()): raise ValueError('Bu toplantının ses kaydı klasörü yok')
    stored=metadata.get('model') if mode in ('capture','file') else None
    if stored and model and model!=stored: raise ValueError('Devam ederken model değiştirilemez; bu kayıt '+stored+' ile başladı')
    model=validate_stt_model(model or stored or STT_MODEL)
    client=client or OpenRouterClient(max_audio_bytes=MAX_PIECE_BYTES)  # missing key fails before any file work
    data_dir=Path(data_dir);data_dir.mkdir(parents=True,exist_ok=True)
    with (data_dir/'openrouter-job.lock').open('a') as lock:
        try: fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError: raise ValueError('Bir OpenRouter işlemi zaten çalışıyor') from None
        if mode=='file':
            sources={k:v for k,v in (metadata.get('paths') or {}).items() if isinstance(v,str) and Path(v).is_file()}
            if not sources: raise ValueError('İçe aktarılan ses dosyası bulunamadı')
        else:
            directory=Path(capture).resolve()
            from .audio import adoptable_full_files, assemble_capture
            # Only adopt what an earlier run really finished: every source the journal recorded, each as long as
            # the journal says. A half-written file used to be adopted whole, the chunks were then compacted
            # away, and the meeting was transcribed from the fragment that survived.
            try:
                sources=adoptable_full_files(directory)
                if not sources:
                    emit('assembling')
                    sources=assemble_capture(directory)
            except OSError as exc:
                # Assembly runs before the attempt is opened, so a full disk would otherwise leave no error line
                # at all and the idle queue would come straight back. Say what is wrong, wait, spend nothing.
                if not is_disk_full(exc): raise
                store.status(mid,'incomplete');note_cloud_failure(store,mid,exc);raise
        if not mode:
            with store.db: store.db.execute('DELETE FROM segments WHERE meeting=?',(mid,))  # provisional live text is replaced by the cloud transcript
        metadata.update({'engine':'openrouter','model':model,'cloud_mode':mode or 'capture','cloud_upload_authorized':True,'paths':sources,'provisional':False})
        metadata.pop('cloud_error',None);metadata.pop('cloud_retry_after',None);metadata.pop('cloud_canceled',None)   # an attempt is under way; the old verdict is stale
        metadata['cloud_retry_attempt']=next_attempt(metadata);metadata['cloud_attempt_open']=True   # spent now, so a kill still counts against MAX_CLOUD_RETRIES
        if capture and mode!='file': metadata['markers']=read_markers(capture)
        metadata.update(current_job_metadata())
        with store.db: store.db.execute('UPDATE meetings SET status=?,metadata=? WHERE id=?',('processing',json.dumps(metadata),mid))
        try:
            from .glossary import load as load_glossary, ranked_hint, candidates as glossary_candidates
            glossary,from_file=load_glossary(data_dir,Path(__file__).resolve().parents[1],with_counts=True,store=store)   # the hint carries the team's taught spellings too
            # Same 900 characters, spent on the words that actually go wrong: repeat offenders first, then what
            # was taught here lately, what the user has confirmed, the team's words, the glossary, the
            # vocabulary (Codex #7). What fitted and how much did not is recorded, here and in the report.
            ranked=ranked_hint(store,glossary,data_dir=data_dir,from_file=from_file) if glossary else None
            metadata['hint_included']=(ranked or {}).get('included') or []
            metadata['hint_excluded']=(ranked or {}).get('excluded') or 0
            from .reports import settings_owner
            mic_windows=mic_gate_windows(capture) if (capture and mode!='file') else None
            transcribe_sources(store,mid,sources,client,consent=True,model=model,ffmpeg=ffmpeg,hint=(ranked or {}).get('hint') or None,owner=settings_owner(data_dir),mic_windows=mic_windows)
            metadata['echo_segments']=flag_echo(store,mid)
            metadata['glossary_suggestions']=glossary_candidates(store.segments(mid),glossary)[:80] if glossary else []   # free local pass; LLM refinement is on demand
            usages=[u or '' for (u,) in store.db.execute('SELECT usage FROM cloud_chunks WHERE meeting=?',(mid,))]
            metadata['echo_windows_skipped']=sum(1 for u in usages if 'skipped' in u and 'mic_gated' not in u)
            metadata['mic_gated_windows']=sum(1 for u in usages if 'mic_gated' in u)   # what the mic gate saved: never uploaded, never paid for
            metadata['job_usage']=job_usage(job_started)
            metadata.pop('cloud_error',None);metadata.pop('cloud_retry_after',None);metadata.pop('cloud_retry_attempt',None);metadata.pop('cloud_attempt_open',None)   # it worked: nothing left to retry
            try:
                identity=identify_clusters(store,mid,sources,embedder)
                metadata['identity']=identity;metadata.pop('identity_error',None)
            except Exception as exc:  # voice matching is optional; the cloud transcript stands on its own
                from .resources import MemoryPressureError, ResourceProbeError
                metadata['identity_error']='Bellek baskısı; ses profili eşleştirmesi atlandı' if isinstance(exc,(MemoryPressureError,ResourceProbeError)) else 'Ses profili eşleştirmesi yapılamadı'
            with store.db: store.db.execute('UPDATE meetings SET metadata=? WHERE id=?',(json.dumps(metadata),mid))
            store.status(mid,'complete');emit('complete')
            compact_capture(store,mid)
            from .audio_archive import archive_meeting
            archive_meeting(store,mid)   # float32 WAV → 16-bit FLAC, lossless, 3–4× smaller
            from .reports import write_meeting_report
            from . import __version__
            write_meeting_report(store,mid,data_dir,version=__version__)
            return {'meeting':mid,'segments':len(store.segments(mid)),'model':model,'sources':sorted(sources),
                    'hint_included':metadata['hint_included'],'hint_excluded':metadata['hint_excluded']}
        except BaseException as exc:
            store.status(mid,'incomplete')
            # A deliberate stop (⌘. / quit) is not a cloud failure and must not schedule an unwanted retry.
            if isinstance(exc,Exception): note_cloud_failure(store,mid,exc)
            else: note_cloud_cancel(store,mid)   # KeyboardInterrupt/SystemExit: the user's decision, not a retryable failure
            raise
