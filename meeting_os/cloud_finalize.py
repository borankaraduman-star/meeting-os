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
from .openrouter import OpenRouterClient, STT_MODEL, _consent, validate_stt_model, diarization_options
from .progress import emit
from .types import Segment

PIECE_SECONDS = 1200          # one request per ≤20 minutes keeps provider speaker labels consistent inside a piece
FINE_PIECE_SECONDS = 30       # models without diarization get short windows so timing stays useful
MAX_PIECE_BYTES = 24*1024*1024
REQUEST_TIMEOUT = 600
SOURCE_LABELS = {'mic':'Boran','system':'Karşı taraf'}


def pieces(duration, length):
    if not math.isfinite(duration) or duration<=0: raise ValueError('Ses süresi geçersiz')
    result=[];start=0.0
    while start<duration:
        end=min(start+length,duration);result.append((start,end));start=end
    if len(result)>10000: raise ValueError('Çok fazla ses parçası')
    return result


def is_silent(path, start, end, threshold=1e-4):
    with sf.SoundFile(path) as f:
        f.seek(round(start*f.samplerate));remaining=round((end-start)*f.samplerate)
        while remaining>0:
            block=f.read(min(remaining,f.samplerate*10),dtype='float32')
            if not len(block): break
            if np.abs(block).max()>threshold: return False
            remaining-=len(block)
    return True


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
    """A microphone segment whose words largely repeat the system audio of the same interval is speaker bleed, not Boran."""
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


def speaker_label(source, provider_speaker, piece_index, multi_piece):
    if source=='mic' or provider_speaker is None: return SOURCE_LABELS.get(source,source)
    try: number=int(provider_speaker)+1
    except ValueError: number=provider_speaker
    return f'Konuşmacı {piece_index+1}-{number}' if multi_piece else f'Konuşmacı {number}'


