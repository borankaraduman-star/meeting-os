"""Bounded, meeting-owned raw CPP outputs for interrupted retries only."""
import hashlib,json,math,os,platform,shutil,sqlite3,time,sys
from pathlib import Path
import numpy as np
from .audio import RATE
from .resources import check_pressure

MAX_ENTRY=2*1024**2
MAX_BYTES=64*1024**2
MAX_ENTRIES=4096


def _signature(path):
    s=path.stat();return (s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns)


def _hash_file(path, allow_warning=False):
    before=_signature(path);h=hashlib.sha256();blocks=0
    check_pressure(allow_warning=allow_warning)
    with path.open('rb') as f:
        while block:=f.read(1024**2):
            if blocks%64==0:check_pressure(allow_warning=allow_warning)
            blocks+=1;h.update(block)
    if before!=_signature(path):raise ValueError('ASR artifact changed during hashing')
    return before,h.hexdigest()


def _rows(value):
    if not isinstance(value,list) or len(value)>1000:raise ValueError('Invalid ASR checkpoint rows')
    for row in value:
        if not isinstance(row,dict) or not isinstance(row.get('text'),str):raise ValueError('Invalid ASR checkpoint text')
        a,b=row.get('start'),row.get('end')
        if type(a) not in (int,float) or type(b) not in (int,float) or not all(math.isfinite(x) for x in (a,b)) or not 0<=a<b:
            raise ValueError('Invalid ASR checkpoint time')
        words=row.get('words',[])
        if not isinstance(words,list):raise ValueError('Invalid ASR checkpoint words')
        for w in words:
            if not isinstance(w,dict) or not isinstance(w.get('word'),str):raise ValueError('Invalid ASR checkpoint word')
            x,y=w.get('start'),w.get('end')
            if type(x) not in (int,float) or type(y) not in (int,float) or not all(math.isfinite(z) for z in (x,y)) or not a<=x<=y<=b:
                raise ValueError('Invalid ASR checkpoint word time')
    return value


class CheckpointASR:
    def __init__(self,backend,store,meeting):
        if backend.engine!='cpp':raise ValueError('Checkpoints require CPP')
        self.backend=backend;self.db=store.db;self.meeting=meeting
        self.hits=self.misses=self.errors=0
        if self.db.in_transaction:raise ValueError('Checkpoint setup requires idle transaction')
        binary=shutil.which(backend.cpp_bin)
        if not binary:raise ValueError('CPP binary unavailable')
        root=Path(__file__).parent
        self.paths=[Path(backend.model).resolve(),Path(binary).resolve(),root/'backends.py',root/'cpp_words.py',Path(__file__).resolve()]
        self.artifacts=[_hash_file(p) for p in self.paths]
        self.initial_options=self._options()
        identity={'schema':1,'artifacts':[h for _,h in self.artifacts],'options':self.initial_options,
                  'platform':[platform.system(),platform.release(),platform.machine()]}
        self.identity=hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()
        self.db.execute('''CREATE TABLE IF NOT EXISTS asr_checkpoints(
            meeting TEXT REFERENCES meetings(id) ON DELETE CASCADE,
            identity TEXT, audio TEXT, payload TEXT NOT NULL, bytes INTEGER NOT NULL,
            digest TEXT NOT NULL, used INTEGER NOT NULL, PRIMARY KEY(meeting,identity,audio))''')
        self.db.commit()

    def __getattr__(self,key):return getattr(self.backend,key)

    def _options(self):
        b=self.backend
        env={k:v for k,v in os.environ.items() if k.startswith(('GGML_','WHISPER_','OMP_','VECLIB_')) or k in ('LANG','LC_ALL','LC_NUMERIC')}
        return {'model':str(b.model),'binary':str(b.cpp_bin),'engine':b.engine,'language':b.language,'prompt':b.prompt,
                'threads':b.cpp_threads,'flash':b.flash_attention,'gpu':b.use_gpu,'environment':env}

    def _unchanged(self):
        binary=shutil.which(self.backend.cpp_bin)
        if not binary or Path(binary).resolve()!=self.paths[1] or Path(self.backend.model).resolve()!=self.paths[0]:
            raise ValueError('ASR artifact target changed during retry')
        if self._options()!=self.initial_options or any(_signature(p)!=s for p,(s,_) in zip(self.paths,self.artifacts)):
            raise ValueError('ASR identity changed during retry')

    def _report(self):
        print(json.dumps({"asr_checkpoints":{"hits":self.hits,"misses":self.misses,"errors":self.errors}}),file=sys.stderr)

    def transcribe(self,audio):
        self._unchanged()
        if self.db.in_transaction:raise ValueError('Checkpoint operation requires idle transaction')
        audio=np.asarray(audio,dtype=np.float32)
        if audio.ndim!=1 or not np.isfinite(audio).all():raise ValueError('Invalid ASR checkpoint audio')
        key=hashlib.sha256(str(RATE).encode()+np.ascontiguousarray(audio,dtype='<f4').tobytes()).hexdigest()
        params=(self.meeting,self.identity,key)
        try:
            row=self.db.execute('SELECT CASE WHEN length(CAST(payload AS BLOB))<=? THEN payload ELSE NULL END,bytes,digest FROM asr_checkpoints WHERE meeting=? AND identity=? AND audio=?',(MAX_ENTRY,*params)).fetchone()
            if row is not None:
                try:
                    if not isinstance(row[0],str) or len(row[0].encode())!=row[1] or len(row[0].encode())>MAX_ENTRY or hashlib.sha256(row[0].encode()).hexdigest()!=row[2]:raise ValueError('Invalid checkpoint payload')
                    value=_rows(json.loads(row[0]));json.dumps(value,allow_nan=False)
                except (ValueError,TypeError,OverflowError):
                    self.errors+=1
                    with self.db:self.db.execute('DELETE FROM asr_checkpoints WHERE meeting=? AND identity=? AND audio=?',params)
                else:
                    self._unchanged()
                    with self.db:self.db.execute('UPDATE asr_checkpoints SET used=? WHERE meeting=? AND identity=? AND audio=?',(time.time_ns(),*params))
                    self.hits+=1;self._report();return value
        except sqlite3.Error:self.errors+=1
        self.misses+=1
        value=self.backend.transcribe(audio)
        self._unchanged();_rows(value)
        payload=json.dumps(value,ensure_ascii=False,allow_nan=False);size=len(payload.encode())
        if size<=min(MAX_ENTRY,MAX_BYTES):
            try:
                with self.db:
                    self.db.execute('INSERT OR REPLACE INTO asr_checkpoints VALUES(?,?,?,?,?,?,?)',(*params,payload,size,hashlib.sha256(payload.encode()).hexdigest(),time.time_ns()))
                    while True:
                        total,count=self.db.execute('SELECT COALESCE(SUM(bytes),0),COUNT(*) FROM asr_checkpoints').fetchone()
                        if total<=MAX_BYTES and count<=MAX_ENTRIES:break
                        self.db.execute('DELETE FROM asr_checkpoints WHERE rowid=(SELECT rowid FROM asr_checkpoints ORDER BY used,rowid LIMIT 1)')
            except sqlite3.Error:self.errors+=1
        self._report();return value
