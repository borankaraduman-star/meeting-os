"""Per-meeting diagnostic reports shared between Macs through a synced folder (iCloud Drive by default).

Allowlisted content only: sizes, counts, scores, costs, model names, error lines. Transcript text is
included only when the user turns that on. Reports let the development Mac follow what happens on the
Mac that is used for real meetings."""
import json
import math
import os
import platform
import re
import shutil
import socket
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from .capture_metrics import journal_events

SETTINGS_FILE = 'settings.json'
HEARTBEAT_FILE = 'heartbeat.json'
RECORDING_HEARTBEAT_FILE = 'recording-heartbeat.json'
RECORDING_HEARTBEAT_STALE_SECONDS = 300   # the recorder writes once a minute; older than this means it is gone, not quiet
CHUNK_SECONDS = 12.0            # MeetingCapture --chunk-seconds default; the expected chunk count comes from it
ICLOUD = Path.home() / 'Library/Mobile Documents/com~apple~CloudDocs'
DEFAULT_SUBDIR = 'MeetingOS-Reports'


REAL_DATA_DIR = Path.home() / 'Library/Application Support/MeetingOS'
DEFAULT_USER_NAME = 'Boran'   # the label every segment recorded before this setting existed carries; a teammate overwrites it on first run
NAME_LIMIT = 40


def default_report_dir(data_dir):
    """iCloud Drive only for the real data folder; any other folder (tests, private copies) stays local."""
    try: is_real = Path(data_dir).resolve() == REAL_DATA_DIR.resolve()
    except OSError: is_real = False
    return str(ICLOUD / DEFAULT_SUBDIR) if is_real and ICLOUD.is_dir() else str(Path(data_dir) / DEFAULT_SUBDIR)


def settings_path(data_dir): return Path(data_dir) / SETTINGS_FILE


def load_settings(data_dir):
    path = settings_path(data_dir)
    try: data = json.loads(path.read_text(encoding='utf-8')) if path.is_file() else {}
    except ValueError: data = {}
    if not isinstance(data, dict): data = {}
    # auto_retry: when OpenRouter was down, pick the meeting up again while the Mac is idle. On by default —
    # a meeting the cloud refused is otherwise a meeting the user has to remember.
    defaults = {'share_reports': True, 'share_text': False, 'report_dir': default_report_dir(data_dir), 'auto_update': False, 'audio_retention_days': 30, 'auto_retry': True,
                'user_name': DEFAULT_USER_NAME, 'team_dir': '', 'share_glossary': True}
    return {**defaults, **{k: v for k, v in data.items() if k in defaults}}


def save_settings(data_dir, changes):
    current = load_settings(data_dir)
    for key, value in (changes or {}).items():
        if key in ('share_reports', 'share_text', 'auto_update', 'auto_retry', 'share_glossary') and isinstance(value, bool): current[key] = value
        elif key == 'audio_retention_days' and isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= 3650: current[key] = value
        elif key == 'report_dir' and isinstance(value, str) and value.strip(): current[key] = value.strip()
        elif key == 'user_name' and isinstance(value, str) and 0 < len(value.strip()) <= NAME_LIMIT: current[key] = value.strip()
        # An unreachable team folder is refused rather than stored: the app would silently stop sharing.
        elif key == 'team_dir' and isinstance(value, str) and (not value.strip() or Path(value.strip()).expanduser().is_dir()): current[key] = value.strip()
    Path(data_dir).mkdir(parents=True, exist_ok=True)
    settings_path(data_dir).write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding='utf-8')
    return current


def settings_owner(data_dir):
    """Who this Mac belongs to. One lookup for every place that used to say “Boran”: the microphone speaker
    label, the “Bana ait” task filter, the digest and the waiting board. Falls back to the historical label so
    an existing database whose mic segments say “Boran” keeps matching."""
    name = load_settings(data_dir).get('user_name')
    return name.strip() if isinstance(name, str) and name.strip() else DEFAULT_USER_NAME


def host_name():
    """Stable, file-safe Mac name (System Settings → local hostname); falls back to the network hostname."""
    import subprocess
    try:
        name = subprocess.run(['scutil', '--get', 'LocalHostName'], capture_output=True, text=True, timeout=3).stdout.strip()
        if name: return name
    except (OSError, subprocess.TimeoutExpired): pass
    return socket.gethostname().split('.')[0]


