"""Recorded-file GPT Transcribe import with local speakers and durable checkpoints."""
import contextlib
import hashlib
import io
import json
import math
from pathlib import Path
import shutil
import subprocess
import uuid

import soundfile as sf
from .openrouter import OpenRouterClient, STT_MODEL, _consent, validate_stt_model
from .progress import emit
from .types import Segment


def windows(turns, duration):
    clean=[]
    for a,b,s in turns:
        if not all(math.isfinite(x) for x in (a,b)) or not 0<=a<b<=duration+.01 or not isinstance(s,str):
            raise ValueError('Geçersiz konuşmacı zamanları')
        clean.append((a,min(b,duration),s))
    points=sorted({x for a,b,_ in clean for x in (a,b)})
    spans=[]
    for a,b in zip(points,points[1:]):
        active={s for x,y,s in clean if x<b and y>a}
        if not active:continue
        speaker=next(iter(active)) if len(active)==1 else 'unknown'
        if spans and spans[-1][2]==speaker and spans[-1][1]==a:spans[-1]=(spans[-1][0],b,speaker)
        else:spans.append((a,b,speaker))
    result=[]
    for a,b,speaker in spans:
        while a<b:
            end=min(a+30,b);result.append((a,end,speaker));a=end
    if len(result)>10000:raise ValueError('Çok fazla konuşma bölümü')
    return result


