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
import tempfile
from datetime import datetime, timedelta, timezone
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
LEGACY_DEFAULT_NAME = 'Boran'   # what 1.2.42 and earlier persisted without anyone typing it
DEFAULT_USER_NAME = ''   # nobody by default: a name typed into Settings is the only thing that labels a mic row with a person
NAME_LIMIT = 40
# The mic labels a database can already carry before its owner typed a name: the source fallback
# cloud_finalize uses today, and the personal default this app shipped with until 1.2.42.
LEGACY_MIC_LABELS = ('Ben', 'Boran')


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
    # text_retention_days is OFF by default (0): audio can be re-derived from nothing, but a transcript is the
    # meeting. A user who wants a crisis-proof horizon sets one deliberately, up front — which is safer than
    # deciding to wipe everything on the day something happens.
    defaults = {'share_reports': True, 'share_text': False, 'report_dir': default_report_dir(data_dir), 'auto_update': False, 'audio_retention_days': 30, 'text_retention_days': 0, 'auto_retry': True,
                'user_name': DEFAULT_USER_NAME, 'user_name_confirmed': False, 'team_dir': '', 'team_url': '', 'share_glossary': True,
                # The team folder is one knowledge base, so both halves of it are on by default: a taught word and
                # a named voice are worth the same to everybody, and the way out is per row (a team word can be
                # switched off, a person's team samples deleted) rather than a switch nobody finds.
                'share_words': True, 'share_profiles': True,
                # Voice-matching bars. `None` means "the shipped constant" — which is what every install has
                # until the user runs `quality calibrate --apply` on their own measured evidence. Nothing here
                # is written by the app itself: a calibration only ever produces a recommendation.
                'identity_threshold': None, 'identity_margin': None,
                # 1.2.85: may a measured experiment APPLY itself? Off. The idle pass measures either way and
                # writes down what it found; with this off the setup card says "otomatik uygulama kapalı" and
                # the user applies it deliberately. Nothing about a local-only, reversible change makes it
                # safe to make on a Mac whose owner never asked for it.
                'auto_promote_policies': False}
    merged = {**defaults, **{k: v for k, v in data.items() if k in defaults}}
    # 1.2.42 and earlier wrote the old default 'Boran' into settings.json on any settings save, so a teammate's file
    # can carry a stranger's name nobody typed. Only a name saved through save_settings (confirmed) counts.
    if merged.get('user_name') == LEGACY_DEFAULT_NAME and not merged.get('user_name_confirmed'): merged['user_name'] = ''
    # The team cloud has no setting to switch on: when this Mac has a team token and the user has NOT picked a
    # team folder, the local mirror IS the team folder, and every caller of `team_dir` (report_root,
    # glossary.team_path, team_knowledge.shared_root) follows it without knowing a server exists. `_mirror` is
    # derived, never stored (`save_settings` drops it) and never shown in Ayarlar: `team_dir` stays ''.
    try:
        from . import team_cloud
        if not merged['team_dir'] and team_cloud.configured(merged, data_dir): merged['_mirror'] = str(team_cloud.mirror_dir(data_dir))
    except Exception: pass   # a broken token file must never make settings unreadable
    return merged


def save_settings(data_dir, changes):
    current = load_settings(data_dir)
    for key, value in (changes or {}).items():
        if key in ('share_reports', 'share_text', 'auto_update', 'auto_retry', 'share_glossary', 'share_words', 'share_profiles', 'auto_promote_policies') and isinstance(value, bool): current[key] = value
        elif key in ('audio_retention_days', 'text_retention_days') and isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= 3650: current[key] = value
        elif key == 'report_dir' and isinstance(value, str) and value.strip(): current[key] = value.strip()
        # An empty name is stored, not dropped: "" means nobody, and the mic rows keep the neutral 'Ben' label.
        elif key == 'user_name' and isinstance(value, str) and len(value.strip()) <= NAME_LIMIT:
            # An empty value never wipes a stored name by accident (a settings sheet that opened before the name
            # loaded used to do exactly that); clearing is explicit: {'user_name': '', 'user_name_clear': True}.
            if value.strip() or not current.get('user_name') or (changes or {}).get('user_name_clear') is True:
                current[key] = value.strip(); current['user_name_confirmed'] = bool(value.strip())
        # An unreachable team folder is refused rather than stored: the app would silently stop sharing.
        elif key == 'team_dir' and isinstance(value, str) and (not value.strip() or Path(value.strip()).expanduser().is_dir()): current[key] = value.strip()
        elif key == 'team_url' and isinstance(value, str): current[key] = value.strip()
        # The calibrated identity bars, validated against the shipped ranges. `None` clears the override and
        # puts the constant back; a number outside the range is refused rather than stored, so a hand-edited
        # settings file cannot turn recognition into "name everybody" or "name nobody".
        elif key in ('identity_threshold', 'identity_margin'):
            from .store import IDENTITY_MARGIN_RANGE, IDENTITY_THRESHOLD_RANGE
            low, high = IDENTITY_THRESHOLD_RANGE if key == 'identity_threshold' else IDENTITY_MARGIN_RANGE
            if value is None: current[key] = None
            elif isinstance(value, (int, float)) and not isinstance(value, bool) and low <= float(value) <= high: current[key] = round(float(value), 4)
    current.pop('_mirror', None)   # derived at load time; persisting it would turn the mirror into a picked folder
    Path(data_dir).mkdir(parents=True, exist_ok=True, mode=0o700)
    publish(settings_path(data_dir), json.dumps(current, ensure_ascii=False, indent=2))   # the report folder and the team folder live in here
    return current