def team_dir(settings):
    """The shared team folder, or None. iCloud Drive is per-Apple-ID, so teammates need an ordinary folder
    (a shared drive, Dropbox, a network volume) that every Mac can see."""
    team = (settings.get('team_dir') or '').strip()
    return Path(team).expanduser() if team else None


def report_root(settings):
    """Where this Mac writes its diagnostic reports. A team folder REPLACES the personal report folder rather
    than doubling the write: one destination keeps `summarize`, deletion and the setup card consistent.
    Reports written earlier stay where they were."""
    team = team_dir(settings)
    return team / 'reports' if team else Path(settings['report_dir'])


def host_dir(settings):
    return report_root(settings) / host_name()


def _errors(log_path, limit=8):
    if not Path(log_path).is_file(): return []
    out = []
    for line in Path(log_path).read_text(encoding='utf-8', errors='replace').splitlines()[-400:]:
        if line.startswith('Meeting OS:') or 'Traceback' in line or 'Error' in line:
            out.append(re.sub(r'/Users/[^ /]+', '/Users/…', line)[:240])
    return out[-limit:]


def recording_line(beat):
    """One line for a recording that is happening right now: 'kayıt sürüyor · 41 dk · son parça 4 sn önce'."""
    if not isinstance(beat, dict): return None
    seconds = beat.get('elapsed_seconds')
    seconds = float(seconds) if isinstance(seconds, (int, float)) else 0.0
    parts = ['kayıt sürüyor', f'{int(seconds//60)} dk' if seconds >= 60 else f'{int(seconds)} sn']
    age = beat.get('last_chunk_age_seconds')
    parts.append(f'son parça {int(age)} sn önce' if isinstance(age, (int, float)) else 'henüz parça yok')
    if beat.get('relaunches'): parts.append(f"{beat['relaunches']} kez yeniden başlatıldı")
    elif beat.get('restarts'): parts.append(f"{beat['restarts']} kez ses akışı yenilendi")
    lost = (beat.get('gap_seconds') or 0) + (beat.get('wake_gap_seconds') or 0)
    if lost >= 1: parts.append(f'{int(round(lost))} sn boşluk')
    return ' · '.join(parts)


def write_recording_heartbeat(data_dir, state):
    """Overwrite <report_dir>/<host>/recording-heartbeat.json while a recording runs, so 'reports heartbeat' and
    the shared folder answer 'is it still recording?' without touching the meeting database. At most once a
    minute from the recorder's own drain loop; never raises, and never writes when sharing is off."""
    try:
        settings = load_settings(data_dir)
        if not settings.get('share_reports'): return None
        folder = host_dir(settings); folder.mkdir(parents=True, exist_ok=True)
        payload = {'recording_heartbeat_version': 1, 'host': host_name(), 'written': datetime.now(timezone.utc).isoformat(), **state}
        payload['line'] = recording_line(payload)
        target = folder / RECORDING_HEARTBEAT_FILE
        target.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding='utf-8')
        return str(target)
    except Exception: return None


def clear_recording_heartbeat(data_dir):
    """The recording ended: remove the file rather than leave a line that says a meeting is still being taped."""
    try:
        (host_dir(load_settings(data_dir)) / RECORDING_HEARTBEAT_FILE).unlink(missing_ok=True)
    except Exception: pass


def read_recording_heartbeat(source):
    """The live recording state a folder claims, or None when there is none or it is too old to trust."""
    path = Path(source)
    if path.is_dir(): path = path / RECORDING_HEARTBEAT_FILE
    try: beat = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError): return None
    if not isinstance(beat, dict): return None
    try: age = (datetime.now(timezone.utc) - datetime.fromisoformat(beat['written'])).total_seconds()
    except (KeyError, TypeError, ValueError): return None
    if age > RECORDING_HEARTBEAT_STALE_SECONDS or age < -RECORDING_HEARTBEAT_STALE_SECONDS: return None
    beat['age_seconds'] = round(age, 1)
    return beat


