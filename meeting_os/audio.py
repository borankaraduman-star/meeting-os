"""Local PCM I/O and speech segmentation. All times remain in source coordinates."""
from pathlib import Path
from functools import lru_cache
import json
import math
import numpy as np
import soundfile as sf
from scipy.signal import resample_poly

RATE = 16000

def read_audio(path):
    audio, rate = sf.read(path, dtype='float32', always_2d=True)
    audio = audio.mean(axis=1)
    if not np.isfinite(audio).all(): raise ValueError('Audio contains non-finite samples')
    if rate != RATE:
        gcd = math.gcd(rate, RATE)
        audio = resample_poly(audio, RATE//gcd, rate//gcd).astype(np.float32)
    return audio

@lru_cache(maxsize=1)
def vad_model():
    from silero_vad import load_silero_vad
    return load_silero_vad()

def speech_regions(audio, max_seconds=28):
    if len(audio) == 0 or np.max(np.abs(audio)) < 1e-5: return []
    import torch
    from silero_vad import get_speech_timestamps
    stamps = get_speech_timestamps(torch.from_numpy(audio), vad_model(), sampling_rate=RATE,
        min_speech_duration_ms=250, min_silence_duration_ms=500, speech_pad_ms=200,
        max_speech_duration_s=max_seconds, return_seconds=False)
    return [(int(s['start']), int(s['end'])) for s in stamps]

def assemble_capture(directory):
    """Reconstruct separate sources with explicit silence for capture clock gaps."""
    directory = Path(directory).resolve()
    events = []
    journal = directory/'capture-native.jsonl'
    if not journal.exists(): journal = directory/'events.jsonl'
    with journal.open() as f:
        for line in f:
            try: e = json.loads(line)
            except json.JSONDecodeError: continue # crash-truncated final line
            if e.get('event') == 'chunk': events.append(e)
    result = {}
    for source in ('mic', 'system'):
        chunks = sorted((e for e in events if e['source'] == source), key=lambda e:e['start'])
        if not chunks: continue
        target = directory/f'{source}-full.wav'
        with sf.SoundFile(target, 'w', samplerate=RATE, channels=1, subtype='PCM_16') as out:
            cursor = 0
            for e in chunks:
                path = Path(e['path']).resolve()
                if path.parent != directory: raise ValueError('Chunk must be inside capture directory')
                x = read_audio(path)
                start = round(float(e['start'])*RATE)
                if start < 0: raise ValueError('Negative capture timestamp')
                if start > cursor:
                    gap = start-cursor
                    while gap:
                        n = min(gap, RATE*60); out.write(np.zeros(n, dtype=np.float32)); gap -= n
                elif start < cursor:
                    x = x[min(len(x), cursor-start):]
                out.write(x); cursor = max(cursor, start)+len(x)
        result[source] = str(target)
    if not result: raise ValueError('No finalized audio chunks')
    return result