def settings_owner(data_dir):
    """Who this Mac belongs to, or '' when nobody has said. One lookup for every place that needs the user's own
    name: the microphone speaker label, the “Bana ait” task filter, the digest and the waiting board.

    Empty is a real answer and every caller has to mean “no owner” by it — not “everyone” and not a guess.
    Guessing is what labelled a teammate's first meeting “Boran” forever."""
    name = load_settings(data_dir).get('user_name')
    return name.strip() if isinstance(name, str) and name.strip() else DEFAULT_USER_NAME


def store_owner(store):
    """The settings owner of the folder this database lives in, or ''. The read-only reports are handed a
    store and nothing else, but they still have to know whose microphone rows those are — the mic label is
    a person's name, and masking or a "mine" filter that misses it leaks or loses exactly one person: the user.
    Never raises: an unreadable settings file means no owner, which every caller already has to handle."""
    try:
        path = getattr(store, 'path', None)
        return settings_owner(Path(path).parent) if path else DEFAULT_USER_NAME
    except Exception: return DEFAULT_USER_NAME


def owner_rename_targets(old, new):
    """Which mic labels a change of `user_name` to `new` should relabel. The previous name when there was one;
    the labels a database carries when its owner never typed a name (the 'Ben' fallback, the old 'Boran'
    default) when there was not — a teammate's first meeting is recorded before they reach Settings."""
    old = (old or '').strip(); new = (new or '').strip()
    if not new: return []
    targets = [old] if old and old != new else []
    # The legacy labels are swept every time: a Mac that already had a name can still carry 'Boran'/'Ben' mic rows
    # from meetings recorded before the name was typed, and those words are the owner's own.
    targets += [name for name in LEGACY_MIC_LABELS if name != new and name not in targets]
    return targets


def rename_owner_segments(store, old, new):
    """Relabel the mic rows the previous owner name left behind, across every meeting, and move the tasks that
    were written from those rows onto the new name. Returns the counts, or None when there is nothing to do.
    Analyses of the touched meetings go stale on their own: the speaker string is part of the transcript
    fingerprint, and owner attribution is exactly what an analysis reads."""
    if store is None: return None
    segments = 0; tasks = 0; renamed = []; touched = set()
    for target in owner_rename_targets(old, new):
        try: result = store.rename_mic_owner(target, new)
        except Exception: continue   # a settings write must never fail on the relabel
        tasks += result.get('tasks') or 0
        if result['segments']:
            touched.update(result.get('meeting_ids') or []); segments += result['segments']; renamed.append(target)
    meetings = len(touched)
    return {'meetings': meetings, 'segments': segments, 'tasks': tasks, 'renamed_from': renamed} if segments or tasks else None


def save_settings_with_rename(store, data_dir, changes):
    """Save the settings, then relabel the mic rows a changed `user_name` left behind. The bridge and the CLI
    both do this and both have to return the same counts, so it is written once."""
    before = (load_settings(data_dir).get('user_name') or '').strip()
    saved = save_settings(data_dir, changes)
    # A name typed after the first meeting was already recorded has to reach that meeting too.
    renamed = rename_owner_segments(store, before, saved.get('user_name')) if (saved.get('user_name') or '').strip() != before else None
    return {**saved, 'renamed_meetings': (renamed or {}).get('meetings', 0), 'renamed_segments': (renamed or {}).get('segments', 0)}


def host_name():
    """Stable, file-safe Mac name (System Settings → local hostname); falls back to the network hostname."""
    import subprocess
    try:
        name = subprocess.run(['scutil', '--get', 'LocalHostName'], capture_output=True, text=True, timeout=3).stdout.strip()
        if name: return name
    except (OSError, subprocess.TimeoutExpired): pass
    return socket.gethostname().split('.')[0]


def team_dir(settings):
    """The shared team folder, or None. A folder the user picked wins (a NAS, a shared drive); otherwise the
    team cloud's local mirror (`_mirror`, added by `load_settings`), which the sync client keeps in step with
    the server. iCloud Drive is per-Apple-ID, so it was never a team answer at all."""
    team = (settings.get('team_dir') or '').strip()
    if team: return Path(team).expanduser()
    mirror = (settings.get('_mirror') or '').strip()
    return Path(mirror) if mirror else None


def report_root(settings):
    """Where this Mac writes its diagnostic reports. A team folder REPLACES the personal report folder rather
    than doubling the write: one destination keeps `summarize`, deletion and the setup card consistent.
    Reports written earlier stay where they were."""
    team = team_dir(settings)
    return team / 'reports' if team else Path(settings['report_dir'])


def host_dir(settings):
    return report_root(settings) / host_name()


PRIVATE_MODE = 0o600
SHARED_MODE = 0o644          # inside a team folder: a teammate has to be able to open the file
SHARED_DIR_MODE = 0o755


def publish(path, text, *, shared=False):
    """Write a file AT a mode. Path.write_text keeps whatever mode the file already had, so a report folder that
    was once world-readable stayed world-readable for the life of the Mac; a fresh temp file plus os.replace
    settles the mode on every write. Inside a team folder the mode is 0644 on purpose."""
    path = Path(path); temporary = None
    try:
        with tempfile.NamedTemporaryFile('w', encoding='utf-8', dir=path.parent, prefix='.'+path.name+'.', delete=False) as out:
            temporary = Path(out.name); os.fchmod(out.fileno(), SHARED_MODE if shared else PRIVATE_MODE)
            out.write(text); out.flush(); os.fsync(out.fileno())
        os.replace(temporary, path); temporary = None
    finally:
        if temporary is not None: temporary.unlink(missing_ok=True)
    return path