def capture_block(directory, duration_seconds=0.0):
    """Numbers only from a meeting's capture folder: chunk files per source against the count the duration
    implies, the capture journal's gap/error events, and the assembled *-full.* sizes. The journal records
    'gap' (a discontinuity between two chunks) and 'error'; there is no dropped-frame event. Never raises."""
    try:
        if not isinstance(directory, str) or not directory: return None
        root = Path(directory)
        if not root.is_dir(): return None
        chunks = {}; full = {}
        for p in root.glob('*-full.*'):   # audio_archive writes FLAC, the capture tool WAV
            try: full[p.name.split('-full.')[0]] = p.stat().st_size
            except OSError: pass
        for p in root.glob('*.wav'):
            found = re.fullmatch(r'([A-Za-z]+)-\d{6}\.wav', p.name)
            if found: chunks[found.group(1)] = chunks.get(found.group(1), 0) + 1
        journal = root/'capture-native.jsonl'
        if not journal.is_file(): journal = root/'events.jsonl'
        gaps = 0; announced = {}
        events = journal_events(journal)
        for event in events:
            kind = event.get('event')
            if kind == 'gap': gaps += 1
            elif kind == 'chunk' and isinstance(event.get('source'), str):
                announced[event['source']] = announced.get(event['source'], 0) + 1
        from .capture_metrics import capture_health
        health = capture_health(events)
        expected = math.ceil(float(duration_seconds or 0)/CHUNK_SECONDS)
        # restarts/relaunches/wakes are how the owner sees, after the fact, that the recording survived something.
        return {'chunk_files': chunks, 'announced_chunks': announced, 'expected_chunks': expected, 'chunk_seconds': CHUNK_SECONDS,
                'gaps': gaps, 'full_bytes': full, 'journal': journal.name if journal.is_file() else None, **health}
    except Exception:  # a report must never fail on a folder that is being written
        return None


def build_meeting_report(store, mid, data_dir, *, include_text=False, version=None, commit=None):
    row = store.db.execute('SELECT id,title,status,created,metadata FROM meetings WHERE id=?', (mid,)).fetchone()
    if not row: raise ValueError('Toplantı bulunamadı')
    meta = json.loads(row['metadata'] or '{}')
    rows = store.segments(mid)
    chunks = [json.loads(u[0]) for u in store.db.execute('SELECT usage FROM cloud_chunks WHERE meeting=? ORDER BY position', (mid,))] if store.db.execute("SELECT name FROM sqlite_master WHERE name='cloud_chunks'").fetchone() else []
    paid = [u for u in chunks if isinstance(u, dict) and 'cost' in u]
    speakers = {}
    for r in rows:
        if r['source'] != 'system': continue
        sp = speakers.setdefault(r['speaker'], {'segments': 0, 'seconds': 0.0, 'name': r.get('speaker_name'), 'clusters': set(), 'similarity': None, 'suggested': None})
        sp['segments'] += 1; sp['seconds'] += float(r['end'] - r['start']); sp['clusters'].add((r.get('metrics') or {}).get('cluster'))
        ident = (r.get('metrics') or {}).get('identity') or {}
        if ident.get('similarity') is not None: sp['similarity'] = round(float(ident['similarity']), 3); sp['suggested'] = ident.get('suggested')
    for sp in speakers.values(): sp['clusters'] = len(sp['clusters']); sp['seconds'] = round(sp['seconds'], 1)
    from .review import review_queue
    from .quality import identity_report
    queue = review_queue(store, mid)
    kinds = {}
    for item in queue['items']: kinds[item['kind']] = kinds.get(item['kind'], 0) + 1
    analysis = store.db.execute('SELECT model,payload,created FROM analyses WHERE meeting=? ORDER BY id DESC LIMIT 1', (mid,)).fetchone()
    analysis_summary = None
    if analysis:
        payload = json.loads(analysis['payload'])
        analysis_summary = {'model': analysis['model'], 'counts': {k: len(payload.get(k, [])) for k in ('summary', 'decisions', 'risks', 'questions', 'actions')}, 'coverage': payload.get('coverage'), 'dropped_quotes': payload.get('dropped_quotes'), 'created': analysis['created']}
    duration = round(max((r['end'] for r in rows), default=0.0), 1)
    report = {
        'report_version': 1, 'host': host_name(), 'macos': platform.mac_ver()[0], 'app_version': version, 'commit': commit,
        'written': datetime.now(timezone.utc).isoformat(), 'meeting': row['id'], 'title': row['title'], 'created': row['created'], 'status': row['status'],
        'engine': meta.get('engine'), 'model': meta.get('model'), 'cloud_mode': meta.get('cloud_mode'),
        'duration_seconds': duration, 'segments': len(rows), 'words': sum(len((r.get('text') or '').split()) for r in rows),
        'capture': capture_block(meta.get('capture_dir'), duration),
        'pieces': len(chunks), 'pieces_paid': len(paid), 'pieces_skipped': sum(1 for u in chunks if isinstance(u, dict) and 'skipped' in u),
        'cost_usd': round(sum(float(u.get('cost') or 0) for u in paid), 5), 'uploaded_seconds': round(sum(float(u.get('seconds') or 0) for u in paid), 1),
        'echo_windows_skipped': meta.get('echo_windows_skipped'), 'echo_segments': meta.get('echo_segments'), 'identity': meta.get('identity'), 'identity_error': meta.get('identity_error'),
        'markers': len(meta.get('markers') or []), 'glossary_suggestions': len(meta.get('glossary_suggestions') or []),
        'job_usage': meta.get('job_usage'),
        'speakers': speakers, 'review_queue': kinds, 'analysis': analysis_summary, 'scorecard': identity_report(store), 'errors': _errors(Path(data_dir) / 'last-job.log'),
    }
    if include_text:
        report['transcript'] = [{'start': r['start'], 'speaker': r.get('speaker_name') or r['speaker'], 'text': r.get('text')} for r in rows]
    return report


