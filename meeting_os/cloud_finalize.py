"""Finalize a recorded capture through OpenRouter only: no local STT, diarization or identity models.

Audio assembly is plain file I/O. Each source (mic / system) is encoded with ffmpeg into bounded
Opus pieces and sent to the selected OpenRouter model; diarization-capable models return
speaker-labelled segments. Every finished piece is checkpointed with its transcript in one
transaction, so an interrupted job resumes without re-uploading finished pieces.
"""
import contextlib
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
from .reports import DEFAULT_USER_NAME
SOURCE_LABELS = {'mic':DEFAULT_USER_NAME,'system':'Karşı taraf'}   # 'mic' is only the fallback for databases recorded before the user_name setting; source_labels() is what jobs use


def source_labels(owner=None):
    """Mic audio is always the person who owns this Mac. The name is read from settings once per job, never per segment."""
    return {**SOURCE_LABELS,'mic':owner.strip()} if isinstance(owner,str) and owner.strip() else dict(SOURCE_LABELS)
RETRY_WAITS = (2,8,20)        # a rate limit or a 5xx usually clears in seconds; 30 s of waiting is cheaper than losing the batch
RETRY_JITTER = 0.25           # three workers that failed together must not come back in lockstep
BACKOFF_MINUTES = (10,30,120,360)   # idle-retry spacing after a failed job; every 24 h from then on
MAX_CLOUD_RETRIES = 30        # the queue stops asking after this; the audio is still never deleted


def backoff_minutes(attempt):
    """How long the idle queue waits before offering this meeting again. 1-based attempt count."""
    return BACKOFF_MINUTES[attempt-1] if 1<=attempt<=len(BACKOFF_MINUTES) else 24*60


def note_cloud_failure(store, mid, exc):
    """Remember why the cloud refused this meeting, and when it is worth asking again. Nothing about the
    audio or the finished pieces changes: this is the one line the sidebar shows and the idle queue reads."""
    from datetime import datetime, timedelta, timezone
    row=store.db.execute('SELECT metadata FROM meetings WHERE id=?',(mid,)).fetchone()
    if not row: return None
    meta=json.loads(row['metadata'] or '{}')
    previous=meta.get('cloud_retry_attempt')
    attempt=min((previous if isinstance(previous,int) and not isinstance(previous,bool) and previous>0 else 0)+1,MAX_CLOUD_RETRIES)
    now=datetime.now(timezone.utc)
    meta['cloud_error']={'kind':error_kind(exc),'message':error_message(exc),'at':now.isoformat()}
    meta['cloud_retry_attempt']=attempt
    meta['cloud_retry_after']=(now+timedelta(minutes=backoff_minutes(attempt))).isoformat()
    with store.db: store.db.execute('UPDATE meetings SET metadata=? WHERE id=?',(json.dumps(meta,ensure_ascii=False),mid))
    return meta['cloud_error']


def pieces(duration, length):
    if not math.isfinite(duration) or duration<=0: raise ValueError('Ses süresi geçersiz')
    result=[];start=0.0
    while start<duration:
        end=min(start+length,duration);result.append((start,end));start=end
    if len(result)>10000: raise ValueError('Çok fazla ses parçası')
    return result


ECHO_HOP=800            # 50 ms RMS envelope
ECHO_THRESHOLD=0.5      # measured: speaker bleed 0.72–0.88, unrelated speech 0.07

def _envelope(x):
    n=len(x)//ECHO_HOP
    if n==0: return np.zeros(0,dtype='float32')
    return np.sqrt((x[:n*ECHO_HOP].reshape(n,ECHO_HOP)**2).mean(axis=1))

def envelope_correlation(mic, system, max_lag=20):
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
    """One piece at a time while a Zoom meeting is on screen: the app sets the env flag at launch and, for a job
    that is already running when the next meeting opens, drops a flag file we re-check before every batch."""
    if os.environ.get('MEETING_OS_LOW_PRIORITY'): return 1
    flag=os.environ.get('MEETING_OS_LOW_PRIORITY_FLAG')
    return 1 if flag and os.path.exists(flag) else UPLOAD_WORKERS


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