def prepare_folder(settings):
    """(folder, shared) for this host's report folder. mkdir's `mode` is masked by the umask, and the bridge runs
    under 077, so a team folder created that way came out 0700 and no teammate could list it. chmod says it
    outright, on the host folder and on the `reports` root above it."""
    # `shared` means "a folder other people open": a picked team folder, never the cloud mirror, which is this
    # Mac's own 0700 copy and reaches teammates through the sync client instead.
    folder = host_dir(settings); shared = bool((settings.get('team_dir') or '').strip())
    folder.mkdir(parents=True, exist_ok=True)
    for target in ((folder, folder.parent) if shared else (folder,)):
        try: target.chmod(SHARED_DIR_MODE if shared else 0o700)
        except OSError: pass   # a network volume or a synced folder may refuse; sharing still works
    return folder, shared


TIGHTEN_FILES = (SETTINGS_FILE, 'probe-last.json', 'last-job.log')


def tighten_modes(data_dir):
    """Pull the personal files back to 0600 and the data folder to 0700. Anything written before this Mac learned
    to publish at a fixed mode keeps its old, wider mode forever. The team folder is deliberately left alone."""
    data = Path(data_dir); fixed = []
    try:
        data.chmod(0o700); fixed.append(str(data))
    except OSError: pass
    try: personal = Path(load_settings(data_dir)['report_dir']) / host_name() / HEARTBEAT_FILE
    except Exception: personal = None
    for path in [data/name for name in TIGHTEN_FILES] + ([personal] if personal else []):
        try:
            if path.is_file() and (path.stat().st_mode & 0o777) != PRIVATE_MODE: path.chmod(PRIVATE_MODE); fixed.append(str(path))
        except OSError: pass
    return fixed


HOME_PATH = re.compile(r'/Users/[^ /]+')


def redact_home(text):
    """'/Users/ayse/…' → '/Users/…'. A report lands in iCloud Drive or a shared team folder, where a macOS
    account name is a person's name; error lines were already redacted, everything else has to be too."""
    return HOME_PATH.sub('/Users/…', text) if isinstance(text, str) else text


def redact_paths(value):
    """redact_home over a whole report payload — every string, however deep, keys included."""
    if isinstance(value, dict): return {redact_home(k): redact_paths(v) for k, v in value.items()}
    if isinstance(value, list): return [redact_paths(v) for v in value]
    if isinstance(value, tuple): return [redact_paths(v) for v in value]
    return redact_home(value)


def _errors(log_path, limit=8):
    if not Path(log_path).is_file(): return []
    out = []
    for line in Path(log_path).read_text(encoding='utf-8', errors='replace').splitlines()[-400:]:
        if line.startswith('Meeting OS:') or line.startswith('Traceback') or re.match(r'\s*[\w.]*(Error|Exception)\b', line):   # anchored: a transcript line containing the word Error must never be copied into a shared report
            out.append(redact_home(line)[:240])
    return out[-limit:]


def error_journal(data_dir):
    """The local error journal (errors.jsonl), summarised for the heartbeat: how many of each kind in the
    last day, the newest few messages, how many crashes. Redacted where it is written; `redact_paths` runs
    over the whole heartbeat as well. Never raises — observability must not break the app."""
    try:
        from . import errors
        return errors.summary(data_dir)
    except Exception: return None


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
        folder, shared = prepare_folder(settings)
        payload = {'recording_heartbeat_version': 1, 'host': host_name(), 'written': datetime.now(timezone.utc).isoformat(), **state}
        payload['line'] = recording_line(payload)
        payload = redact_paths(payload)   # the recorder hands over capture_dir, which starts /Users/<name>/
        return str(publish(folder / RECORDING_HEARTBEAT_FILE, json.dumps(payload, ensure_ascii=False, indent=1), shared=shared))
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
        from .capture_metrics import journal_counters
        health = journal_counters(journal)   # counted over the whole journal; `gaps` below stays the tail's own count
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
    for sp in speakers.values(): sp['clusters'] = len(sp['clusters']); sp['seconds'] = round(sp['seconds'], 1); sp['named'] = bool(sp['name'])
    if not include_text:
        # The Settings caption promises "yalnız sayı, puan, maliyet, model adı ve hata satırı". A meeting title
        # and a person's name are content, and this file lands in iCloud Drive or the team folder; the counts,
        # the similarity and whether the cluster was named at all survive, the identity does not.
        speakers = {f'S{i}': {**sp, 'name': None, 'suggested': None} for i, sp in enumerate(speakers.values(), 1)}
    from .review import review_queue
    from .quality import identity_report
    queue = review_queue(store, mid, data_dir)
    kinds = {}
    for item in queue['items']: kinds[item['kind']] = kinds.get(item['kind'], 0) + 1
    analysis = store.db.execute('SELECT model,payload,created FROM analyses WHERE meeting=? ORDER BY id DESC LIMIT 1', (mid,)).fetchone()
    analysis_summary = None
    if analysis:
        payload = json.loads(analysis['payload'])
        spend = store.analysis_cost_totals(mid)
        analysis_summary = {'model': analysis['model'], 'counts': {k: len(payload.get(k, [])) for k in ('summary', 'decisions', 'risks', 'questions', 'actions')},
                            'superseded_decisions': sum(1 for d in payload.get('decisions', []) if d.get('superseded')),
                            'coverage': payload.get('coverage'), 'dropped_quotes': payload.get('dropped_quotes'), 'dropped_items': payload.get('dropped_items'),
                            'cost_usd': spend['cost'], 'calls': spend['calls'], 'cost_estimated': spend['estimated'], 'created': analysis['created']}
    duration = round(max((r['end'] for r in rows), default=0.0), 1)
    report = {
        'report_version': 2, 'host': host_name(), 'macos': platform.mac_ver()[0], 'app_version': version, 'commit': commit,
        'written': datetime.now(timezone.utc).isoformat(), 'meeting': row['id'], 'title': row['title'] if include_text else None, 'created': row['created'], 'status': row['status'],
        'engine': meta.get('engine'), 'model': meta.get('model'), 'cloud_mode': meta.get('cloud_mode'),
        'duration_seconds': duration, 'segments': len(rows), 'words': sum(len((r.get('text') or '').split()) for r in rows),
        'capture': capture_block(meta.get('capture_dir'), duration),
        'pieces': len(chunks), 'pieces_paid': len(paid), 'pieces_skipped': sum(1 for u in chunks if isinstance(u, dict) and 'skipped' in u),
        'cost_usd': round(sum(float(u.get('cost') or 0) for u in paid), 5), 'uploaded_seconds': round(sum(float(u.get('seconds') or 0) for u in paid), 1),
        'echo_windows_skipped': meta.get('echo_windows_skipped'), 'mic_gated_windows': meta.get('mic_gated_windows'), 'echo_segments': meta.get('echo_segments'), 'identity': meta.get('identity'), 'identity_error': meta.get('identity_error'),
        'markers': len(meta.get('markers') or []), 'glossary_suggestions': len(meta.get('glossary_suggestions') or []),
        # How the spelling hint's 900 characters were spent: how many terms fitted and how many did not. The
        # TERMS stay on this Mac — a word is content, and this file lands in a team folder (Codex #7).
        'hint_included': len(meta.get('hint_included') or []), 'hint_excluded': meta.get('hint_excluded'),
        'job_usage': meta.get('job_usage'),
        # THIS meeting's identity scorecard, not the database's. Until 1.2.82 every report carried the DB-wide
        # one, so two reports from the same Mac added up to twice the same clusters; `scope` says which it is and
        # `summarize` adds up only the per-meeting kind.
        'speakers': speakers, 'review_queue': kinds, 'analysis': analysis_summary, 'scorecard': identity_report(store, mid), 'errors': _errors(Path(data_dir) / 'last-job.log'),
    }
    if include_text:
        from .intelligence import row_label
        owner = settings_owner(data_dir)
        report['transcript'] = [{'start': r['start'], 'speaker': row_label(r, owner), 'text': r.get('text')} for r in rows]
    return report


