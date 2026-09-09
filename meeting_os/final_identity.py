"""Retry-only Resemblyzer worker, after ASR; parent never imports Torch."""
import importlib.util,json,math,sys,tempfile
from pathlib import Path
import soundfile as sf
from .asr_checkpoints import _hash_file,_signature
from .supervisor import run_guarded

MAX_SPANS=10000
MAX_BATCH_SPANS=512
MAX_OUTPUT=32*1024**2


def validate_spans(spans,frames):
    if not isinstance(spans,(list,tuple)) or len(spans)>MAX_SPANS:raise ValueError('Too many embedding spans')
    for span in spans:
        if not isinstance(span,(list,tuple)) or len(span)!=2 or any(type(x) is not int for x in span) or not 0<=span[0]<=span[1]<=frames or span[1]-span[0]>16000*60:
            raise ValueError('Invalid embedding span')


def validate_vectors(data,count,model_id):
    if not isinstance(data,dict) or data.get('model_id')!=model_id or not isinstance(data.get('rows'),list) or len(data['rows'])!=count:
        raise ValueError('Incomplete embedding output')
    vectors=[]
    for i,row in enumerate(data['rows']):
        if not isinstance(row,dict) or type(row.get('index')) is not int or row['index']!=i:raise ValueError('Embedding order mismatch')
        v=row.get('vector')
        if 'vector' not in row:raise ValueError('Missing embedding vector')
        if v is not None:
            if not isinstance(v,list) or len(v)!=256 or any(type(x) not in (int,float) or not math.isfinite(x) for x in v) or abs(sum(x*x for x in v)-1)>1e-4:
                raise ValueError('Invalid embedding vector')
        vectors.append(v)
    return vectors


class FinalEmbedder:
    isolated_final=True
    engine='resemblyzer'
    def __init__(self,model=None,light=False):
        self.light=light  # voice embedder is small; under light mode OS warning pressure does not block it
        if model:self.weights=Path(model).resolve(strict=True)
        else:
            spec=importlib.util.find_spec('resemblyzer')
            if spec is None or not spec.submodule_search_locations:raise ValueError('Resemblyzer package unavailable')
            self.weights=(Path(next(iter(spec.submodule_search_locations)))/'pretrained.pt').resolve(strict=True)
        self.signature,self.digest=_hash_file(self.weights)
        self.model_id='resemblyzer:'+self.digest[:16]
    def embed(self,audio):raise ValueError('Final identity requires deferred file batch')
    def embed_file(self,path,spans):
        if _signature(self.weights)!=self.signature:raise ValueError('Embedding weights changed')
        path=Path(path).resolve(strict=True);signature=_signature(path);info=sf.info(path)
        if info.samplerate!=16000 or info.channels!=1 or info.subtype!='FLOAT' or not 0<info.frames<=16000*14400:raise ValueError('Invalid identity snapshot')
        validate_spans(spans,info.frames)
        if not spans:return []
        vectors=[]
        # Reload the model per bounded batch to limit worker/result memory.
        # This trades additional startup work for memory, with no latency claim.
        for start in range(0,len(spans),MAX_BATCH_SPANS):
            batch=spans[start:start+MAX_BATCH_SPANS]
            if _signature(path)!=signature or _signature(self.weights)!=self.signature:raise ValueError('Identity input changed')
            with tempfile.TemporaryDirectory(prefix='meeting-os-identity-') as tmp:
                root=Path(tmp);request=root/'request.json';output=root/'result.json'
                request.write_text(json.dumps({'path':str(path),'signature':signature,'frames':info.frames,'spans':batch,'weights':str(self.weights),'weight_signature':self.signature,'digest':self.digest}))
                run_guarded([sys.executable,'-m','meeting_os.final_identity',str(request),str(output)],timeout=600,light=self.light)
                with output.open('rb') as f:raw=f.read(MAX_OUTPUT+1)
                if len(raw)>MAX_OUTPUT:raise ValueError('Embedding output too large')
                batch_vectors=validate_vectors(json.loads(raw),len(batch),self.model_id)
                if _signature(path)!=signature or _signature(self.weights)!=self.signature:raise ValueError('Identity input changed')
                vectors.extend(batch_vectors)
        return vectors


def main():
    with Path(sys.argv[1]).open('rb') as f:raw=f.read(2*1024**2+1)
    if len(raw)>2*1024**2:raise ValueError('Embedding request too large')
    data=json.loads(raw);path=Path(data['path']);weights=Path(data['weights'])
    if list(_signature(path))!=data['signature']:raise ValueError('Identity snapshot changed')
    sig,digest=_hash_file(weights)
    if list(sig)!=data['weight_signature'] or digest!=data['digest']:raise ValueError('Identity weights changed')
    import torch
    # The prior in-process path runs after Silero, which sets this to one.
    # Preserve that CPU budget when identity moves to its own fresh process.
    torch.set_num_threads(1)
    from .speakers import Embedder
    embedder=Embedder('resemblyzer',weights)
    if embedder.model_id!='resemblyzer:'+digest[:16]:raise ValueError('Embedding model identity mismatch')
    rows=[]
    import numpy as np
    with sf.SoundFile(path) as reader:
        if reader.samplerate!=16000 or reader.channels!=1 or reader.subtype!='FLOAT' or reader.frames!=data['frames'] or type(data['frames']) is not int or not 0<reader.frames<=16000*14400:raise ValueError('Invalid identity snapshot')
        validate_spans(data['spans'],reader.frames)
        for i,(a,b) in enumerate(data['spans']):
            reader.seek(a);clip=reader.read(b-a,dtype='float32')
            if len(clip)!=b-a or not np.isfinite(clip).all():raise ValueError('Invalid identity audio')
            rows.append({'index':i,'vector':embedder.embed(clip)})
    if list(_signature(path))!=data['signature'] or _signature(weights)!=sig:raise ValueError('Identity input changed')
    result={'model_id':embedder.model_id,'rows':rows};validate_vectors(result,len(data['spans']),embedder.model_id)
    encoded=json.dumps(result,allow_nan=False).encode()
    if len(encoded)>MAX_OUTPUT:raise ValueError('Embedding output too large')
    Path(sys.argv[2]).write_bytes(encoded)

if __name__=='__main__':main()
