"""Shrink finished recordings without losing anything playback or voice identity needs.

The assembled `*-full.wav` files are 16 kHz mono float32 (≈230 MB per hour per source). After the cloud
transcript and identity pass they are re-encoded as 16-bit FLAC: lossless for speech at this depth, read by
soundfile everywhere the app touches audio, played by AVAudioPlayer, typically 3–4× smaller."""
import json, os
from pathlib import Path
import numpy as np
import soundfile as sf

BLOCK = 16000 * 30   # 30 s of 16 kHz audio per block: bounded memory


class ArchivePaused(Exception):
    """A live recording takes priority over an idle archive pass."""


def _check_recording(should_stop):
    if should_stop is not None and should_stop(): raise ArchivePaused()


def archive_file(src, dst=None, *, remove_source=True, should_stop=None):
    """WAV → verified FLAC. Meeting callers keep the WAV until its replacement path commits."""
    src = Path(src)
    if src.suffix.lower() != '.wav': return src, 0
    dst = Path(dst) if dst else src.with_suffix('.flac')
    tmp = dst.with_name(dst.name + '.tmp')
    try:
        with sf.SoundFile(src) as f:
            if f.channels != 1 or f.samplerate != 16000: raise ValueError('Yalnız 16 kHz mono birleştirilmiş ses arşivlenir')
            with sf.SoundFile(tmp, 'w', samplerate=f.samplerate, channels=1, format='FLAC', subtype='PCM_16') as out:
                while True:
                    _check_recording(should_stop)
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
    os.replace(tmp, dst)
    if remove_source: src.unlink()
    return dst, before - dst.stat().st_size


def _save_metadata(store,mid,previous,replacement):
    """Merge only archive changes under the write lock; encoding must not undo a concurrent Keep Audio edit."""
    changed={k:v for k,v in replacement.items() if k not in previous or previous[k]!=v}
    removed=set(previous)-set(replacement)
    with store.db:
        store.db.execute('BEGIN IMMEDIATE')
        row=store.db.execute('SELECT status,metadata FROM meetings WHERE id=?',(mid,)).fetchone()
        if not row or row['status']!='complete': raise ValueError('Arşivlenirken toplantı durumu değişti; kaynak ses korundu')
        current=json.loads(row['metadata'] or '{}')
        if current.get('paths')!=previous.get('paths'): raise ValueError('Arşivlenirken ses yolu değişti; kaynak ses korundu')
        current.update(changed)
        for key in removed: current.pop(key,None)
        store.db.execute('UPDATE meetings SET metadata=? WHERE id=?',(json.dumps(current),mid))
    return current


def _audio_stamp(path):
    s=Path(path).stat()
    return s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns


def _verified_archive(source,target,should_stop):
    """A retained WAV may be deleted only for a readable, unchanged FLAC of the same complete length."""
    try:
        stamps=(_audio_stamp(source),_audio_stamp(target))
        original=sf.info(source)
        with sf.SoundFile(target) as archive:
            if (archive.format!='FLAC' or original.channels!=1 or original.samplerate!=16000 or original.frames<=0
                or (archive.channels,archive.samplerate,archive.frames)!=(original.channels,original.samplerate,original.frames)):
                return None
            # A truncated FLAC can retain the original frame count in its header. Read the body too,
            # outside the database lock, with the same bounded recording checks as the encoder.
            frames=0
            while True:
                _check_recording(should_stop)
                block=archive.read(BLOCK,dtype='int16')
                if len(block)==0: break
                frames+=len(block)
            if frames!=original.frames: return None
        return stamps if stamps==(_audio_stamp(source),_audio_stamp(target)) else None
    except (OSError,ValueError,RuntimeError): return None