def transcribe_sources(store, mid, sources, client, *, consent=False, model=STT_MODEL, ffmpeg=None, hint=None, owner=None):
    """sources: {'mic': path, 'system': path} of 16 kHz mono files. Returns the plan."""
    _consent(consent);validate_stt_model(model)
    labels=source_labels(owner)
    diarize=diarization_options(model) is not None
    length=PIECE_SECONDS if diarize else FINE_PIECE_SECONDS
    plan=[]
    for source in sorted(sources):
        info=sf.info(sources[source])
        if info.samplerate!=16000 or info.channels!=1 or not 0<info.duration<=14400: raise ValueError('Ses mono 16 kHz ve en fazla dört saat olmalı')
        piece_length=FINE_PIECE_SECONDS if source=='mic' else length   # the mic is never diarized; short windows let echo be skipped per window
        for index,(a,b) in enumerate(pieces(info.duration,piece_length)): plan.append((source,a,b,index))
    counts={s:sum(1 for p in plan if p[0]==s) for s in sources}
    signature=digest_files([sources[s] for s in sorted(sources)])
    store.db.executescript('''CREATE TABLE IF NOT EXISTS cloud_sources(meeting TEXT PRIMARY KEY REFERENCES meetings(id), digest TEXT, plan TEXT);
        CREATE TABLE IF NOT EXISTS cloud_chunks(meeting TEXT REFERENCES meetings(id), position INTEGER, usage TEXT, PRIMARY KEY(meeting,position));''')
    if 'model' not in {r[1] for r in store.db.execute('PRAGMA table_info(cloud_sources)')}:
        with store.db:store.db.execute("ALTER TABLE cloud_sources ADD COLUMN model TEXT NOT NULL DEFAULT 'openai/gpt-transcribe'")
    plan_json=json.dumps(plan)
    old=store.db.execute('SELECT * FROM cloud_sources WHERE meeting=?',(mid,)).fetchone()
    if old and (old['digest']!=signature or old['plan']!=plan_json or old['model']!=model):
        paid=[u for (u,) in store.db.execute('SELECT usage FROM cloud_chunks WHERE meeting=?',(mid,)) if u and ('"cost"' in u or '"seconds"' in u)]  # silent/echo windows cost nothing
        if paid or old['digest']!=signature or old['model']!=model: raise ValueError('Kaynak ses veya plan değişti; devam edilmedi')
        with store.db:  # only free (skipped) checkpoints exist: adopt the new piece plan without losing anything
            store.db.execute('DELETE FROM cloud_chunks WHERE meeting=?',(mid,));store.db.execute('UPDATE cloud_sources SET plan=? WHERE meeting=?',(plan_json,mid))
        old=store.db.execute('SELECT * FROM cloud_sources WHERE meeting=?',(mid,)).fetchone()
    if not old:
        with store.db:store.db.execute('INSERT INTO cloud_sources(meeting,digest,plan,model) VALUES(?,?,?,?)',(mid,signature,plan_json,model))
    done={r[0] for r in store.db.execute('SELECT position FROM cloud_chunks WHERE meeting=?',(mid,))}
    def prepare(position):
        """Main-thread decision per piece: skip (echo/silent) or hand encoded audio to an upload worker."""
        source,a,b,index=plan[position];path=sources[source]
        if source=='mic' and 'system' in sources and not is_silent(path,a,b) and is_echo(path,sources['system'],a,b): return ('skip',{'skipped':'echo'})
        if is_silent(path,a,b): return ('skip',{'skipped':'silent'})
        audio=encode_piece(path,a,b,ffmpeg)
        if len(audio)>MAX_PIECE_BYTES: raise ValueError('Ses parçası yükleme sınırını aşıyor')
        return ('upload',audio)
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
    import random, time
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=UPLOAD_WORKERS) as pool:
        def send(positions,encoded):
            """Upload these pieces, never more than upload_workers() at a time (re-read so a meeting that opens
            mid-job slows the next slice down). Every paid success is checkpointed even when a sibling fails."""
            nonlocal finished
            failures={};queue=list(positions)
            while queue:
                slice_=queue[:max(1,upload_workers())];queue=queue[len(slice_):]
                futures={i:pool.submit(client.transcribe,encoded[i],'ogg',model=model,consent=True,
                    diarize=diarize and plan[i][0]!='mic',timeout=REQUEST_TIMEOUT,hint=hint) for i in slice_}
                for position in sorted(futures):
                    try: result=futures[position].result()
                    except Exception as exc: failures[position]=exc;continue
                    commit(position,result['usage'],result);finished+=1
            return failures
        start=0
        while start<len(pending):
            workers=upload_workers()   # re-read per batch: a meeting may start mid-job
            batch=pending[start:start+workers]; start+=workers
            emit('transcribing',finished,len(plan),'OpenRouter')
            encoded={}
            for position in batch:
                kind,payload=prepare(position)
                if kind=='skip': commit(position,payload,None);finished+=1;continue
                encoded[position]=payload
            attempt=0;waiting=sorted(encoded)
            while waiting:
                failures=send(waiting,encoded)
                if not failures: break
                # An invalid key or an empty balance cannot be fixed by asking again; a timeout or a 5xx often can.
                fatal=next((e for e in failures.values() if not getattr(e,'retryable',False)),None)
                if fatal is not None or attempt>=len(RETRY_WAITS): raise fatal or failures[min(failures)]
                wait=RETRY_WAITS[attempt]
                emit('transcribing',finished,len(plan),f'OpenRouter · yeniden deneme {attempt+1}/{len(RETRY_WAITS)}')
                time.sleep(wait+random.uniform(0,wait*RETRY_JITTER))
                attempt+=1;waiting=sorted(failures)
    emit('transcribing',len(plan),len(plan),'OpenRouter')
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
    for (source,speaker),members in speakers.items():
        centroid=linked_centroid(members,embedder.model_id)
        if centroid is None: continue
        scored.append((members,store.identify(centroid,embedder.model_id,IDENTITY_THRESHOLD,IDENTITY_MARGIN),centroid))
    assignment=assign_identities([(members,identity) for members,identity,_ in scored])
    suggested=0;fed=0
    for members,identity,centroid in scored:
        name=assignment.get(id(members))
        sim=identity.get('similarity') or 0;gap=identity.get('margin') or 0
        suggestion=identity.get('candidate') if (not name and sim>=SUGGEST_THRESHOLD and gap>=IDENTITY_MARGIN) else None
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