def write_meeting_report(store, mid, data_dir, *, version=None, commit=None):
    """Write <report_dir>/<host>/<created-date>_<meeting>.json when sharing is on. Never raises into the caller."""
    try:
        settings = load_settings(data_dir)
        if not settings.get('share_reports'): return None
        report = build_meeting_report(store, mid, data_dir, include_text=bool(settings.get('share_text')), version=version, commit=commit)
        folder = host_dir(settings); folder.mkdir(parents=True, exist_ok=True)
        target = folder / f"{report['created'][:10]}_{mid}.json"
        target.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding='utf-8')
        return str(target)
    except Exception as exc:  # reporting must never break a job
        import sys; print(f'Rapor yazılamadı: {type(exc).__name__}', file=sys.stderr); return None


def _thermal():
    """CPU_Speed_Limit from `pmset -g therm`: 100 means no throttling. None when unavailable."""
    try: out = subprocess.run(['/usr/bin/pmset', '-g', 'therm'], capture_output=True, text=True, timeout=3).stdout
    except (OSError, subprocess.SubprocessError): return None
    found = re.search(r'CPU_Speed_Limit\s*=\s*(\d+)', out or '')
    return int(found.group(1)) if found else None


def _memory_pressure():
    """resources.py exposes no level reader, only the admission check; report what that check sees."""
    from . import resources
    reader = getattr(resources, 'pressure_level', None) or getattr(resources, 'memory_pressure', None)
    if callable(reader):
        try: return reader()
        except Exception: return None
    try: resources.check_pressure(); return 'normal'
    except resources.MemoryPressureError: return 'pressure'
    except Exception: return None


def build_heartbeat(store, data_dir, *, app=None):
    """This Mac's current state, independent of any single meeting: counts, sizes, disk, thermal, errors."""
    from .desktop import folder_bytes   # the bridge owns the one copy; importing it here keeps this module light
    data = Path(data_dir)
    version = commit = None
    if isinstance(app, dict): version, commit = app.get('version'), app.get('commit')
    elif isinstance(app, str): version = app
    statuses = {row[0]: row[1] for row in store.db.execute('SELECT status,count(*) FROM meetings GROUP BY status')}
    last = store.db.execute("SELECT max(created) FROM meetings WHERE status='complete'").fetchone()[0]
    db_path = Path(getattr(store, 'path', data/'meeting-os.sqlite'))
    database = sum(p.stat().st_size for p in (db_path, Path(str(db_path)+'-wal'), Path(str(db_path)+'-shm')) if p.is_file())
    try: free = shutil.disk_usage(data if data.is_dir() else data.parent).free
    except OSError: free = None
    try: load = [round(v, 2) for v in os.getloadavg()]
    except OSError: load = None
    return {
        'heartbeat_version': 1, 'host': host_name(), 'macos': platform.mac_ver()[0], 'app_version': version, 'commit': commit,
        'written': datetime.now(timezone.utc).isoformat(), 'meetings': sum(statuses.values()), 'statuses': statuses, 'last_complete': last,
        'sizes': {'recordings': folder_bytes(data/'recordings'), 'imports': folder_bytes(data/'imports'), 'database': database, 'free_disk': free},
        'memory_pressure': _memory_pressure(), 'thermal': _thermal(), 'load_average': load,
        'recording': read_recording_heartbeat(host_dir(load_settings(data_dir))),   # a meeting being taped right now
        'errors': _errors(data/'last-job.log', limit=5),
        'cloud_blocked': store.db.execute("SELECT count(*) FROM meetings WHERE status!='complete' AND json_extract(metadata,'$.cloud_error.kind') IN ('auth','credit')").fetchone()[0],
        'probe': daily_probe(data),
    }


