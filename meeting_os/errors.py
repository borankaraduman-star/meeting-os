"""Local error journal: what actually went wrong on this Mac, one JSON line per event.

Three to five people is the point at which a fault stops being something the owner watches happen.
`last-job.log` holds the receipts of the last job only, a `model.error` banner is gone on the next click,
and a crash left nothing behind at all — so a Mac that misbehaves every third meeting looked exactly like
a Mac that never did. This journal is the missing memory: bounded, redacted, local, and summarised into
the hourly heartbeat so the development Mac learns about it without anyone having to report it.

Allowlisted content only: a kind, a short redacted message, a handful of small non-content fields and the
version. Never transcript text, never audio, never a whole crash report.
"""
import hashlib
import json
import math
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

JOURNAL_FILE = 'errors.jsonl'
ROTATED_FILE = 'errors.jsonl.1'
STATE_FILE = 'errors-state.json'      # crash watermark and the last imported update failure; survives `clear`
UPDATE_STATUS_FILE = 'update-status.json'
PRIVATE_MODE = 0o600
MAX_BYTES = 1024*1024                 # one generation is kept; the journal answers "lately", not "ever"
MESSAGE_LIMIT = 300
CONTEXT_KEYS = 8
CONTEXT_TEXT = 120
DEDUPE_SECONDS = 600                  # the same (kind, message) twice in ten minutes is one event, not two
KINDS = ('ui', 'job', 'cloud', 'capture', 'update', 'crash')
READ_LIMIT = 4000
WINDOW_HOURS = 24

DIAGNOSTIC_REPORTS = Path.home() / 'Library/Logs/DiagnosticReports'
CRASH_PREFIXES = ('MeetingOS-', 'MeetingCapture-')
CRASH_IMAGES = ('MeetingOS', 'MeetingCapture')
CRASH_FRAMES = 8
CRASH_BATCH = 20                      # a folder full of old reports must never become a thousand journal lines
CRASH_MEMORY = 50                     # incident ids remembered, so a report touched again is not recorded twice


def _now(now=None): return now or datetime.now(timezone.utc)


def _version():
    try:
        from . import __version__
        return __version__
    except Exception: return None


def _default_data_dir():
    try:
        from .cli import DATA_DIR
        return DATA_DIR
    except Exception: return None


def _redact(text, limit=MESSAGE_LIMIT):
    """One line, home path masked, bounded. Journal lines reach the shared report folder through the
    heartbeat and leave this Mac in a diagnostics export, so they are redacted where they are written."""
    from .reports import redact_home   # lazy: reports reaches back into this module for the heartbeat
    return redact_home(' · '.join(str(text).split('\n')).strip())[:limit]


def meeting_key(mid):
    """A meeting id is not content, but it still names one meeting and the journal travels. Eight hex
    characters tell two failures apart and say nothing to anyone else."""
    return hashlib.sha256(str(mid).encode('utf-8')).hexdigest()[:8] if mid else None


def _small(value):
    """One context value: a number, a flag, a short redacted string, or a short list of them. Anything
    else (a dict, a payload, a transcript) is dropped rather than trimmed."""
    if isinstance(value, bool): return value
    if isinstance(value, int): return value
    if isinstance(value, float): return value if math.isfinite(value) else None
    if isinstance(value, str): return _redact(value, CONTEXT_TEXT) or None
    if isinstance(value, (list, tuple)):
        return [item for item in (_redact(str(v), 80) for v in list(value)[:CRASH_FRAMES]) if item] or None
    return None


def _context(context):
    if not isinstance(context, dict): return {}
    out = {}
    for key, value in list(context.items())[:CONTEXT_KEYS]:
        small = _small(value)
        if small is None: continue
        name = _redact(str(key), 40)
        if name: out[name] = small
    return out


def journal_path(data_dir): return Path(data_dir) / JOURNAL_FILE
def state_path(data_dir): return Path(data_dir) / STATE_FILE


def _parse(value):
    try: stamp = datetime.fromisoformat(value)
    except (TypeError, ValueError): return None
    return stamp if stamp.tzinfo else stamp.replace(tzinfo=timezone.utc)


def _load_state(data_dir):
    try:
        state = json.loads(state_path(data_dir).read_text(encoding='utf-8'))
        return state if isinstance(state, dict) else {}
    except (OSError, ValueError): return {}


def _save_state(data_dir, state):
    try:
        path = state_path(data_dir)
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, PRIVATE_MODE)
        try: os.write(fd, json.dumps(state, ensure_ascii=False).encode('utf-8'))
        finally: os.close(fd)
    except (OSError, ValueError, TypeError): pass


