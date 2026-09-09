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
            provider_segments=result.get('segments') or []
            if provider_segments:
                for seg in provider_segments:
                    if not seg['text']: continue
                    label=speaker_label(source,seg['speaker'],index,multi)
                    segments.append(Segment(a+seg['start'],min(a+seg['end'],b),seg['text'],source,label,
                        metrics={'provider':'openrouter','model':model,'piece':index},flags=flags+(['cloud_diarization'] if source!='mic' else [])))
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


def import_file_cloud_only(store, path, title, data_dir, *, consent=False, model=None, client=None, ffmpeg=None):
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
    return finalize_capture(store,mid,data_dir,consent=True,model=model,client=client,ffmpeg=ffmpeg)


def finalize_capture(store, mid, data_dir, *, consent=False, model=None, client=None, ffmpeg=None):
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
            store.status(mid,'complete');emit('complete')
            return {'meeting':mid,'segments':len(store.segments(mid)),'model':model,'sources':sorted(sources)}
        except BaseException:
            store.status(mid,'incomplete');raise
