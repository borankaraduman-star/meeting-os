"""Meeting-owned completed Sherpa turns; only immutable-file retries use this."""
import hashlib,json,os,platform,sqlite3,sys,time
from pathlib import Path
import soundfile as sf
from .asr_checkpoints import _hash_file,_signature
from .isolated_diarization import validate_turns

MAX_ENTRY=4*1024**2
MAX_BYTES=32*1024**2
MAX_ENTRIES=128


def artifact_paths(backend):
    import sherpa_onnx
    root=Path(__file__).parent
    models=Path(backend.sherpa_root).resolve(strict=True)
    runtime=Path(sherpa_onnx.__file__).resolve().parent
    # Include package native libraries and Python configuration code, as well
    # as model auxiliary files; exclude bytecode, which changes on import.
    paths=[p.resolve() for p in models.rglob('*') if p.is_file()]
    paths += [p.resolve() for p in runtime.rglob('*') if p.is_file() and p.suffix in ('.py','.so','.dylib')]
    paths += [root/n for n in ('speakers.py','isolated_diarization.py','diarization_checkpoints.py')]
    paths=sorted(set(paths))
    if len(paths)>1024 or not (models/'titanet-small.onnx').is_file() or not (models/'sherpa-onnx-pyannote-segmentation-3-0/model.onnx').is_file():
        raise ValueError('Invalid diarization artifacts')
    return paths


class CheckpointDiarizer:
    def __init__(self,backend,store,meeting):
        if backend.mode!='sherpa' or not backend.isolate_sherpa:raise ValueError('Checkpoints require isolated Sherpa')
        self.backend=backend;self.db=store.db;self.meeting=meeting
        self.hits=self.misses=self.errors=0
        if self.db.in_transaction:raise ValueError('Diarization checkpoint requires idle transaction')
        self.paths=artifact_paths(backend);self.artifacts=[_hash_file(p) for p in self.paths]
        self.options=self._options()
        self.identity=hashlib.sha256(json.dumps({'schema':1,'artifacts':[(str(p),h) for p,(_,h) in zip(self.paths,self.artifacts)],'options':self.options},sort_keys=True).encode()).hexdigest()
        self.db.execute('''CREATE TABLE IF NOT EXISTS diarization_checkpoints(
            meeting TEXT REFERENCES meetings(id) ON DELETE CASCADE,identity TEXT,audio TEXT,
            payload TEXT NOT NULL,bytes INTEGER NOT NULL,digest TEXT NOT NULL,used INTEGER NOT NULL,
            PRIMARY KEY(meeting,identity,audio))''');self.db.commit()
    def __getattr__(self,key):return getattr(self.backend,key)
    def _options(self):
        return {'model_root':str(Path(self.backend.sherpa_root).resolve()),'threshold':self.backend.threshold,
                'platform':[platform.system(),platform.release(),platform.machine(),platform.python_version()],
                'environment':{k:v for k,v in os.environ.items() if k.startswith(('OMP_','ORT_','SHERPA_','VECLIB_'))}}
    def _unchanged(self,path,signature):
        if self._options()!=self.options or artifact_paths(self.backend)!=self.paths or any(_signature(p)!=s for p,(s,_) in zip(self.paths,self.artifacts)) or _signature(path)!=signature:
            raise ValueError('Diarization checkpoint input changed')
    def _report(self):
        print(json.dumps({'diarization_checkpoints':{'hits':self.hits,'misses':self.misses,'errors':self.errors}}),file=sys.stderr)
    def turns_file(self,path,source,frames):
        if self.db.in_transaction:raise ValueError('Diarization checkpoint requires idle transaction')
        path=Path(path).resolve(strict=True);signature,audio_hash=_hash_file(path)
        info=sf.info(path)
        if type(frames) is not int or not 0<frames<=16000*14400 or info.frames!=frames or info.samplerate!=16000 or info.channels!=1 or info.subtype!='FLOAT':
            raise ValueError('Checkpoint requires private mono16k float32 snapshot')
        if not isinstance(source,str) or not source or len(source)>128:raise ValueError('Invalid source')
        self._unchanged(path,signature)
        key=hashlib.sha256(json.dumps([audio_hash,source,frames,16000]).encode()).hexdigest()
        params=(self.meeting,self.identity,key)
        try:
            row=self.db.execute('SELECT CASE WHEN length(CAST(payload AS BLOB))<=? THEN payload ELSE NULL END,bytes,digest FROM diarization_checkpoints WHERE meeting=? AND identity=? AND audio=?',(MAX_ENTRY,*params)).fetchone()
            if row is not None:
                try:
                    if not isinstance(row[0],str) or len(row[0].encode())!=row[1] or hashlib.sha256(row[0].encode()).hexdigest()!=row[2]:raise ValueError('Invalid checkpoint checksum')
                    turns=validate_turns(json.loads(row[0]),source,frames)
                except (ValueError,TypeError,OverflowError):
                    self.errors+=1
                    with self.db:self.db.execute('DELETE FROM diarization_checkpoints WHERE meeting=? AND identity=? AND audio=?',params)
                else:
                    self._unchanged(path,signature)
                    with self.db:self.db.execute('UPDATE diarization_checkpoints SET used=? WHERE meeting=? AND identity=? AND audio=?',(time.time_ns(),*params))
                    self.hits+=1;self._report();return turns
        except sqlite3.Error:self.errors+=1
        self.misses+=1
        turns=self.backend.turns_file(path,source,frames)
        self._unchanged(path,signature)
        turns=validate_turns([list(t) for t in turns],source,frames)
        payload=json.dumps(turns,allow_nan=False);size=len(payload.encode())
        if size<=min(MAX_ENTRY,MAX_BYTES):
            try:
                with self.db:
                    self.db.execute('INSERT OR REPLACE INTO diarization_checkpoints VALUES(?,?,?,?,?,?,?)',(*params,payload,size,hashlib.sha256(payload.encode()).hexdigest(),time.time_ns()))
                    while True:
                        total,count=self.db.execute('SELECT COALESCE(SUM(bytes),0),COUNT(*) FROM diarization_checkpoints').fetchone()
                        if total<=MAX_BYTES and count<=MAX_ENTRIES:break
                        self.db.execute('DELETE FROM diarization_checkpoints WHERE rowid=(SELECT rowid FROM diarization_checkpoints ORDER BY used,rowid LIMIT 1)')
            except sqlite3.Error:self.errors+=1
        self._report();return turns
