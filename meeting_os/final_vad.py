"""Run unchanged Silero VAD outside the retry parent; release Torch on exit."""
import json,sys,tempfile,warnings
from pathlib import Path
import numpy as np
import soundfile as sf
from .asr_checkpoints import _signature
from .supervisor import run_guarded


def validate_regions(rows,frames):
    if not isinstance(rows,list) or len(rows)>10000:raise ValueError('Invalid VAD output')
    result=[];previous=-1
    for row in rows:
        if not isinstance(row,(list,tuple)) or len(row)!=2 or any(type(x) is not int for x in row) or not 0<=row[0]<row[1]<=frames or row[0]<previous:raise ValueError('Invalid VAD timeline')
        previous=row[0];result.append(tuple(row))
    return result


def isolated_regions(path,frames):
    path=Path(path).resolve(strict=True);signature=_signature(path)
    if type(frames) is not int or not 0<frames<=16000*14400:raise ValueError('Invalid VAD length')
    with tempfile.TemporaryDirectory(prefix='meeting-os-vad-') as tmp:
        out=Path(tmp)/'regions.json'
        run_guarded([sys.executable,'-m','meeting_os.final_vad',str(path),str(out),str(frames)],timeout=600)
        with out.open('rb') as f:raw=f.read(1024**2+1)
        if len(raw)>1024**2:raise ValueError('VAD output too large')
        result=validate_regions(json.loads(raw),frames)
        if _signature(path)!=signature:raise ValueError('VAD input changed')
        return result


def main():
    path=Path(sys.argv[1]);frames=int(sys.argv[3]);signature=_signature(path)
    if not 0<frames<=16000*14400:raise ValueError('Invalid VAD length')
    with sf.SoundFile(path) as f:
        if f.samplerate!=16000 or f.channels!=1 or f.subtype!='FLOAT' or f.frames!=frames:raise ValueError('Invalid VAD snapshot')
    from scipy.io import wavfile
    # Map the private assembled WAV rather than allocating decoded PCM.
    # Copy-on-write is not an external-write snapshot; pre/post signatures
    # check inode, size and nanosecond mtime/ctime before accepting output.
    # SciPy uses writable copy-on-write storage: Torch can share this view
    # without allowing writes through to the source. Keep it alive for VAD.
    with warnings.catch_warnings():
        warnings.filterwarnings('ignore',message=r'^Chunk \(non-data\) not understood, skipping it\.$',category=wavfile.WavFileWarning)
        rate,audio=wavfile.read(path,mmap=True)
    if (rate!=16000 or not isinstance(audio,np.memmap) or audio.mode!='c'
            or not audio.flags.writeable or audio.dtype!=np.dtype('float32')
            or audio.ndim!=1 or audio.shape!=(frames,)):
        raise ValueError('Invalid VAD mapping')
    if _signature(path)!=signature:raise ValueError('VAD input changed')
    if len(audio)!=frames or not all(np.isfinite(audio[a:a+65536]).all() for a in range(0,frames,65536)):raise ValueError('Invalid VAD samples')
    from .audio import speech_regions
    regions=validate_regions(speech_regions(audio),frames)
    if _signature(path)!=signature:raise ValueError('VAD input changed')
    Path(sys.argv[2]).write_text(json.dumps(regions))

if __name__=='__main__':main()