PROBE_CACHE = 'probe-last.json'
PROBE_EVERY_SECONDS = 24*3600


def daily_probe(data_dir, *, now=None, force=False):
    """The self-test, at most once a day, riding the hourly heartbeat: the other Mac learns overnight that this
    one cannot record tomorrow, instead of the user learning it in the meeting. Cached; never runs while a
    recording heartbeat is live."""
    data = Path(data_dir); cache = data / PROBE_CACHE
    now = now or datetime.now(timezone.utc)
    try:
        last = json.loads(cache.read_text(encoding='utf-8'))
        if not force and (now - datetime.fromisoformat(last['at'])).total_seconds() < PROBE_EVERY_SECONDS: return last
    except (OSError, ValueError, KeyError, TypeError): last = None
    if not force and read_recording_heartbeat(host_dir(load_settings(data_dir))): return last
    try:
        from .probe import run, summary_line
        from .cli import ROOT
        result = run(ROOT, data)
        last = {'ok': result['ok'], 'failed': result['failed'], 'warnings': result['warnings'], 'summary': summary_line(result), 'at': result['at']}
        cache.write_text(json.dumps(last, ensure_ascii=False), encoding='utf-8')
    except Exception as exc:  # observability must never break the app
        last = {'ok': False, 'failed': ['probe'], 'warnings': [], 'summary': f'Öz-test çalıştırılamadı: {type(exc).__name__}', 'at': now.isoformat()}
    return last


def write_heartbeat(store, data_dir, *, app=None):
    """Overwrite <report_dir>/<host>/heartbeat.json when sharing is on, so the other Mac sees this one is
    alive and how it is doing without waiting for a meeting. One file per host, never per day. Never raises."""
    try:
        settings = load_settings(data_dir)
        if not settings.get('share_reports'): return None
        folder = host_dir(settings); folder.mkdir(parents=True, exist_ok=True)
        target = folder / HEARTBEAT_FILE
        target.write_text(json.dumps(build_heartbeat(store, data_dir, app=app), ensure_ascii=False, indent=1), encoding='utf-8')
        return str(target)
    except Exception as exc:  # observability must never break the app
        import sys; print(f'Nabız yazılamadı: {type(exc).__name__}', file=sys.stderr); return None


def remove_meeting_report(mid, data_dir):
    """Delete this host's report for a meeting that was deleted, so the shared folder mirrors the app. Never raises."""
    removed = []
    try:
        folder = host_dir(load_settings(data_dir))
        if folder.is_dir():
            for path in folder.glob(f'*_{mid}.json'):
                path.unlink(); removed.append(str(path))
    except Exception as exc:
        import sys; print(f'Rapor silinemedi: {type(exc).__name__}', file=sys.stderr)
    return removed


def summarize(report_dir, limit=30):
    """Digest of every host's reports in the shared folder: newest first."""
    root = Path(report_dir)
    out = []
    if not root.is_dir(): return {'hosts': {}, 'reports': []}
    files = [p for p in root.glob('*/*.json') if p.name not in (HEARTBEAT_FILE, RECORDING_HEARTBEAT_FILE)]
    for path in sorted(files, key=lambda p: p.stat().st_mtime, reverse=True)[:limit]:
        try: r = json.loads(path.read_text(encoding='utf-8'))
        except ValueError: continue
        named = sum(1 for s in (r.get('speakers') or {}).values() if s.get('name'))
        out.append({'host': r.get('host'), 'file': path.name, 'title': r.get('title'), 'status': r.get('status'), 'duration_min': round((r.get('duration_seconds') or 0) / 60, 1), 'cost_usd': r.get('cost_usd'), 'model': r.get('model'),
                    'speakers': len(r.get('speakers') or {}), 'named': named, 'review': r.get('review_queue'), 'analysis': (r.get('analysis') or {}).get('counts'), 'errors': len(r.get('errors') or []), 'commit': r.get('commit'), 'app_version': r.get('app_version')})
    hosts = {}
    for r in out: hosts.setdefault(r['host'], {'reports': 0, 'errors': 0, 'cost_usd': 0.0}); hosts[r['host']]['reports'] += 1; hosts[r['host']]['errors'] += r['errors']; hosts[r['host']]['cost_usd'] = round(hosts[r['host']]['cost_usd'] + (r['cost_usd'] or 0), 4)
    for path in sorted(root.glob('*/'+HEARTBEAT_FILE)):   # a host that has written no report can still be alive
        try: beat = json.loads(path.read_text(encoding='utf-8'))
        except (OSError, ValueError): continue
        if not isinstance(beat, dict): continue
        host = beat.get('host') or path.parent.name
        hosts.setdefault(host, {'reports': 0, 'errors': 0, 'cost_usd': 0.0})
        hosts[host]['heartbeat'] = {'last_seen': beat.get('written'), 'free_disk': (beat.get('sizes') or {}).get('free_disk'), 'thermal': beat.get('thermal'),
                                    'memory_pressure': beat.get('memory_pressure'), 'meetings': beat.get('meetings'), 'app_version': beat.get('app_version'),
                                    'probe': beat.get('probe'), 'cloud_blocked': beat.get('cloud_blocked'), 'errors': len(beat.get('errors') or [])}
    for path in sorted(root.glob('*/'+RECORDING_HEARTBEAT_FILE)):   # a Mac that is in a meeting right now says so
        beat = read_recording_heartbeat(path)
        if not beat: continue
        host = beat.get('host') or path.parent.name
        hosts.setdefault(host, {'reports': 0, 'errors': 0, 'cost_usd': 0.0})
        hosts[host]['recording'] = {'line': beat.get('line') or recording_line(beat), 'meeting': beat.get('meeting'), 'elapsed_seconds': beat.get('elapsed_seconds'),
                                    'last_chunk_age_seconds': beat.get('last_chunk_age_seconds'), 'restarts': beat.get('restarts'), 'relaunches': beat.get('relaunches')}
    return {'hosts': hosts, 'reports': out, 'alerts': alerts(hosts)}