def _cleanup_sources(store,mid,meta,should_stop):
    pending=meta.get('archive_pending_wavs') or []
    expected=meta.get('paths') or {}
    safe={p for p in expected.values() if isinstance(p,str) and Path(p).suffix.lower()=='.flac'}
    candidates=[p for p in pending if isinstance(p,str) and Path(p).suffix.lower()=='.wav' and str(Path(p).with_suffix('.flac')) in safe]
    verified={p:_verified_archive(p,Path(p).with_suffix('.flac'),should_stop) for p in candidates if Path(p).is_file()}
    _check_recording(should_stop)
    with store.db:
        store.db.execute('BEGIN IMMEDIATE')
        row=store.db.execute('SELECT status,metadata FROM meetings WHERE id=?',(mid,)).fetchone()
        if not row or row['status']!='complete': raise ValueError('Arşivlenirken toplantı durumu değişti; kaynak ses korundu')
        current=json.loads(row['metadata'] or '{}');paths=current.get('paths') or {}
        if paths!=expected: raise ValueError('Arşivlenirken ses yolu değişti; kaynak ses korundu')
        remaining=[]
        for old in candidates:
            source=Path(old);target=source.with_suffix('.flac')
            if not source.exists(): continue  # cleanup succeeded before an interrupted metadata commit
            try: safe_now=verified.get(old) is not None and verified[old]==(_audio_stamp(source),_audio_stamp(target))
            except OSError: safe_now=False
            if not safe_now:
                # Restore playback to the only verified source. The next idle pass can re-encode it;
                # repairing metadata must succeed before that pass is ever allowed to remove the WAV.
                for key,value in paths.items():
                    if value==str(target): paths[key]=old
                continue
            try: source.unlink()
            except OSError: remaining.append(old)
        current['paths']=paths
        if remaining: current['archive_pending_wavs']=remaining
        else: current.pop('archive_pending_wavs',None)
        # Keep the path check and unlink under the same lock: another bridge cannot switch playback
        # back to the WAV between those two operations. Before this transaction the FLAC was committed.
        store.db.execute('UPDATE meetings SET metadata=? WHERE id=?',(json.dumps(current),mid))


def archive_meeting(store, mid, row=None, *, should_stop=None):
    """Archive every `paths` entry of a completed meeting; metadata paths are rewritten. Returns bytes saved.
    A caller that already holds the meeting row passes it in rather than making the database find it again."""
    if row is None: row = store.db.execute('SELECT status,metadata FROM meetings WHERE id=?', (mid,)).fetchone()
    if not row or row['status'] != 'complete': return 0
    previous=json.loads(row['metadata'] or '{}')
    meta = json.loads(row['metadata'] or '{}'); paths = meta.get('paths') or {}
    saved = 0; changed = False
    pending = list(meta.get('archive_pending_wavs') or [])
    for source, p in list(paths.items()):
        _check_recording(should_stop)
        path = Path(p) if isinstance(p, str) else None
        if not path or path.suffix.lower() != '.wav': continue
        if not path.is_file():
            # Older versions deleted the WAV before committing the new path. A verified, atomically
            # published sibling can repair that interruption without re-transcribing the meeting.
            dst=path.with_suffix('.flac')
            try: info=sf.info(dst)
            except (OSError,ValueError,RuntimeError): continue
            if info.format!='FLAC' or info.channels!=1 or info.samplerate!=16000 or info.frames<=0: continue
            paths[source]=str(dst);changed=True
            continue
        try: dst, gain = archive_file(path,remove_source=False,should_stop=should_stop)
        except (OSError, ValueError, RuntimeError) as exc:
            meta.setdefault('archive_errors', []).append(f'{source}: {type(exc).__name__}'); changed = True; continue
        paths[source] = str(dst); saved += gain; changed = True
        if str(path) not in pending: pending.append(str(path))
    if changed:
        meta['paths'] = paths; meta['audio_archived_bytes'] = meta.get('audio_archived_bytes', 0) + saved
        if pending: meta['archive_pending_wavs']=pending
        meta=_save_metadata(store,mid,previous,meta)
    # The database now points to the FLAC. An interrupted cleanup leaves its exact old paths in metadata
    # so the next idle pass can finish, without re-encoding or deleting an unrelated neighbouring file.
    if pending:
        _cleanup_sources(store,mid,meta,should_stop)
    return saved


def archive_all(store, *, should_stop=None):
    """One pass over every completed meeting (used by the settings button and the hourly housekeeping)."""
    total = 0; count = 0
    for m in store.meetings():
        _check_recording(should_stop)
        if m['status'] != 'complete': continue
        gain = archive_meeting(store, m['id'], m,should_stop=should_stop)
        if gain: total += gain; count += 1
    return {'meetings': count, 'bytes': total}