def write_meeting_report(store, mid, data_dir, *, version=None, commit=None):
    """Write <report_dir>/<host>/<created-date>_<meeting>.json when sharing is on. Never raises into the caller."""
    try:
        settings = load_settings(data_dir)
        if not settings.get('share_reports'): return None
        report = redact_paths(build_meeting_report(store, mid, data_dir, include_text=bool(settings.get('share_text')), version=version, commit=commit))
        folder, shared = prepare_folder(settings)
        written = publish(folder / f"{report['created'][:10]}_{mid}.json", json.dumps(report, ensure_ascii=False, indent=1), shared=shared)
        # A report the team cloud has not uploaded yet is exactly what the outbox is for; the mirror holds it
        # until a pass delivers it (sanitised at that point, never before — the file here stays as written).
        try:
            from . import team_cloud
            if not (settings.get('team_dir') or '').strip(): team_cloud.mark_outbox(data_dir, 'report')
        except Exception: pass
        return str(written)
    except Exception as exc:  # reporting must never break a job
        import sys; print(f'Meeting OS: Rapor yazılamadı: {type(exc).__name__}', file=sys.stderr); return None


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


_REPO_COMMIT = ...   # resolved once per run; a git call per heartbeat is pointless and can fail slowly


def repo_commit():
    """Short HEAD of the checkout this process runs from, or None. Cached, and tolerant of every way git can be
    absent: the heartbeat is observability and must never raise or block on it."""
    global _REPO_COMMIT
    if _REPO_COMMIT is ...:
        _REPO_COMMIT = None
        try:
            from .cli import ROOT
            r = subprocess.run(['git', 'rev-parse', '--short', 'HEAD'], cwd=ROOT, capture_output=True, text=True, timeout=5)
            if r.returncode == 0: _REPO_COMMIT = r.stdout.strip() or None
        except Exception: pass
    return _REPO_COMMIT


def update_status(data_dir):
    """What scripts/update.sh last recorded: state, message, time. The other Mac learns from this that an update
    started and never finished, instead of guessing from a version that stopped moving."""
    try:
        raw = json.loads((Path(data_dir) / 'update-status.json').read_text(encoding='utf-8'))
        return {k: raw.get(k) for k in ('state', 'message', 'time')} if isinstance(raw, dict) else None
    except (OSError, ValueError): return None


def signing_partition_granted():
    """The marker scripts/fix-signing-prompts.sh writes. Read through the probe module so tests can redirect it;
    nothing here ever calls `security`, so it can never open a dialog."""
    try:
        from . import probe
        return bool(probe.SIGNING_MARKER.is_file())
    except Exception: return None


