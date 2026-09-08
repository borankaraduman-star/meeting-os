"""Canonical exact float32 sample identity, excluding WAV container metadata."""
import hashlib,json
from pathlib import Path
import numpy as np
import soundfile as sf
from .asr_checkpoints import _signature
from .resources import check_pressure


def hash_snapshot(path):
    path=Path(path);before=_signature(path);check_pressure()
    with sf.SoundFile(path) as audio:
        if audio.samplerate!=16000 or audio.channels!=1 or audio.subtype!='FLOAT' or not 0<audio.frames<=16000*14400:
            raise ValueError('Checkpoint requires mono16k float32 snapshot')
        h=hashlib.sha256(json.dumps(['pcm-f32le-v1',audio.samplerate,audio.channels,audio.frames]).encode())
        count=0
        for index,block in enumerate(audio.blocks(blocksize=65536,dtype='float32')):
            if index%64==0:check_pressure()
            if not np.isfinite(block).all():raise ValueError('Nonfinite diarization samples')
            h.update(np.ascontiguousarray(block,dtype='<f4').tobytes());count+=len(block)
        if count!=audio.frames:raise ValueError('Incomplete diarization snapshot')
    if _signature(path)!=before:raise ValueError('Diarization snapshot changed while hashing')
    return before,h.hexdigest()