def transcribe_sources(store, mid, sources, client, *, consent=False, model=STT_MODEL, ffmpeg=None):
    """sources: {'mic': path, 'system': path} of 16 kHz mono files. Returns the plan."""
    _consent(consent);validate_stt_model(model)
    diarize=diarization_options(model) is not None
    length=PIECE_SECONDS if diarize else FINE_PIECE_SECONDS
    plan=[]
    for source in sorted(sources):
        info=sf.info(sources[source])
        if info.samplerate!=16000 or info.channels!=1 or not 0<info.duration<=14400: raise ValueError('Ses mono 16 kHz ve en fazla dört saat olmalı')
        for index,(a,b) in enumerate(pieces(info.duration,length)): plan.append((source,a,b,index))
    counts={s:sum(1 for p in plan if p[0]==s) for s in sources}
    signature=digest_files([sources[s] for s in sorted(sources)])
    store.db.executescript('''CREATE TABLE IF NOT EXISTS cloud_sources(meeting TEXT PRIMARY KEY REFERENCES meetings(id), digest TEXT, plan TEXT);
        CREATE TABLE IF NOT EXISTS cloud_chunks(meeting TEXT REFERENCES meetings(id), position INTEGER, usage TEXT, PRIMARY KEY(meeting,position));''')
    if 'model' not in {r[1] for r in store.db.execute('PRAGMA table_info(cloud_sources)')}:
        with store.db:store.db.execute("ALTER TABLE cloud_sources ADD COLUMN model TEXT NOT NULL DEFAULT 'openai/gpt-transcribe'")
    plan_json=json.dumps(plan)
    old=store.db.execute('SELECT * FROM cloud_sources WHERE meeting=?',(mid,)).fetchone()
    if old and (old['digest']!=signature or old['plan']!=plan_json or old['model']!=model): raise ValueError('Kaynak ses veya plan değişti; devam edilmedi')
    if not old:
        with store.db:store.db.execute('INSERT INTO cloud_sources(meeting,digest,plan,model) VALUES(?,?,?,?)',(mid,signature,plan_json,model))
    done={r[0] for r in store.db.execute('SELECT position FROM cloud_chunks WHERE meeting=?',(mid,))}
    for position,(source,a,b,index) in enumerate(plan):
        emit('transcribing',position,len(plan),'OpenRouter')
        if position in done: continue
        path=sources[source]
        segments=[];usage={}
        if not is_silent(path,a,b):
            audio=encode_piece(path,a,b,ffmpeg)
            if len(audio)>MAX_PIECE_BYTES: raise ValueError('Ses parçası yükleme sınırını aşıyor')
            result=client.transcribe(audio,'ogg',model=model,consent=True,diarize=diarize and source!='mic',timeout=REQUEST_TIMEOUT)
            usage=result['usage']
            flags=['cloud_transcript','confidence_unavailable','speaker_unverified']
            multi=counts[source]>1
            provider_segments=merge_segments(result.get('segments') or [])
            if provider_segments:
                for seg in provider_segments:
                    label=speaker_label(source,seg['speaker'],index,multi)
                    segments.append(Segment(a+seg['start'],min(a+seg['end'],b),seg['text'],source,label,
                        metrics={'provider':'openrouter','model':model,'piece':index,'cluster':f'{index}:{seg["speaker"]}'},flags=flags+(['cloud_diarization'] if source!='mic' else [])))
            elif result['text'].strip():
                segments.append(Segment(a,b,result['text'].strip(),source,SOURCE_LABELS.get(source,source),
                    metrics={'provider':'openrouter','model':model,'piece':index,'usage':usage},flags=flags+['coarse_timing']))
        with store.db:  # transcript and checkpoint land together or not at all
            for segment in segments:
                d=segment.to_dict()
                store.db.execute('INSERT INTO segments(meeting,start,end,source,speaker,speaker_name,payload) VALUES(?,?,?,?,?,?,?)',
                    (mid,segment.start,segment.end,source,segment.speaker,None,json.dumps(d,ensure_ascii=False)))
            store.db.execute('INSERT INTO cloud_chunks VALUES(?,?,?)',(mid,position,json.dumps(usage)))
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
    """Local, light voiceprint step: one vector per diarized segment, cluster centroid matched against saved profiles.
    Never blocks the transcript: caller records failures in metadata."""
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
    named=0
    clusters={}
    for r in store.segments(mid):
        key=(r['source'],(r.get('metrics') or {}).get('cluster'))
        if key[1] is not None: clusters.setdefault(key,[]).append(r)
    scored=[]
    for (source,cluster),members in clusters.items():
        vectors=[r['embedding'] for r in members if r.get('embedding') and r.get('embedding_model')==embedder.model_id]
        if not vectors: continue
        centroid=[sum(col)/len(vectors) for col in zip(*vectors)]
        scored.append((members,store.identify(centroid,embedder.model_id,IDENTITY_THRESHOLD,IDENTITY_MARGIN)))
    assignment=assign_identities(scored)
    suggested=0;fed=0
    for members,identity in scored:
        name=assignment.get(id(members))
        sim=identity.get('similarity') or 0;gap=identity.get('margin') or 0
        suggestion=identity.get('candidate') if (not name and sim>=SUGGEST_THRESHOLD and gap>=IDENTITY_MARGIN) else None
        for r in members:
            r.setdefault('metrics',{})['identity']={**identity,'name':name,'suggested':suggestion}
            with store.db: store.db.execute('UPDATE segments SET speaker_name=?,payload=? WHERE id=? AND meeting=?',(name,json.dumps(r,ensure_ascii=False),r['id'],mid))
        if name: named+=len(members)
        if suggestion: suggested+=len(members)
        total=sum(r['end']-r['start'] for r in members)
        if name and sim>=FEED_THRESHOLD and gap>=FEED_MARGIN and total>=FEED_MIN_SECONDS:
            vectors=[r['embedding'] for r in members if r.get('embedding')]
            centroid=[sum(col)/len(vectors) for col in zip(*vectors)]
            cluster=(members[0].get('metrics') or {}).get('cluster')
            if store.add_sample_if_new(name,centroid,embedder.model_id,total,f'auto:{mid}:{cluster}',cap=MAX_AUTO_SAMPLES): fed+=1
    return {'embedded':embedded,'named':named,'suggested':suggested,'fed':fed}