def build_heartbeat(store, data_dir, *, app=None):
    """This Mac's current state, independent of any single meeting: counts, sizes, disk, thermal, errors.

    `app_version` is what the RUNNING BUNDLE reports (CFBundleShortVersionString, handed over by the app);
    `repo_version` and `commit` describe the checkout the update would build from. When they disagree, an update
    merged but never finished its build — the one failure the fleet could not see before."""
    from .desktop import folder_bytes   # the bridge owns the one copy; importing it here keeps this module light
    from . import __version__
    data = Path(data_dir)
    version = commit = None
    if isinstance(app, dict): version, commit = app.get('version'), app.get('commit')
    elif isinstance(app, str): version = app
    commit = commit or repo_commit()
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
        'repo_version': __version__, 'update_status': update_status(data), 'signing_partition': signing_partition_granted(),
        'written': datetime.now(timezone.utc).isoformat(), 'meetings': sum(statuses.values()), 'statuses': statuses, 'last_complete': last,
        'sizes': {'recordings': folder_bytes(data/'recordings'), 'imports': folder_bytes(data/'imports'), 'database': database, 'free_disk': free},
        'memory_pressure': _memory_pressure(), 'thermal': _thermal(), 'load_average': load,
        'recording': read_recording_heartbeat(host_dir(load_settings(data_dir))),   # a meeting being taped right now
        'errors': _errors(data/'last-job.log', limit=5),
        'error_journal': error_journal(data),   # errors.jsonl: crashes, failed jobs, cloud/capture faults nobody reported
        'cloud_blocked': store.db.execute("SELECT count(*) FROM meetings WHERE status!='complete' AND json_extract(metadata,'$.cloud_error.kind') IN ('auth','credit')").fetchone()[0],
        'probe': daily_probe(data),
        # What the user actually decided this week, in numbers: how many of each action, and how the automatic
        # names ended up (verified / falsified / unreviewed). No word, no name, no title, no id — and it
        # reaches the server through the same whitelist as everything else (telemetry_schema).
        'learning': _learning(store),
        'team_cloud': _team_cloud(data),   # is the shared knowledge base reaching the server, and how many Macs are on it
        # Numbers only, one record per (device, day, app_version), REPLACED on every upload rather than added
        # to: a heartbeat that is written again must not make the fleet count the same day twice.
        'quality_daily': _quality_daily(store, data, version),
        # What this Mac takes from the shared knowledge base and what it puts back in. Counts only: no name, no word.
        **_team_counts(store),
    }


def _quality_daily(store, data_dir, version):
    """This Mac's daily quality numbers (quality.daily_summary): names reviewed/overruled, taught words that
    came back wrong, summary and task corrections, Kontrol results, exports, analysis seconds. No text, no
    person, no meeting — counts and their denominators. Never raises: observability is not a job."""
    try:
        from .quality import daily_for_heartbeat
        return daily_for_heartbeat(store, data_dir, version=version)
    except Exception:
        return []


def _team_cloud(data_dir):
    """The team cloud in four fields: when it last synced, what went wrong if anything, which Macs are on it,
    and which DEVICE this heartbeat came from. The host name a heartbeat carries is `LocalHostName`, which two
    Macs in an office can share and any user can change; `device` is this Mac's own random id, so the team's
    diagnostics can still tell two same-named Macs apart. Never raises and never touches the network."""
    try:
        from . import team_cloud
        state = team_cloud.status(data_dir)
        from .errors import code_for
        error = state.get('last_error')
        # `last_error` is the sentence the local reader needs; `last_error_code` is the half that is allowed to
        # travel (telemetry_schema drops the sentence). Same classifier the error export uses.
        return {'last_ok': state.get('last_ok'), 'last_error': error, 'last_error_code': code_for('cloud', error) if error else None,
                'hosts': state.get('hosts') or [], 'device': state.get('device') or ''}
    except Exception:
        return {}


def _learning(store, days=7):
    """`learning.summary` for the heartbeat. Never raises: a database with no learning_events is normal."""
    try:
        from .learning import summary
        return summary(store, days=days)
    except Exception:
        return {}


def _team_counts(store):
    """`team_profiles`/`team_words` (what this Mac imported) and `shared_profiles`/`shared_words` (what it
    publishes). Never raises: the heartbeat is observability, and a database with no team tables is normal."""
    try:
        from .team_knowledge import team_summary
        summary = team_summary(store)
        return {'team_profiles': summary['profiles'], 'team_words': summary['words'],
                'shared_profiles': summary['shared_profiles'], 'shared_words': summary['shared_words']}
    except Exception:
        return {}


PROBE_CACHE = 'probe-last.json'   # kept in step with TIGHTEN_FILES above
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
        publish(cache, json.dumps(last, ensure_ascii=False))
    except Exception as exc:  # observability must never break the app
        last = {'ok': False, 'failed': ['probe'], 'warnings': [], 'summary': f'Öz-test çalıştırılamadı: {type(exc).__name__}', 'at': now.isoformat()}
    return last


def write_heartbeat(store, data_dir, *, app=None):
    """Overwrite <report_dir>/<host>/heartbeat.json when sharing is on, so the other Mac sees this one is
    alive and how it is doing without waiting for a meeting. One file per host, never per day. Never raises."""
    try:
        settings = load_settings(data_dir)
        if not settings.get('share_reports'): return None
        folder, shared = prepare_folder(settings)
        return str(publish(folder / HEARTBEAT_FILE, json.dumps(redact_paths(build_heartbeat(store, data_dir, app=app)), ensure_ascii=False, indent=1), shared=shared))
    except Exception as exc:  # observability must never break the app
        import sys; print(f'Meeting OS: Nabız yazılamadı: {type(exc).__name__}', file=sys.stderr); return None


