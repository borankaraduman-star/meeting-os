"""Shrink finished recordings without losing anything playback or voice identity needs.

The assembled `*-full.wav` files are 16 kHz mono float32 (≈230 MB per hour per source). After the cloud
transcript and identity pass they are re-encoded as 16-bit FLAC: lossless for speech at this depth, read by
soundfile everywhere the app touches audio, played by AVAudioPlayer, typically 3–4× smaller."""
import json, os
from pathlib import Path
import numpy as np
import soundfile as sf

BLOCK = 16000 * 30   # 30 s of 16 kHz audio per block: bounded memory


def archive_file(src, dst=None):
    """WAV → FLAC (PCM_16). Verifies the frame count before the WAV is removed. Returns (dst, bytes_saved)."""
    src = Path(src)
    if src.suffix.lower() != '.wav': return src, 0
    dst = Path(dst) if dst else src.with_suffix('.flac')
    tmp = dst.with_name(dst.name + '.tmp')
    try:
        with sf.SoundFile(src) as f:
            if f.channels != 1 or f.samplerate != 16000: raise ValueError('Yalnız 16 kHz mono birleştirilmiş ses arşivlenir')
            with sf.SoundFile(tmp, 'w', samplerate=f.samplerate, channels=1, format='FLAC', subtype='PCM_16') as out:
                while True:
                    block = f.read(BLOCK, dtype='float32')
                    if len(block) == 0: break
                    out.write(np.clip(block, -1.0, 1.0))
            frames = f.frames
    except BaseException:   # a full disk or a kill left a recording-sized `.flac.tmp` that nothing swept
        tmp.unlink(missing_ok=True)
        raise
    with sf.SoundFile(tmp) as check:
        if check.frames != frames: tmp.unlink(missing_ok=True); raise ValueError('FLAC doğrulaması başarısız')
    before = src.stat().st_size
    os.replace(tmp, dst); src.unlink()
    return dst, before - dst.stat().st_size


def archive_meeting(store, mid, row=None):
    """Archive every `paths` entry of a completed meeting; metadata paths are rewritten. Returns bytes saved.
    A caller that already holds the meeting row passes it in rather than making the database find it again."""
    if row is None: row = store.db.execute('SELECT status,metadata FROM meetings WHERE id=?', (mid,)).fetchone()
    if not row or row['status'] != 'complete': return 0
    meta = json.loads(row['metadata'] or '{}'); paths = meta.get('paths') or {}
    saved = 0; changed = False
    for source, p in list(paths.items()):
        path = Path(p) if isinstance(p, str) else None
        if not path or not path.is_file() or path.suffix.lower() != '.wav': continue
        try: dst, gain = archive_file(path)
        except (OSError, ValueError, RuntimeError) as exc:
            meta.setdefault('archive_errors', []).append(f'{source}: {type(exc).__name__}'); changed = True; continue
        paths[source] = str(dst); saved += gain; changed = True
    if changed:
        meta['paths'] = paths; meta['audio_archived_bytes'] = meta.get('audio_archived_bytes', 0) + saved
        with store.db: store.db.execute('UPDATE meetings SET metadata=? WHERE id=?', (json.dumps(meta), mid))
    return saved


def archive_all(store):
    """One pass over every completed meeting (used by the settings button and the hourly housekeeping)."""
    total = 0; count = 0
    for m in store.meetings():
        if m['status'] != 'complete': continue
        gain = archive_meeting(store, m['id'], m)
        if gain: total += gain; count += 1
    return {'meetings': count, 'bytes': total}