def entries(data_dir, limit=200):
    """The last `limit` journal lines, oldest first. Never raises; an unreadable line is skipped."""
    try: raw = journal_path(data_dir).read_text(encoding='utf-8', errors='replace').splitlines()
    except (OSError, ValueError): return []
    out = []
    for line in raw[-max(1, int(limit)):]:
        try: entry = json.loads(line)
        except ValueError: continue
        if isinstance(entry, dict) and entry.get('kind') in KINDS: out.append(entry)
    return out


def _recent(data_dir, kind, message, moment):
    """True when this exact event is already in the journal from the last ten minutes. A banner that a
    poll re-sets every two seconds must leave one line, not eighteen hundred."""
    for entry in reversed(entries(data_dir, limit=200)):
        if entry.get('kind') != kind or entry.get('message') != message: continue
        stamp = _parse(entry.get('time'))
        return stamp is not None and abs((moment - stamp).total_seconds()) < DEDUPE_SECONDS
    return False


def _rotate(path):
    try:
        if path.is_file() and path.stat().st_size >= MAX_BYTES: path.replace(path.with_name(ROTATED_FILE))
    except OSError: pass


def record(kind, message, *, context=None, data_dir=None, now=None):
    """Append one event. Never raises and never returns anything the caller has to handle: failing to write
    the journal must not break the thing that was already failing."""
    try:
        data = Path(data_dir) if data_dir is not None else _default_data_dir()
        if data is None: return None
        kind = kind if kind in KINDS else 'ui'
        message = _redact(message)
        if not message: return None
        moment = _now(now)
        if _recent(data, kind, message, moment): return None
        entry = {'time': moment.isoformat(), 'kind': kind, 'message': message,
                 'context': _context(context), 'version': _version()}
        line = json.dumps(entry, ensure_ascii=False, allow_nan=False) + '\n'
        path = journal_path(data)
        data.mkdir(parents=True, exist_ok=True, mode=0o700)
        _rotate(path)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND | os.O_NOFOLLOW, PRIVATE_MODE)
        try: os.write(fd, line.encode('utf-8'))   # one O_APPEND write: two jobs never interleave a line
        finally: os.close(fd)
        try:
            if (path.stat().st_mode & 0o777) != PRIVATE_MODE: path.chmod(PRIVATE_MODE)
        except OSError: pass
        return entry
    except Exception: return None


def summary(data_dir, *, limit=5, now=None):
    """What the heartbeat and the settings card show: counts by kind over the last day, the newest few
    messages (newest first) and how many of them were crashes."""
    moment = _now(now); horizon = moment - timedelta(hours=WINDOW_HOURS)
    rows = entries(data_dir, limit=READ_LIMIT)
    counts = {}; crashes = 0
    for entry in rows:
        stamp = _parse(entry.get('time'))
        if stamp is None or stamp < horizon: continue
        counts[entry['kind']] = counts.get(entry['kind'], 0) + 1
        if entry['kind'] == 'crash': crashes += 1
    last = [{'time': e.get('time'), 'kind': e.get('kind'), 'message': e.get('message')} for e in rows[-limit:]][::-1]
    return {'last_24h': counts, 'last': last, 'crashes_24h': crashes}


def clear(data_dir):
    """Empty the journal. The watermark file stays: a cleared crash must not be collected again."""
    removed = []
    for name in (JOURNAL_FILE, ROTATED_FILE):
        path = Path(data_dir) / name
        try:
            if path.is_file(): path.unlink(); removed.append(name)
        except OSError: pass
    return removed


def _frames(body):
    """The top frames of the thread that died, ours only, function names only. Addresses say nothing here
    and the report itself is never copied."""
    images = body.get('usedImages') if isinstance(body.get('usedImages'), list) else []
    names = [str(i.get('name') or '') if isinstance(i, dict) else '' for i in images]
    threads = [t for t in (body.get('threads') if isinstance(body.get('threads'), list) else []) if isinstance(t, dict)]
    faulting = body.get('faultingThread')
    chosen = next((t for i, t in enumerate(threads) if t.get('triggered') or i == faulting), threads[0] if threads else {})
    out = []
    for frame in chosen.get('frames') or []:
        if not isinstance(frame, dict): continue
        index = frame.get('imageIndex')
        image = names[index] if isinstance(index, int) and not isinstance(index, bool) and 0 <= index < len(names) else ''
        if not image or not image.startswith(CRASH_IMAGES): continue
        symbol = str(frame.get('symbol') or '')[:80]
        out.append(f'{image}: {symbol}' if symbol else image)
        if len(out) >= CRASH_FRAMES: break
    return out