def remove_meeting_report(mid, data_dir):
    """Delete this host's report for a meeting that was deleted, so the shared folder mirrors the app. Never raises."""
    removed = []
    try:
        settings = load_settings(data_dir)
        roots = {host_dir(settings), Path(settings['report_dir']) / host_name()}   # today's root and the personal one it may have replaced
        team = team_dir(settings)
        if team: roots.add(team / 'reports' / host_name())
        for folder in roots:
            try:
                if folder.is_dir():
                    for path in folder.glob(f'*_{mid}.json'):
                        path.unlink(); removed.append(str(path))
            except Exception as exc:   # a stuck iCloud sync on one root must not spare the copy on another
                import sys; print(f'Meeting OS: Rapor silinemedi ({folder.name}): {type(exc).__name__}', file=sys.stderr)
    except Exception as exc:
        import sys; print(f'Meeting OS: Rapor silinemedi: {type(exc).__name__}', file=sys.stderr)
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
        named = sum(1 for s in (r.get('speakers') or {}).values() if s.get('named') or s.get('name'))   # `name` only in older reports and share_text ones
        out.append({'host': r.get('host'), 'file': path.name, 'title': r.get('title'), 'status': r.get('status'), 'duration_min': round((r.get('duration_seconds') or 0) / 60, 1), 'cost_usd': r.get('cost_usd'), 'model': r.get('model'),
                    'speakers': len(r.get('speakers') or {}), 'named': named, 'review': r.get('review_queue'), 'analysis': (r.get('analysis') or {}).get('counts'), 'errors': len(r.get('errors') or []), 'commit': r.get('commit'), 'app_version': r.get('app_version'),
                    'scorecard': r.get('scorecard') if isinstance(r.get('scorecard'), dict) else None})
    hosts = {}
    for r in out: hosts.setdefault(r['host'], {'reports': 0, 'errors': 0, 'cost_usd': 0.0}); hosts[r['host']]['reports'] += 1; hosts[r['host']]['errors'] += r['errors']; hosts[r['host']]['cost_usd'] = round(hosts[r['host']]['cost_usd'] + (r['cost_usd'] or 0), 4)
    for host, aggregate in add_scorecards(out).items(): hosts.setdefault(host, {'reports': 0, 'errors': 0, 'cost_usd': 0.0})['identity'] = aggregate
    for path in sorted(root.glob('*/'+HEARTBEAT_FILE)):   # a host that has written no report can still be alive
        try: beat = json.loads(path.read_text(encoding='utf-8'))
        except (OSError, ValueError): continue
        if not isinstance(beat, dict): continue
        host = beat.get('host') or path.parent.name
        hosts.setdefault(host, {'reports': 0, 'errors': 0, 'cost_usd': 0.0})
        hosts[host]['heartbeat'] = {'last_seen': beat.get('written'), 'free_disk': (beat.get('sizes') or {}).get('free_disk'), 'thermal': beat.get('thermal'),
                                    'memory_pressure': beat.get('memory_pressure'), 'meetings': beat.get('meetings'), 'app_version': beat.get('app_version'),
                                    'repo_version': beat.get('repo_version'), 'commit': beat.get('commit'),
                                    'update_status': beat.get('update_status'), 'signing_partition': beat.get('signing_partition'),
                                    'probe': beat.get('probe'), 'cloud_blocked': beat.get('cloud_blocked'), 'errors': len(beat.get('errors') or []),
                                    'team_profiles': beat.get('team_profiles'), 'team_words': beat.get('team_words'),
                                    'shared_profiles': beat.get('shared_profiles'), 'shared_words': beat.get('shared_words'),
                                    'error_journal': beat.get('error_journal'),
                                    'quality_daily': beat.get('quality_daily') if isinstance(beat.get('quality_daily'), list) else []}
    for path in sorted(root.glob('*/'+RECORDING_HEARTBEAT_FILE)):   # a Mac that is in a meeting right now says so
        beat = read_recording_heartbeat(path)
        if not beat: continue
        host = beat.get('host') or path.parent.name
        hosts.setdefault(host, {'reports': 0, 'errors': 0, 'cost_usd': 0.0})
        hosts[host]['recording'] = {'line': beat.get('line') or recording_line(beat), 'meeting': beat.get('meeting'), 'elapsed_seconds': beat.get('elapsed_seconds'),
                                    'last_chunk_age_seconds': beat.get('last_chunk_age_seconds'), 'restarts': beat.get('restarts'), 'relaunches': beat.get('relaunches')}
    trend = quality_trend(hosts)
    return {'hosts': hosts, 'reports': out, 'quality_trend': trend, 'alerts': alerts(hosts, trend=trend)}


SCORECARD_FIELDS = ('clusters', 'auto_correct', 'auto_wrong', 'suggestion_confirmed', 'suggestion_rejected', 'missed_known', 'still_unnamed')


def add_scorecards(reports):
    """Per host: this fleet's identity numbers added up over its meetings — and ONLY over reports that carry
    their own meeting's numbers.

    A report written before 1.2.82 put the whole database's scorecard into every file (and so does anything
    that marks itself `snapshot`). Adding two of those from one Mac doubled numbers that describe one Mac
    once, which is exactly the double counting the review asked to stop. Such a report is not added; it is
    counted in `snapshots_skipped` so the fleet can see why a host has fewer meetings than reports."""
    hosts = {}
    for r in reports:
        card = r.get('scorecard')
        if not isinstance(card, dict): continue
        slot = hosts.setdefault(r['host'], {**{k: 0 for k in SCORECARD_FIELDS}, 'meetings': 0, 'snapshots_skipped': 0})
        if card.get('scope') != 'meeting' or card.get('snapshot'):
            slot['snapshots_skipped'] += 1; continue
        slot['meetings'] += 1
        for key in SCORECARD_FIELDS:
            value = card.get(key)
            if isinstance(value, int) and not isinstance(value, bool): slot[key] += value
    for slot in hosts.values():
        named = slot['auto_correct'] + slot['auto_wrong']
        slot['auto_precision'] = round(slot['auto_correct'] / named, 3) if named else None
    return hosts