CLUSTER_MIN_SECONDS=2.0   # concatenated back-channels; the embedder accepts ≥1 s, the margin rule guards weak vectors
CLUSTER_MAX_SECONDS=60.0

def embed_short_clusters(store, mid, sources, embedder):
    """Back-channel speakers (“hı hı”, “aynen”) never reach 3 s in one turn. Their cluster's pieces are
    concatenated into one private snapshot and embedded once, so the cluster can still be matched or enrolled."""
    import tempfile
    clusters={}
    for r in store.segments(mid):
        cl=(r.get('metrics') or {}).get('cluster')
        if cl is not None and 'cloud_diarization' in r['flags'] and r['source'] in sources: clusters.setdefault((r['source'],cl),[]).append(r)
    count=0
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
        audio=np.concatenate(pieces)
        with tempfile.TemporaryDirectory(prefix='meeting-os-cluster-') as tmp:
            snapshot=Path(tmp)/'cluster.wav';sf.write(snapshot,audio,16000,subtype='FLOAT')
            with contextlib.redirect_stdout(__import__('sys').stderr):
                vectors=embedder.embed_file(str(snapshot),[(0,len(audio))])
        vector=vectors[0] if vectors else None
        if vector is None: continue
        for r in members:
            r['embedding']=vector;r['embedding_model']=embedder.model_id;r.setdefault('metrics',{})['cluster_embedding']=round(kept,2)
            with store.db: store.db.execute('UPDATE segments SET payload=? WHERE id=? AND meeting=?',(json.dumps(r,ensure_ascii=False),r['id'],mid))
        count+=1
    return count


SUGGEST_THRESHOLD=0.83    # below the naming threshold but worth a one-click confirmation ("Sol Üst?")
FEED_THRESHOLD=0.93       # a match this strong adds one more sample to the profile automatically
FEED_MARGIN=0.10
FEED_MIN_SECONDS=10.0
MAX_AUTO_SAMPLES=8        # per person; manual samples count too
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


def finalize_capture(store, mid, data_dir, *, consent=False, model=None, client=None, ffmpeg=None, embedder=None):
    """Capture-directory recordings and cloud-only file imports share this resumable path."""
    _consent(consent)
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
        metadata.update(current_job_metadata())
        with store.db: store.db.execute('UPDATE meetings SET status=?,metadata=? WHERE id=?',('processing',json.dumps(metadata),mid))
        try:
            transcribe_sources(store,mid,sources,client,consent=True,model=model,ffmpeg=ffmpeg)
            metadata['echo_segments']=flag_echo(store,mid)
            try:
                identity=identify_clusters(store,mid,sources,embedder)
                metadata['identity']=identity;metadata.pop('identity_error',None)
            except Exception as exc:  # voice matching is optional; the cloud transcript stands on its own
                from .resources import MemoryPressureError, ResourceProbeError
                metadata['identity_error']='Bellek baskısı; ses profili eşleştirmesi atlandı' if isinstance(exc,(MemoryPressureError,ResourceProbeError)) else 'Ses profili eşleştirmesi yapılamadı'
            with store.db: store.db.execute('UPDATE meetings SET metadata=? WHERE id=?',(json.dumps(metadata),mid))
            store.status(mid,'complete');emit('complete')
            return {'meeting':mid,'segments':len(store.segments(mid)),'model':model,'sources':sorted(sources)}
        except BaseException:
            store.status(mid,'incomplete');raise
