"""Bounded read-only signal evidence for finalized capture chunks; no speech claim."""
from pathlib import Path
import time

def inspect_signal(path, directory):
    import numpy as np
    import soundfile as sf
    unknown={'state':'unavailable'}
    try:
        path=Path(path).resolve()
        if path.parent!=Path(directory).resolve():return unknown
        before=path.stat()
        if not 0<before.st_size<=64*1024*1024:return unknown
        with sf.SoundFile(path) as audio:
            if audio.format not in ('WAV','WAVEX') or not 0<audio.channels<=8:return unknown
            if not 0<audio.samplerate<=192000 or not 0<audio.frames<=audio.samplerate*65:return unknown
            count=0;sum_squares=0.;peak=0.
            for block in audio.blocks(blocksize=32768,dtype='float64',always_2d=True):
                if not np.isfinite(block).all():return unknown
                peak=max(peak,float(np.max(np.abs(block))))
                with np.errstate(over="ignore",invalid="ignore"):
                    sum_squares+=float(np.sum(block*block))
                count+=block.size
            if count!=audio.frames*audio.channels or not np.isfinite(sum_squares):return unknown
            duration=audio.frames/audio.samplerate
        after=path.stat()
        identity=lambda s:(s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns)
        if identity(before)!=identity(after):return unknown
        return {'state':'digital_silence' if peak==0 else 'signal','rms':float(np.sqrt(sum_squares/count)),
                'peak':peak,'duration':duration,'age_seconds':max(0,time.time()-after.st_mtime)}
    except (OSError,RuntimeError,ValueError,TypeError):return unknown