STALE_HEARTBEAT_SECONDS = 3*24*3600
LOW_DISK_BYTES = 3*1024**3


def alerts(hosts, *, now=None):
    """What the person maintaining the fleet should look at today, one Turkish line each. Derived only from the
    shared folder, so it works on the dev Mac without touching the other machines."""
    now = now or datetime.now(timezone.utc); out = []
    for host, h in sorted(hosts.items()):
        beat = h.get('heartbeat') or {}
        seen = beat.get('last_seen')
        if seen:
            try:
                age = (now - datetime.fromisoformat(seen)).total_seconds()
                if age > STALE_HEARTBEAT_SECONDS: out.append({'host': host, 'level': 'warning', 'key': 'stale', 'line': f'{host}: {int(age//86400)} gündür nabız yok · uygulama açık mı, güncelleme takıldı mı?'})
            except ValueError: pass
        elif h.get('reports'): out.append({'host': host, 'level': 'note', 'key': 'no_heartbeat', 'line': f'{host}: rapor var ama nabız dosyası yok · 1.2.15 öncesi sürüm olabilir'})
        free = beat.get('free_disk')
        if isinstance(free, (int, float)) and free < LOW_DISK_BYTES: out.append({'host': host, 'level': 'error', 'key': 'disk', 'line': f'{host}: disk {free/1024**3:.1f} GB boş · kayıt 400 MB altında durur; eski sesleri temizleyin'})
        probe = beat.get('probe') or {}
        if probe and not probe.get('ok'): out.append({'host': host, 'level': 'error', 'key': 'probe', 'line': f'{host}: {probe.get("summary") or "öz-test başarısız"}'})
        elif probe.get('warnings'): out.append({'host': host, 'level': 'warning', 'key': 'probe', 'line': f'{host}: {probe.get("summary")}'})
        blocked = beat.get('cloud_blocked')
        if isinstance(blocked, int) and blocked > 0: out.append({'host': host, 'level': 'error', 'key': 'cloud', 'line': f'{host}: {blocked} toplantı bulutta bekliyor (anahtar/kredi) · kişi Ayarlar → OpenRouter’a bakmalı'})
        if beat.get('memory_pressure') not in (None, 0, 1, 'normal'): out.append({'host': host, 'level': 'warning', 'key': 'memory', 'line': f'{host}: bellek baskısı {beat.get("memory_pressure")} · yerel işler durur, bulut işleri sürer'})
        rec = h.get('recording') or {}
        age = rec.get('last_chunk_age_seconds')
        if isinstance(age, (int, float)) and age > 60: out.append({'host': host, 'level': 'error', 'key': 'recording', 'line': f'{host}: kayıt sürüyor ama son parça {int(age)} sn önce · yardımcı takılmış olabilir'})
        if h.get('errors'): out.append({'host': host, 'level': 'note', 'key': 'errors', 'line': f'{host}: son raporlarda {h["errors"]} hata satırı'})
    return out