def digest_file(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
    return h.hexdigest()


def transcribe_prepared(store,mid,path,turns,client,*,consent=False,model=STT_MODEL):
    _consent(consent);validate_stt_model(model)
    info=sf.info(path)
    if info.samplerate!=16000 or info.channels!=1 or not 0<info.duration<=14400:
        raise ValueError('Ses mono 16 kHz ve en fazla dört saat olmalı')
    spans=windows(turns,info.duration)
    if not spans:raise ValueError('Konuşma bulunamadı; ses yüklenmedi')
    signature=digest_file(path)
    store.db.executescript('''CREATE TABLE IF NOT EXISTS cloud_sources(meeting TEXT PRIMARY KEY REFERENCES meetings(id), digest TEXT, plan TEXT);
        CREATE TABLE IF NOT EXISTS cloud_chunks(meeting TEXT REFERENCES meetings(id), position INTEGER, usage TEXT, PRIMARY KEY(meeting,position));''')
    if 'model' not in {r[1] for r in store.db.execute('PRAGMA table_info(cloud_sources)')}:
        with store.db:store.db.execute("ALTER TABLE cloud_sources ADD COLUMN model TEXT NOT NULL DEFAULT 'openai/gpt-transcribe'")
    plan=json.dumps(spans)
    old=store.db.execute('SELECT * FROM cloud_sources WHERE meeting=?',(mid,)).fetchone()
    if old and (old['digest']!=signature or old['plan']!=plan or old['model']!=model):raise ValueError('Kaynak ses veya konuşmacı planı değişti; devam edilmedi')
    if not old:
        with store.db:store.db.execute('INSERT INTO cloud_sources(meeting,digest,plan,model) VALUES(?,?,?,?)',(mid,signature,plan,model))
    done={r[0] for r in store.db.execute('SELECT position FROM cloud_chunks WHERE meeting=?',(mid,))}
    with sf.SoundFile(path) as f:
        for i,(a,b,speaker) in enumerate(spans):
            emit('transcribing',i,len(spans),'OpenRouter')
            if i in done:continue
            f.seek(round(a*16000));audio=f.read(round(b*16000)-round(a*16000),dtype='float32')
            if not len(audio):raise ValueError('Ses parçası boş')
            data=io.BytesIO();sf.write(data,audio,16000,format='WAV',subtype='PCM_16')
            result=client.transcribe(data.getvalue(),'wav',model=model,consent=True)
            flags=['cloud_transcript','coarse_timing','confidence_unavailable','speaker_unverified']
            if speaker=='unknown':flags.append('speaker_ambiguous')
            text=result['text'].strip()
            segment=Segment(a,b,text,'system',speaker,metrics={'provider':'openrouter','model':model,'usage':result['usage']},flags=flags)
            # One transaction: never checkpoint a result without its transcript.
            with store.db:
                if text:
                    d=segment.to_dict()
                    store.db.execute('INSERT INTO segments(meeting,start,end,source,speaker,speaker_name,payload) VALUES(?,?,?,?,?,?,?)',
                        (mid,a,b,'system',speaker,None,json.dumps(d,ensure_ascii=False)))
                store.db.execute('INSERT INTO cloud_chunks VALUES(?,?,?)',(mid,i,json.dumps(result['usage'])))
    emit('transcribing',len(spans),len(spans),'OpenRouter')
    return spans


def import_file(store,path,title,data_dir,*,consent=False,resume=None,client=None,model=None):
    _consent(consent)
    if not isinstance(title,str) or not title.strip() or len(title)>200:raise ValueError('Toplantı başlığı gerekli (en fazla 200 karakter)')
    client=client or OpenRouterClient()  # Fail on missing key before local inference or new meeting.
    import fcntl
    data_dir=Path(data_dir);data_dir.mkdir(parents=True,exist_ok=True)
    with (data_dir/'openrouter-job.lock').open('a') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise ValueError('Bir OpenRouter işlemi zaten çalışıyor') from None
        from .recovery import current_job_metadata
        if resume:
            row=store.db.execute('SELECT * FROM meetings WHERE id=?',(resume,)).fetchone()
            if not row:raise ValueError('Toplantı bulunamadı')
            metadata=json.loads(row['metadata'])
            if metadata.get('engine')!='openrouter':raise ValueError('Bu toplantı OpenRouter ile oluşturulmamış')
            stored_model=validate_stt_model(metadata.get('model'))
            if model is not None and model!=stored_model:raise ValueError('Devam ederken model değiştirilemez; farklı model için yeni toplantı oluşturun')
            model=stored_model
            mid=resume;target=Path(metadata['paths']['system'])
            if row['status']=='complete':return {'meeting':mid,'segments':len(store.segments(mid))}
        else:
            model=validate_stt_model(model or STT_MODEL)
            path=Path(path).resolve(strict=True)
            if not path.is_file():raise ValueError('Ses dosyası bulunamadı')
            folder=data_dir/'imports'/uuid.uuid4().hex;folder.mkdir(parents=True,mode=0o700)
            target=folder/'audio.wav'
            metadata={'engine':'openrouter','model':model,'diarization':'sherpa','paths':{'system':str(target)},'cloud_upload_authorized':True}
            mid=store.create_meeting(title.strip(),metadata)
        metadata.update(current_job_metadata())
        with store.db:store.db.execute('UPDATE meetings SET status=?,metadata=? WHERE id=?',('processing',json.dumps(metadata),mid))
        try:
            if not resume:
                emit('reading_audio')
                result=subprocess.run([shutil.which('ffmpeg') or '/opt/homebrew/bin/ffmpeg','-nostdin','-v','error','-i',str(path),'-vn','-ar','16000','-ac','1','-c:a','pcm_f32le',str(target)],capture_output=True,timeout=600)
                if result.returncode:raise ValueError('Ses dosyası dönüştürülemedi')
            info=sf.info(target)
            if not 0<info.duration<=14400:raise ValueError('En fazla dört saatlik kayıt destekleniyor')
            source=store.db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='cloud_sources'").fetchone()
            saved=store.db.execute('SELECT * FROM cloud_sources WHERE meeting=?',(mid,)).fetchone() if source else None
            if saved:
                if digest_file(target)!=saved['digest']:raise ValueError('Kaynak ses değişmiş; devam edilmedi')
                turns=json.loads(saved['plan'])
            else:
                emit('diarizing')
                from .isolated_diarization import isolated_file_turns
                root=Path(__file__).resolve().parents[1]/'models/sherpa'
                turns=isolated_file_turns(target,'system',root,.9,info.frames)
            transcribe_prepared(store,mid,target,turns,client,consent=True,model=model)
            # Existing voice identity remains local; no automatic profile enrollment.
            emit('identifying')
            from .final_identity import FinalEmbedder
            embedder=FinalEmbedder()
            rows=[r for r in store.segments(mid) if 'speaker_ambiguous' not in r['flags'] and r['end']-r['start']>=3 and r.get('embedding') is None]
            with contextlib.redirect_stdout(__import__('sys').stderr):
                vectors=embedder.embed_file(target,[(round(r['start']*16000),round(r['end']*16000)) for r in rows])
            for row,vector in zip(rows,vectors):
                if vector is None:continue
                identity=store.identify(vector,embedder.model_id,.80,.08)
                row['embedding']=vector;row['embedding_model']=embedder.model_id
                row['speaker_name']=identity['name'];row['metrics']['identity']=identity
                with store.db:store.db.execute('UPDATE segments SET speaker_name=?,payload=? WHERE id=? AND meeting=?',
                    (identity['name'],json.dumps(row,ensure_ascii=False),row['id'],mid))
            store.status(mid,'complete');emit('complete')
            return {'meeting':mid,'segments':len(store.segments(mid)),'duration':info.duration,'model':model}
        except BaseException:
            store.status(mid,'incomplete');raise
