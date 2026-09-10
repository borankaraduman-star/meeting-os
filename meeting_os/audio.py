"""Local PCM I/O and speech segmentation. All times remain in source coordinates."""
from pathlib import Path
from functools import lru_cache
import json
import math
import os
import shutil
import errno
import numpy as np
import soundfile as sf
from scipy.signal import resample_poly
from .progress import emit

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
    if len(audio) == 0: return []
    # Keep mapped final audio from acquiring a recording-sized abs temporary.
    peak = np.max(np.abs(audio[:65536]))
    for start in range(65536, len(audio), 65536):
        peak = np.maximum(peak, np.max(np.abs(audio[start:start+65536])))
    if peak < 1e-5: return []
    import torch
    from silero_vad import get_speech_timestamps
    stamps = get_speech_timestamps(torch.from_numpy(audio), vad_model(), sampling_rate=RATE,
        min_speech_duration_ms=250, min_silence_duration_ms=500, speech_pad_ms=200,
        max_speech_duration_s=max_seconds, return_seconds=False)
    return [(int(s['start']), int(s['end'])) for s in stamps]

ASSEMBLY_HEADROOM = 100*1024**2   # what the rest of finalize needs on disk once the assembled files exist


def disk_full(required_bytes):
    """The one error the user can actually act on. Carries `kind` so the cloud queue can tell it apart from a
    provider failure: freeing space fixes it, so it must not spend one of the meeting's cloud retries."""
    megabytes = math.ceil(required_bytes/1024**2)
    message = f'Disk dolu: birleştirme için ≈{megabytes} MB boş alan gerekli'
    error = OSError(errno.ENOSPC, message)
    error.user_message = message; error.kind = 'disk_full'; error.required_bytes = int(required_bytes)
    return error


def chunk_events(directory):
    """Every `chunk` line of a capture journal, in the order it was written."""
    directory = Path(directory).resolve()
    journal = directory/'capture-native.jsonl'
    if not journal.exists(): journal = directory/'events.jsonl'
    events = []
    with journal.open() as f:
        for line in f:
            try: e = json.loads(line)
            except json.JSONDecodeError: continue # crash-truncated final line
            if e.get('event') == 'chunk': events.append(e)
    return events


def journal_source_ends(directory):
    """{source: seconds of audio the journal accounts for}, or None when there is no readable journal.

    This is what a finished `*-full.wav` has to match. A killed assembler leaves a perfectly readable but
    shorter file behind, and adopting one silently transcribed part of a meeting."""
    try: events = chunk_events(directory)
    except OSError: return None
    ends = {}
    for e in events:
        source = e.get('source')
        if source not in ('mic', 'system'): continue
        try: start = float(e['start'])
        except (KeyError, TypeError, ValueError): continue
        if not math.isfinite(start) or start < 0: continue
        duration = e.get('duration')
        if not isinstance(duration, (int, float)) or isinstance(duration, bool) or not math.isfinite(duration) or duration < 0:
            try: duration = sf.info(Path(e['path']).resolve()).duration
            except Exception: duration = 0.0   # the chunk is gone; it can only make the expectation shorter
        ends[source] = max(ends.get(source, 0.0), start+float(duration))
    return ends


ADOPTION_TOLERANCE = 1.0   # seconds: the assembler rounds and the last chunk may be a hair short


TEMPORARY_GRACE_SECONDS = 3600   # a `.tmp` younger than this may still be being written by a live assembler


def adoptable_full_files(directory):
    """The assembled files of an earlier run, but only when every source the journal recorded has one and each
    is as long as the journal says. Anything else returns {} and the caller rebuilds from the chunks."""
    directory = Path(directory).resolve()
    # An assembler that was killed mid-write leaves `*-full.wav.tmp`: never adopted, and swept once it is old
    # enough to be nobody's work in progress. The hour of grace is the one `compact_capture` already uses —
    # without it this deleted the file a second assembler was writing at that very moment.
    import time
    for stale in directory.glob('*-full.wav.tmp'):
        try:
            if time.time()-stale.stat().st_mtime < TEMPORARY_GRACE_SECONDS: continue
            stale.unlink()
        except OSError: pass
    expected = journal_source_ends(directory)
    present = {s: directory/f'{s}-full.wav' for s in ('mic', 'system') if (directory/f'{s}-full.wav').is_file()}
    if not expected: return {s: str(p) for s, p in present.items()}   # no journal to check against: nothing to rebuild from either
    if set(expected) - set(present): return {}
    for source, end in expected.items():
        try: duration = sf.info(present[source]).duration
        except Exception: return {}
        if duration+ADOPTION_TOLERANCE < end: return {}   # truncated: the chunks are still the truth
    return {s: str(present[s]) for s in sorted(expected)}


def assemble_capture(directory):
    """Reconstruct separate sources with explicit silence for capture clock gaps."""
    directory = Path(directory).resolve()
    events = chunk_events(directory)
    # Plan every source before writing any of it: reserving per source in turn filled the disk halfway through
    # the second one, and a meeting that ends up with only its microphone channel has lost the other half.
    plans = {}
    for source in ('mic', 'system'):
        chunks = sorted((e for e in events if e['source'] == source), key=lambda e:e['start'])
        if not chunks: continue
        # Float output preserves capture peaks; reserve disk before creating it.
        frames_needed = 0
        for event in chunks:
            path = Path(event['path']).resolve()
            if path.parent != directory: raise ValueError('Chunk must be inside capture directory')
            start = round(float(event['start'])*RATE)
            if start < 0: raise ValueError('Negative capture timestamp')
            info = sf.info(path)
            frames_needed = max(frames_needed, start+math.ceil(info.frames*RATE/info.samplerate))
        plans[source] = (chunks, frames_needed)
    if not plans: raise ValueError('No finalized audio chunks')
    required = sum(frames*4+4096 for _,frames in plans.values())+ASSEMBLY_HEADROOM
    if shutil.disk_usage(directory).free < required: raise disk_full(required)
    result = {}
    for source,(chunks,_) in plans.items():
        target = directory/f'{source}-full.wav'
        temp = directory/f'{source}-full.wav.tmp'
        if target.is_symlink() or temp.is_symlink(): raise ValueError('Assembled audio path must not be a symlink')
        try: temp.unlink()
        except FileNotFoundError: pass
        emit('assembling',current=0,total=len(chunks),source=source)
        # The name only appears once the file is whole: a killed writer used to leave a readable, shorter
        # `*-full.wav` that the next run adopted as if the meeting had really been that long.
        try:
            with sf.SoundFile(temp, 'w', samplerate=RATE, channels=1, subtype='FLOAT', format='WAV') as out:
                cursor = 0
                for index,e in enumerate(chunks):
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
                    emit('assembling',current=index+1,total=len(chunks),source=source)
        except BaseException as exc:
            try: temp.unlink()
            except OSError: pass
            if isinstance(exc, OSError) and getattr(exc,'errno',None) == errno.ENOSPC and not hasattr(exc,'user_message'):
                raise disk_full(required) from exc
            raise
        os.replace(temp, target)
        result[source] = str(target)
    return result