def read_markers(capture_dir, limit=200):
    """Moments the user marked with ⌘M while recording: {seconds, kind, created}. Written by the app, read once here."""
    path=Path(capture_dir)/'markers.jsonl'
    if not path.is_file(): return []
    out=[]
    for line in path.read_text(encoding='utf-8').splitlines()[:limit]:
        try: d=json.loads(line)
        except ValueError: continue
        secs=d.get('seconds');kind=d.get('kind')
        if isinstance(secs,(int,float)) and math.isfinite(secs) and secs>=0 and kind in ('important','decision','task','later'):
            out.append({'seconds':round(float(secs),1),'kind':kind,'created':d.get('created')})
    return out


def compact_capture(store, mid):
    """After a cloud transcript is complete the assembled *-full.wav files carry everything playback and
    identity need; the 12-second capture chunks (48 kHz float, several times larger) are removed. The
    journal stays so the capture history remains readable. Returns bytes freed."""
    row=store.db.execute('SELECT status,metadata FROM meetings WHERE id=?',(mid,)).fetchone()
    if not row or row['status']!='complete': return 0
    meta=json.loads(row['metadata'] or '{}');capture=meta.get('capture_dir');paths=meta.get('paths') or {}
    if not capture or meta.get('cloud_mode')!='capture': return 0
    directory=Path(capture)
    full={k:Path(v) for k,v in paths.items() if isinstance(v,str)}
    if not full or not all(f.is_file() and f.stat().st_size>0 for f in full.values()): return 0
    freed=0;removed=0
    for chunk in directory.glob('*-[0-9][0-9][0-9][0-9][0-9][0-9].wav'):
        if chunk.resolve() in {f.resolve() for f in full.values()}: continue
        try: freed+=chunk.stat().st_size;chunk.unlink();removed+=1
        except OSError: pass
    if removed:
        meta['chunks_removed']=removed;meta['chunks_freed_bytes']=freed
        with store.db: store.db.execute('UPDATE meetings SET metadata=? WHERE id=?',(json.dumps(meta),mid))
    return freed


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
            existing={s:str(directory/f'{s}-full.wav') for s in ('mic','system') if (directory/f'{s}-full.wav').is_file()}
            if existing: sources=existing
            else:
                emit('assembling')
                from .audio import assemble_capture
                sources=assemble_capture(directory)
        if not mode:
            with store.db: store.db.execute('DELETE FROM segments WHERE meeting=?',(mid,))  # provisional live text is replaced by the cloud transcript
        metadata.update({'engine':'openrouter','model':model,'cloud_mode':mode or 'capture','cloud_upload_authorized':True,'paths':sources,'provisional':False})
        metadata.pop('cloud_error',None);metadata.pop('cloud_retry_after',None)   # an attempt is under way; the old verdict is stale
        if capture and mode!='file': metadata['markers']=read_markers(capture)
        metadata.update(current_job_metadata())
        with store.db: store.db.execute('UPDATE meetings SET status=?,metadata=? WHERE id=?',('processing',json.dumps(metadata),mid))
        try:
            from .glossary import load as load_glossary, stt_hint, candidates as glossary_candidates
            glossary=load_glossary(data_dir,Path(__file__).resolve().parents[1])
            from .reports import settings_owner
            transcribe_sources(store,mid,sources,client,consent=True,model=model,ffmpeg=ffmpeg,hint=stt_hint(glossary) if glossary else None,owner=settings_owner(data_dir))
            metadata['echo_segments']=flag_echo(store,mid)
            metadata['glossary_suggestions']=glossary_candidates(store.segments(mid),glossary)[:80] if glossary else []   # free local pass; LLM refinement is on demand
            metadata['echo_windows_skipped']=sum(1 for (u,) in store.db.execute('SELECT usage FROM cloud_chunks WHERE meeting=?',(mid,)) if 'skipped' in (u or ''))
            metadata['job_usage']=job_usage(job_started)
            metadata.pop('cloud_error',None);metadata.pop('cloud_retry_after',None);metadata.pop('cloud_retry_attempt',None)   # it worked: nothing left to retry
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
            return {'meeting':mid,'segments':len(store.segments(mid)),'model':model,'sources':sorted(sources)}
        except BaseException as exc:
            store.status(mid,'incomplete')
            # A deliberate stop (⌘. / quit) is not a cloud failure and must not schedule an unwanted retry.
            if isinstance(exc,Exception): note_cloud_failure(store,mid,exc)
            raise