def parse_crash(path):
    """One `.ips`: a JSON header line, then a JSON body. Only the fields that say what died and where."""
    try: raw = Path(path).read_text(encoding='utf-8', errors='replace')
    except OSError: return None
    head, _, rest = raw.partition('\n')
    try: header, body = json.loads(head), json.loads(rest)
    except ValueError: return None
    if not isinstance(header, dict) or not isinstance(body, dict): return None
    exception = body.get('exception') if isinstance(body.get('exception'), dict) else {}
    termination = body.get('termination') if isinstance(body.get('termination'), dict) else {}
    def text(value, limit=40): return (str(value)[:limit] if value else None) or None
    return {'process': text(body.get('procName') or header.get('app_name') or header.get('name') or '?', 60),
            'version': text(header.get('app_version') or header.get('build_version')),
            'incident': text(header.get('incident_id') or body.get('incident')),
            'time': text(header.get('timestamp') or body.get('captureTime')),
            'exception': text(exception.get('type')),
            'signal': text(exception.get('signal')),
            'termination': text(termination.get('indicator') or termination.get('reason') or termination.get('namespace'), 80),
            'frames': _frames(body)}


def crash_message(crash):
    """The minute is part of the line on purpose: two different crashes of the same process minutes apart
    are two events, and the ten-minute dedupe would otherwise swallow the second."""
    parts = [f"{crash['process']} çöktü"]
    fault = '/'.join(p for p in (crash.get('exception'), crash.get('signal')) if p)
    if fault: parts.append(fault)
    if crash.get('termination'): parts.append(crash['termination'])
    if crash.get('time'): parts.append(crash['time'][:16])
    return ' · '.join(parts)


def collect_crashes(data_dir, *, directory=None, now=None):
    """macOS already writes a crash report for a process that died; nothing in this app ever read one.
    Everything newer than the stored watermark is summarised into the journal once, and only ours."""
    folder = Path(directory) if directory is not None else DIAGNOSTIC_REPORTS
    recorded = []
    try:
        if not folder.is_dir(): return recorded
        state = _load_state(data_dir)
        watermark = state.get('crash_mtime') if isinstance(state.get('crash_mtime'), (int, float)) and not isinstance(state.get('crash_mtime'), bool) else 0.0
        seen = [s for s in (state.get('crash_seen') or []) if isinstance(s, str)]
        known = len(seen); newest = watermark
        candidates = []
        for path in folder.glob('*.ips'):
            if not path.name.startswith(CRASH_PREFIXES): continue
            try: mtime = path.stat().st_mtime
            except OSError: continue
            if mtime <= watermark: continue
            candidates.append((mtime, str(path)))
        for mtime, name in sorted(candidates)[-CRASH_BATCH:]:
            newest = max(newest, mtime)
            crash = parse_crash(name)
            if not crash: continue
            key = crash.get('incident') or Path(name).name
            if key in seen: continue
            seen.append(key)
            entry = record('crash', crash_message(crash), data_dir=data_dir, now=now,
                           context={'process': crash['process'], 'bundle_version': crash['version'],
                                    'exception': crash['exception'], 'signal': crash['signal'],
                                    'termination': crash['termination'], 'frames': crash['frames']})
            if entry: recorded.append(entry)
        if newest != watermark or len(seen) != known:
            _save_state(data_dir, {**state, 'crash_mtime': newest, 'crash_seen': seen[-CRASH_MEMORY:]})
    except Exception: pass
    return recorded


def note_update_failure(data_dir):
    """scripts/update.sh already writes its verdict; a failed one reached nowhere a person would look.
    Imported once, keyed on the failure's own time, so an hourly sweep does not repeat it."""
    try:
        raw = json.loads((Path(data_dir) / UPDATE_STATUS_FILE).read_text(encoding='utf-8'))
        if not isinstance(raw, dict) or raw.get('state') != 'failed': return None
        stamp = str(raw.get('time') or '')
        state = _load_state(data_dir)
        if state.get('update_time') == stamp: return None
        entry = record('update', f"Güncelleme başarısız: {raw.get('message') or 'ayrıntı update.log'}",
                       context={'state': 'failed', 'time': stamp}, data_dir=data_dir)
        _save_state(data_dir, {**state, 'update_time': stamp})
        return entry
    except (OSError, ValueError): return None
    except Exception: return None


def sweep(data_dir, *, directory=None):
    """Everything the journal learns on its own rather than being told. App launch and hourly."""
    crashes = collect_crashes(data_dir, directory=directory)
    return {'crashes': len(crashes), 'update': bool(note_update_failure(data_dir))}