def quality_trend(hosts, **kw):
    """The fleet's own numbers over two consecutive periods (quality.quality_trend). Never raises."""
    try:
        from .quality import quality_trend as compute
        return compute(hosts, **kw)
    except Exception:
        return {'current': None, 'previous': None, 'alerts': []}


STALE_HEARTBEAT_SECONDS = 3*24*3600
LOW_DISK_BYTES = 3*1024**3


RETENTION_WARNING_DAYS = 3
ERROR_JOURNAL_ALERT = 5   # journal entries in a day before the fleet view says something is wrong here


def audio_retention_warning(store, days, *, now=None, ahead=RETENTION_WARNING_DAYS):
    """One line, `ahead` days before the OLDEST recording's audio is deleted — or None when nothing is close.

    With a single retention setting every recording of a busy week reaches the cutoff on the same day, so the
    first thing the user notices is that everything is gone at once. Marking a meeting “Sesi koru”
    (metadata.keep) still saves it, and so does widening the setting — but only before the pass runs.
    Read-only: this deletes nothing and never raises on a meeting whose metadata is unreadable."""
    if not days or int(days) <= 0: return None
    days = int(days); now = now or datetime.now(timezone.utc)
    horizon = now + timedelta(days=int(ahead)) - timedelta(days=days)   # created before this is due within the window
    oldest = None; count = 0
    for row in store.meetings():
        try: meta = json.loads(row['metadata'] or '{}')
        except (TypeError, ValueError): continue
        if row['status'] != 'complete' or meta.get('keep') is True or meta.get('cloud_error'): continue
        if meta.get('audio_removed') or not (meta.get('paths') or meta.get('capture_dir')): continue   # its audio is already gone
        if not any(Path(p).exists() for p in ([*(meta.get('paths') or {}).values()] if isinstance(meta.get('paths'), dict) else []) + [meta.get('capture_dir') or '']): continue   # nothing on disk → cleanup skips it too
        try: created = datetime.fromisoformat(row['created'])
        except (TypeError, ValueError): continue
        if created.tzinfo is None: created = created.replace(tzinfo=timezone.utc)
        if created > horizon: continue
        count += 1
        if oldest is None or created < oldest: oldest = created
    if not count: return None
    left = max(0, int((oldest + timedelta(days=days) - now).total_seconds() // 86400))
    when = 'bugün' if left == 0 else ('yarın' if left == 1 else f'{left} gün içinde')
    return {'meetings': count, 'retention_days': days, 'days_left': left, 'within_days': int(ahead),
            'line': f'{count} kaydın sesi {when} silinecek ({days} gün); saklamak için toplantının “Sesi koru” anahtarını açın '
                    'ya da Ayarlar → Sistem → Gelişmiş → Eski toplantıların sesi'}


def text_retention_candidates(store, days, *, now=None, ahead=0):
    """The meetings a text-retention pass would delete WHOLE — transcript, summary, tasks, the lot.

    Eligible: status `complete`, created more than `days` ago (`ahead` days of lookahead for the warning),
    not marked “Sesi koru” (metadata.keep), not waiting on a cloud retry (`cloud_error`), and with no job
    running on them. `processing`, `provisional`, `incomplete` and `failed` are all excluded by the status
    test, so a meeting that is being recorded or transcribed right now is never a candidate.

    Read-only and never raises: a row whose metadata or timestamp is unreadable is skipped, not deleted.
    Returns [(row, created)] oldest first."""
    if not days or int(days) <= 0: return []
    from .recovery import classify
    days = int(days); now = now or datetime.now(timezone.utc)
    cutoff = now + timedelta(days=int(ahead)) - timedelta(days=days)
    out = []
    for row in store.meetings():
        try: meta = json.loads(row['metadata'] or '{}')
        except (TypeError, ValueError): continue
        if not isinstance(meta, dict): continue
        if row['status'] != 'complete' or meta.get('keep') is True or meta.get('cloud_error'): continue
        if classify(meta.get('worker_identity')) == 'active': continue   # the open job's meeting is never swept
        try: created = datetime.fromisoformat(row['created'])
        except (TypeError, ValueError): continue
        if created.tzinfo is None: created = created.replace(tzinfo=timezone.utc)
        if created > cutoff: continue
        out.append((row, created))
    out.sort(key=lambda item: item[1])
    return out


def text_retention_warning(store, days, *, now=None, ahead=RETENTION_WARNING_DAYS):
    """One line, `ahead` days before the OLDEST meeting is deleted outright — or None when nothing is close.

    The audio warning's twin, for a setting that takes far more: the transcript, the summary and the tasks go
    with the meeting, and nothing on this Mac can bring them back. Marking a meeting “Sesi koru” saves it here
    too, and so does widening the setting — but only before the pass runs."""
    if not days or int(days) <= 0: return None
    days = int(days); now = now or datetime.now(timezone.utc)
    due = text_retention_candidates(store, days, now=now, ahead=ahead)
    if not due: return None
    oldest = due[0][1]
    left = max(0, int((oldest + timedelta(days=days) - now).total_seconds() // 86400))
    when = 'bugün' if left == 0 else ('yarın' if left == 1 else f'{left} gün içinde')
    return {'meetings': len(due), 'retention_days': days, 'days_left': left, 'within_days': int(ahead),
            'line': f'{len(due)} toplantının yazısı {when} tümüyle silinecek ({days} gün): transkript, özet ve görevler. '
                    'Saklamak için toplantının “Sesi koru” anahtarını açın ya da Ayarlar → Sistem → Gelişmiş → Eski toplantıların yazısı'}


def alerts(hosts, *, now=None, trend=None):
    """What the person maintaining the fleet should look at today, one Turkish line each. Derived only from the
    shared folder, so it works on the dev Mac without touching the other machines."""
    now = now or datetime.now(timezone.utc); out = []
    for host, h in sorted(hosts.items()):
        beat = h.get('heartbeat') or {}; stale = False
        seen = beat.get('last_seen')
        if seen:
            try:
                age = (now - datetime.fromisoformat(seen)).total_seconds()
                if age > STALE_HEARTBEAT_SECONDS: stale = True; out.append({'host': host, 'level': 'warning', 'key': 'stale', 'line': f'{host}: {int(age//86400)} gündür nabız yok · uygulama açık mı, güncelleme takıldı mı?'})
            except ValueError: pass
        elif h.get('reports'): out.append({'host': host, 'level': 'note', 'key': 'no_heartbeat', 'line': f'{host}: rapor var ama nabız dosyası yok · 1.2.15 öncesi sürüm olabilir'})
        free = beat.get('free_disk')
        if isinstance(free, (int, float)) and free < LOW_DISK_BYTES: out.append({'host': host, 'level': 'error', 'key': 'disk', 'line': f'{host}: disk {free/1024**3:.1f} GB boş · kayıt 400 MB altında durur; eski sesleri temizleyin'})
        probe = beat.get('probe') or {}
        if probe and not probe.get('ok'): out.append({'host': host, 'level': 'error', 'key': 'probe', 'line': f'{host}: {probe.get("summary") or "öz-test başarısız"}'})
        elif probe.get('warnings'): out.append({'host': host, 'level': 'warning', 'key': 'probe', 'line': f'{host}: {probe.get("summary")}'})
        # The installed bundle and the checkout it would be built from disagree: `git merge --ff-only` landed and
        # the build did not. The Mac then reports itself as up to date (behind=0) while running the old app.
        # A Mac that has been silent for days already has its `stale` line; repeating three more alerts about a
        # state nobody can act on is noise. A dev Mac is legitimately ahead of its bundle between a version bump and
        # the next build, so a mismatch alone is a warning; with a failed update behind it, an error.
        update = beat.get('update_status') or {}
        app_version, repo_version = beat.get('app_version'), beat.get('repo_version')
        if not stale and app_version and repo_version and app_version != repo_version:
            out.append({'host': host, 'level': 'error' if update.get('state') == 'failed' else 'warning', 'key': 'version_mismatch',
                        'line': f'{host}: uygulama {app_version}, depo {repo_version} · güncelleme yarıda kalmış olabilir: sh scripts/update.sh'})
        if not stale and update.get('state') == 'failed':   # `refused` (a recording, local edits) is not a failure
            out.append({'host': host, 'level': 'error', 'key': 'update_failed',
                        'line': f'{host}: son güncelleme başarısız · {update.get("message") or "ayrıntı update.log"}'})
        if not stale and beat.get('signing_partition') is False:
            out.append({'host': host, 'level': 'warning', 'key': 'signing_partition',
                        'line': f'{host}: imzalama izni yok · güncelleme başlamadan durur: sh scripts/fix-signing-prompts.sh'})
        blocked = beat.get('cloud_blocked')
        if isinstance(blocked, int) and blocked > 0: out.append({'host': host, 'level': 'error', 'key': 'cloud', 'line': f'{host}: {blocked} toplantı bulutta bekliyor (anahtar/kredi) · kişi Ayarlar → OpenRouter’a bakmalı'})
        if beat.get('memory_pressure') not in (None, 0, 1, 'normal'): out.append({'host': host, 'level': 'warning', 'key': 'memory', 'line': f'{host}: bellek baskısı {beat.get("memory_pressure")} · yerel işler durur, bulut işleri sürer'})
        rec = h.get('recording') or {}
        age = rec.get('last_chunk_age_seconds')
        if isinstance(age, (int, float)) and age > 60: out.append({'host': host, 'level': 'error', 'key': 'recording', 'line': f'{host}: kayıt sürüyor ama son parça {int(age)} sn önce · yardımcı takılmış olabilir'})
        # The journal block was written by another Mac, possibly a newer or a broken one: every shape is checked
        # rather than trusted, because one malformed heartbeat must not take the whole fleet view down.
        journal = beat.get('error_journal') if isinstance(beat.get('error_journal'), dict) else {}
        newest = next((e.get('message') for e in (journal.get('last') or []) if isinstance(e, dict) and e.get('message')), None)
        crashes = journal.get('crashes_24h')
        if isinstance(crashes, int) and not isinstance(crashes, bool) and crashes > 0:
            out.append({'host': host, 'level': 'error', 'key': 'crash',
                        'line': f'{host}: son 24 saatte {crashes} çökme · {newest or "ayrıntı Ayarlar → Sistem → Hatalar"}'})
        counts = journal.get('last_24h') if isinstance(journal.get('last_24h'), dict) else {}
        counted = sum(v for v in counts.values() if isinstance(v, int) and not isinstance(v, bool))
        if counted >= ERROR_JOURNAL_ALERT:
            out.append({'host': host, 'level': 'warning', 'key': 'error_journal',
                        'line': f'{host}: son 24 saatte {counted} hata kaydı' + (f' · en son: {newest}' if newest else '')})
        if h.get('errors'): out.append({'host': host, 'level': 'note', 'key': 'errors', 'line': f'{host}: son raporlarda {h["errors"]} hata satırı'})
    # One fleet-wide quality line at most, and never per person: the rate rose by 30 % or more with at least
    # 20 eligible observations in BOTH periods. Below that the review says to raise nothing at all.
    out.extend((quality_trend(hosts) if trend is None else trend).get('alerts') or [])
    return out
