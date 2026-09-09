"""Per-meeting diagnostic reports shared between Macs through a synced folder (iCloud Drive by default).

Allowlisted content only: sizes, counts, scores, costs, model names, error lines. Transcript text is
included only when the user turns that on. Reports let the development Mac follow what happens on the
Mac that is used for real meetings."""
import json
import platform
import re
import socket
from datetime import datetime, timezone
from pathlib import Path

SETTINGS_FILE = 'settings.json'
ICLOUD = Path.home() / 'Library/Mobile Documents/com~apple~CloudDocs'
DEFAULT_SUBDIR = 'MeetingOS-Reports'


def settings_path(data_dir): return Path(data_dir) / SETTINGS_FILE


def load_settings(data_dir):
    path = settings_path(data_dir)
    try: data = json.loads(path.read_text(encoding='utf-8')) if path.is_file() else {}
    except ValueError: data = {}
    if not isinstance(data, dict): data = {}
    defaults = {'share_reports': True, 'share_text': False, 'report_dir': str(ICLOUD / DEFAULT_SUBDIR) if ICLOUD.is_dir() else str(Path(data_dir) / DEFAULT_SUBDIR), 'auto_update': False}
    return {**defaults, **{k: v for k, v in data.items() if k in defaults}}


def save_settings(data_dir, changes):
    current = load_settings(data_dir)
    for key, value in (changes or {}).items():
        if key in ('share_reports', 'share_text', 'auto_update') and isinstance(value, bool): current[key] = value
        elif key == 'report_dir' and isinstance(value, str) and value.strip(): current[key] = value.strip()
    Path(data_dir).mkdir(parents=True, exist_ok=True)
    settings_path(data_dir).write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding='utf-8')
    return current


def host_dir(settings):
    return Path(settings['report_dir']) / socket.gethostname().split('.')[0]


def _errors(log_path, limit=8):
    if not Path(log_path).is_file(): return []
    out = []
    for line in Path(log_path).read_text(encoding='utf-8', errors='replace').splitlines()[-400:]:
        if line.startswith('Meeting OS:') or 'Traceback' in line or 'Error' in line:
            out.append(re.sub(r'/Users/[^ /]+', '/Users/…', line)[:240])
    return out[-limit:]


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
    report = {
        'report_version': 1, 'host': socket.gethostname().split('.')[0], 'macos': platform.mac_ver()[0], 'app_version': version, 'commit': commit,
        'written': datetime.now(timezone.utc).isoformat(), 'meeting': row['id'], 'title': row['title'], 'created': row['created'], 'status': row['status'],
        'engine': meta.get('engine'), 'model': meta.get('model'), 'cloud_mode': meta.get('cloud_mode'),
        'duration_seconds': round(max((r['end'] for r in rows), default=0.0), 1), 'segments': len(rows), 'words': sum(len((r.get('text') or '').split()) for r in rows),
        'pieces': len(chunks), 'pieces_paid': len(paid), 'pieces_skipped': sum(1 for u in chunks if isinstance(u, dict) and 'skipped' in u),
        'cost_usd': round(sum(float(u.get('cost') or 0) for u in paid), 5), 'uploaded_seconds': round(sum(float(u.get('seconds') or 0) for u in paid), 1),
        'echo_windows_skipped': meta.get('echo_windows_skipped'), 'echo_segments': meta.get('echo_segments'), 'identity': meta.get('identity'), 'identity_error': meta.get('identity_error'),
        'markers': len(meta.get('markers') or []), 'glossary_suggestions': len(meta.get('glossary_suggestions') or []),
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


def summarize(report_dir, limit=30):
    """Digest of every host's reports in the shared folder: newest first."""
    root = Path(report_dir)
    out = []
    if not root.is_dir(): return {'hosts': {}, 'reports': []}
    for path in sorted(root.glob('*/*.json'), key=lambda p: p.stat().st_mtime, reverse=True)[:limit]:
        try: r = json.loads(path.read_text(encoding='utf-8'))
        except ValueError: continue
        named = sum(1 for s in (r.get('speakers') or {}).values() if s.get('name'))
        out.append({'host': r.get('host'), 'file': path.name, 'title': r.get('title'), 'status': r.get('status'), 'duration_min': round((r.get('duration_seconds') or 0) / 60, 1), 'cost_usd': r.get('cost_usd'), 'model': r.get('model'),
                    'speakers': len(r.get('speakers') or {}), 'named': named, 'review': r.get('review_queue'), 'analysis': (r.get('analysis') or {}).get('counts'), 'errors': len(r.get('errors') or []), 'commit': r.get('commit'), 'app_version': r.get('app_version')})
    hosts = {}
    for r in out: hosts.setdefault(r['host'], {'reports': 0, 'errors': 0, 'cost_usd': 0.0}); hosts[r['host']]['reports'] += 1; hosts[r['host']]['errors'] += r['errors']; hosts[r['host']]['cost_usd'] = round(hosts[r['host']]['cost_usd'] + (r['cost_usd'] or 0), 4)
    return {'hosts': hosts, 'reports': out}
