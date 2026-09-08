"""Release Sherpa native memory before ASR by using a bounded direct child."""
import argparse,json,math,shutil,sys,tempfile
from pathlib import Path
import numpy as np
import soundfile as sf
from .audio import RATE
from .supervisor import run_guarded


def isolated_turns(audio,source,model,threshold):
    audio=np.asarray(audio,dtype=np.float32)
    if audio.ndim!=1 or len(audio)>RATE*14400 or not all(np.isfinite(audio[a:a+65536]).all() for a in range(0,len(audio),65536)):
        raise ValueError('Invalid diarization audio')
    if not audio.size:return []
    if not isinstance(source,str) or not source or len(source)>128:raise ValueError('Invalid source label')
    with tempfile.TemporaryDirectory(prefix='meeting-os-diarization-') as tmp:
        root=Path(tmp);wav=root/'input.wav';out=root/'turns.json'
        if shutil.disk_usage(root).free < audio.nbytes+100*1024**2:raise OSError('Insufficient diarization disk space')
        sf.write(wav,audio,RATE,subtype='FLOAT')
        return _run_child(wav,out,source,model,threshold,len(audio))


def _run_child(wav,out,source,model,threshold,frames):
    # Same owned process group as the caller: outer CLI lifeline can reap
    # this worker too. Worker performs no further subprocess/model jobs.
    run_guarded([sys.executable,'-m','meeting_os.isolated_diarization','--audio',str(wav),
        '--output',str(out),'--model',str(Path(model).resolve()),'--source',source,
        '--threshold',str(threshold)],timeout=600)
    with out.open('rb') as f:raw=f.read(4*1024**2+1)
    if len(raw)>4*1024**2:raise ValueError('Diarization result too large')
    data=json.loads(raw)
    if not isinstance(data,list) or len(data)>10000:raise ValueError('Invalid diarization result')
    turns=[];previous=-1
    for row in data:
        if not isinstance(row,list) or len(row)!=3:raise ValueError('Invalid diarization turn')
        a,b,s=row
        if type(a) not in (int,float) or type(b) not in (int,float) or not math.isfinite(a) or not math.isfinite(b) or not 0<=a<b<=frames/RATE or a<previous:
            raise ValueError('Invalid diarization timeline')
        if not isinstance(s,str) or not s.startswith(source+':S') or not s[len(source)+2:].isdigit():raise ValueError('Invalid speaker label')
        turns.append((a,b,s));previous=a
    return turns


def isolated_file_turns(path,source,model,threshold,frames):
    """Only for retry-owned immutable mono16k snapshots; never delete input."""
    path=Path(path).resolve(strict=True)
    def signature():
        st=path.stat();return (st.st_dev,st.st_ino,st.st_size,st.st_mtime_ns,st.st_ctime_ns)
    before=signature();info=sf.info(path)
    if type(frames) is not int or not 0<frames<=RATE*14400 or info.frames!=frames or info.samplerate!=RATE or info.channels!=1:
        raise ValueError('Invalid immutable diarization snapshot')
    if not isinstance(source,str) or not source or len(source)>128:raise ValueError('Invalid source label')
    with tempfile.TemporaryDirectory(prefix='meeting-os-diarization-') as tmp:
        turns=_run_child(path,Path(tmp)/'turns.json',source,model,threshold,frames)
        if signature()!=before:raise ValueError('Diarization snapshot changed')
        return turns


def main():
    p=argparse.ArgumentParser();p.add_argument('--audio',required=True);p.add_argument('--output',required=True)
    p.add_argument('--model',required=True);p.add_argument('--source',required=True);p.add_argument('--threshold',type=float,required=True)
    args=p.parse_args()
    audio,rate=sf.read(args.audio,dtype='float32')
    if rate!=RATE or audio.ndim!=1 or not all(np.isfinite(audio[a:a+65536]).all() for a in range(0,len(audio),65536)):raise ValueError('Invalid worker audio')
    from .speakers import Diarizer
    turns=Diarizer(None,'sherpa',args.model,args.threshold).turns(audio,args.source)
    Path(args.output).write_text(json.dumps(turns,allow_nan=False))

if __name__=='__main__':main()
