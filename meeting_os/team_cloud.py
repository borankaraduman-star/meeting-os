"""The team's shared knowledge, without a folder anybody has to pick.

Until 1.2.63 the team knowledge base was a FOLDER: `team_dir` (the user picks one) or iCloud Drive
`MeetingOS-Shared`. iCloud is per-Apple-ID and never reaches a colleague; picking a folder is a step every
teammate has to take. Neither is "install and forget", and Boran's rule for this app is that a teammate opens
the app and nothing is asked of them.

So the folder gets a stand-in. `<data_dir>/team/<team id>/` is an ordinary local mirror of the very same layout
(`team-words.jsonl`, `glossary.jsonl`, `profiles/<host>.jsonl`, `reports/<host>/…`), `reports.team_dir`
returns it when the cloud is configured, and everything else in the app — `team_knowledge`, `glossary`,
`reports` — keeps writing to a folder and reading from a folder, exactly as before. This module is the only
piece that knows there is a server: it uploads THIS Mac's files and downloads everybody else's.

Identity with nothing to paste: the team token is derived from the OpenRouter key (`sha256("meetingos-team-v1:"
+ key)`), so the Macs installed with the same key are the same team by construction. A Mac installed with a
different key joins with `team.token` (`MEETING_OS_TEAM=… sh scripts/install.sh`, or `meeting_os team join`).
The token never reaches the repo and the raw key never leaves the Mac — only its hash does, as a bearer token.
The FIRST derived token is written to `team.token` and never derived again: an OpenRouter key is a billing
detail the user may replace on any Tuesday, and replacing it must not move this Mac to another team in silence.

The team is therefore a boundary, not a setting. Mirror (`team/<team id short>/`), sync state
(`team-cloud-state-<team id short>.json`) and the rows a pull put in the database all belong to one team, so
joining another one starts clean instead of uploading the previous team's reports and profiles to it.

Rules this module lives by:
  * It never raises. A sync failure is a line in the team's state file and, at most once an hour, one line
    in the error journal. A meeting must never fail because a server is down.
  * It never blocks a meeting. Connect timeout 5 s, a whole-pass budget of 20 s, and the fast bridge hooks
    call `sync_async` (one background pass at a time), never `sync`.
  * Merging happens here, not on the server: every Mac uploads only its own files and downloads the others'.
    Two Macs can never write the same file, so there is no race and no conflict resolution to get wrong.
  * What goes up is a contract, not a hope. Names and voice vectors, taught words, the glossary, diagnostic
    reports and a WHITELISTED export of the error journal (`errors.export_for_team`) — never the journal
    itself, never audio, and never a transcript, a meeting title or a meeting id unless `share_text` is on
    at the moment of the upload. `_report_for_upload` enforces that on every pass; docs/EKIP.md states it.
  * Delivery is durable. Every publish-worthy change writes `team-outbox.json` BEFORE it asks for a pass, and
    only a pass that finished takes it back — see the outbox section below.
"""
import hashlib
import json
import os
import re
import secrets
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from .glossary import ICLOUD, SHARED_DIR, REAL_DATA_DIR   # iCloud is only ever read, and only to seed once

DEFAULT_URL = 'https://hermes-vps.tail2d8c7e.ts.net/meetingos'
TOKEN_FILE = 'team.token'
KEY_FILE = 'openrouter.key'
DEVICE_FILE = 'device.id'
STATE_FILE = 'team-cloud-state.json'      # 1.2.67 and earlier: one state file, whatever team the Mac was in
STATE_PREFIX = 'team-cloud-state-'        # since: `team-cloud-state-<team id short>.json`, one per team
OUTBOX_FILE = 'team-outbox.json'          # "this Mac owes the team a pass"; survives the bridge process
OUTBOX_REASONS = 8                        # the newest few kinds of change, for the card and the journal
MIRROR_NAME = 'team'
WORDS_FILE = 'team-words.jsonl'
GLOSSARY_FILE = 'glossary.jsonl'
WORDS_DIR = 'words'                       # the raw per-host copies the merged views above are rebuilt from
GLOSSARY_DIR = 'glossary'
PROFILES_DIR = 'profiles'
REPORTS_DIR = 'reports'
ERRORS_FILE = 'errors.jsonl'          # the LOCAL journal; `errors/<host>.jsonl` on the server is its whitelisted export
ICLOUD_REPORTS = ICLOUD / 'MeetingOS-Reports'
HEARTBEAT_FILE = 'heartbeat.json'
RECORDING_HEARTBEAT_FILE = 'recording-heartbeat.json'   # reports.RECORDING_HEARTBEAT_FILE; named here too so pruning never needs that import

TOKEN_SALT = 'meetingos-team-v1:'
TOKEN_RE = re.compile(r'^[0-9a-fA-F]{32,128}$')
INVITE_SCHEME = 'meetingos'      # registered in the app's Info.plist; a click on the link opens Meeting OS
INVITE_HOST = 'join'
INVITE_SUFFIX = '.meetingos-invite'
INVITE_VERSION = 1
INVITE_FILE_NAME = 'Meeting OS Daveti' + INVITE_SUFFIX
KEY_RE = re.compile(r'^[A-Za-z0-9._:-]{8,400}$')    # an OpenRouter key (sk-or-v1-…): no spaces, nothing to quote
TEAM_SHORT_RE = re.compile(r'^[0-9a-f]{6}$')
DEVICE_RE = re.compile(r'^[0-9a-f]{12}$')
HOST_RE = re.compile(r'^[A-Za-z0-9._-]{1,64}$')
REPORT_RE = re.compile(r'^[A-Za-z0-9._-]{1,120}\.json$')
PRIVATE_MODE = 0o600
MIRROR_MODE = 0o700
CONNECT_TIMEOUT = 5.0        # a server that does not answer in five seconds is a server that is down
BUDGET = 20.0                # the whole pass, uploads and downloads together
PULL_REPORTS = 300           # the newest reports of the other Macs; a team's history is not a download
PULL_REPORT_BYTES = 50*1024*1024   # …and a hard disk ceiling for them: 300 is a per-pass selection, not a cap
MAX_FILE_BYTES = 4*1024*1024  # the server refuses more; refusing it here keeps one big file out of the budget
ERROR_JOURNAL_EVERY = 3600   # a Mac offline for a week must leave one line an hour, not one line a minute
CLIENT_AGENT = 'MeetingOS-team-cloud/1'


def _now():
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------- identity

def _write_token(path, tok):
    """0600, no symlink, whole file. The only place a team token is written."""
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, PRIVATE_MODE)
    try: os.write(fd, (tok + '\n').encode('utf-8'))
    finally: os.close(fd)
    try: Path(path).chmod(PRIVATE_MODE)
    except OSError: pass
    return path


def _remember_token(data_dir, tok):
    """Write a token that was DERIVED from the OpenRouter key into `team.token`, once, so it is never derived
    again. Without this, replacing the API key silently moves this Mac to a team of one: the mirror it filled,
    the reports it published and the voices it taught all stay behind, and nobody is told. A usable token file
    already on disk always wins — this never overwrites a `join`."""
    data = Path(data_dir); path = data / TOKEN_FILE
    try:
        if not data.is_dir(): return
        try: raw = path.read_text(encoding='utf-8').strip()
        except (OSError, ValueError): raw = ''
        if TOKEN_RE.match(raw): return
        _write_token(path, tok)
    except OSError: pass   # a read-only data folder is not a reason to fail a settings load


def token(data_dir):
    """This Mac's team token, or None. `team.token` (written by the installer, by `team join`, or by the first
    derivation below) wins; otherwise the OpenRouter key is hashed, so Macs installed with the same key are the
    same team without anyone doing anything. The key itself never leaves the Mac: only this hash travels, as a
    bearer token — and once derived it is remembered, so the team survives a new API key."""
    data = Path(data_dir)
    try:
        raw = (data / TOKEN_FILE).read_text(encoding='utf-8').strip()
        if TOKEN_RE.match(raw): return raw.lower()
    except (OSError, ValueError): pass
    try: key = (data / KEY_FILE).read_text(encoding='utf-8').strip()
    except (OSError, ValueError): return None
    if not key: return None
    derived = hashlib.sha256((TOKEN_SALT + key).encode('utf-8')).hexdigest()
    _remember_token(data, derived)
    return derived


def device_id(data_dir):
    """This Mac's own id: twelve random hex, made once, 0600, derived from nothing the user can change.

    The name a team SEES is still `reports.host_name()` — the user renames their Mac in System Settings and the
    team sees the new name, which is what they meant. But `LocalHostName` is not an identity: two Macs can carry
    the same one, and the server's "you may only write your own files" rule is that name. So every request also
    carries `X-Meeting-OS-Device`, and the heartbeat records it: two Macs called the same thing are still two
    devices in the team's own diagnostics, and a server that later wants per-device access has the handle."""
    data = Path(data_dir); path = data / DEVICE_FILE
    for _ in range(2):
        try:
            raw = path.read_text(encoding='utf-8').strip().lower()
            if DEVICE_RE.match(raw): return raw
        except (OSError, ValueError): pass
        made = secrets.token_hex(6)
        try:
            if not data.is_dir(): return made
            path.unlink(missing_ok=True)   # unusable content; replaced once, then never touched again
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, PRIVATE_MODE)
            try: os.write(fd, (made + '\n').encode('utf-8'))
            finally: os.close(fd)
            return made
        except FileExistsError: continue   # another process was first: the loop reads what it wrote
        except OSError: return made
    return made


def team_id_short(tok):
    """Six characters that name the team in a log line or a setup card and identify nobody."""
    return hashlib.sha256((tok or '').encode('utf-8')).hexdigest()[:6] if tok else ''


def _legacy_owner(data_dir, short):
    """Which team the pre-1.2.68 single mirror and state file belonged to. The state file says so; when it does
    not, the team this Mac is in now — an upgrade does not change teams, only the layout."""
    try:
        state = json.loads((Path(data_dir) / STATE_FILE).read_text(encoding='utf-8'))
        owner = state.get('team_id_short') if isinstance(state, dict) else None
        if isinstance(owner, str) and TEAM_SHORT_RE.match(owner): return owner
    except (OSError, ValueError): pass
    return short


def _move_into(path, destination):
    """Move one legacy entry under the team folder. A folder whose name is already taken (an old app version
    running beside a new one recreated `team/reports/` while the migrated copy existed) is MERGED file by file
    rather than skipped: an orphaned reports folder is a meeting's diagnostics nobody can see any more."""
    try:
        if not destination.exists(): return os.replace(path, destination)
        if not (path.is_dir() and destination.is_dir()): return None
        for child in sorted(path.iterdir()): _move_into(child, destination / child.name)
        if not any(path.iterdir()): path.rmdir()
    except OSError: pass
    return None


def _legacy_entries(data_dir):
    """What is still lying in the pre-1.2.68 places: anything directly under `team/` that is not a team folder.
    One directory listing, so the check can run on every settings load — and it has to, because an older app
    version running beside this one can recreate `team/reports/` long after the first migration."""
    try: return [p for p in sorted((Path(data_dir) / MIRROR_NAME).iterdir()) if not TEAM_SHORT_RE.match(p.name)]
    except OSError: return []


def _needs_migration(data_dir):
    return bool(_legacy_entries(data_dir)) or (Path(data_dir) / STATE_FILE).is_file()


def _migrate_layout(data_dir, short):
    """Move to the per-team layout: `team/*` → `team/<team>/`, `team-cloud-state.json` →
    `team-cloud-state-<team>.json`. Nothing is deleted and nothing is uploaded anywhere: the files land under
    the team that produced them, which is exactly what keying them by team is for."""
    data = Path(data_dir); base = data / MIRROR_NAME; owner = None
    legacy = _legacy_entries(data)
    if legacy:
        owner = _legacy_owner(data, short)
        try:
            target = base / owner
            target.mkdir(parents=True, exist_ok=True, mode=MIRROR_MODE)
            for path in legacy: _move_into(path, target / path.name)
        except OSError: pass
    old = data / STATE_FILE
    if old.is_file():
        owner = owner or _legacy_owner(data, short)
        try:
            new = data / f'{STATE_PREFIX}{owner}.json'
            if not new.exists(): os.replace(old, new)
        except OSError: pass


def mirror_dir(data_dir):
    """`<data_dir>/team/<team id short>` — this team's local stand-in for the shared folder. 0700: it is this
    Mac's copy. Per TEAM, not per Mac: joining another team must not upload the previous team's reports and
    profiles to it, and must not leave this Mac reading the previous team's words as if they were the new
    team's. A Mac with no token at all keeps the flat folder — there is no team to name it after."""
    data = Path(data_dir)
    short = team_id_short(token(data))
    if not short: return data / MIRROR_NAME
    if _needs_migration(data): _migrate_layout(data, short)
    return data / MIRROR_NAME / short


def ensure_mirror(data_dir):
    mirror = mirror_dir(data_dir)
    mirror.mkdir(parents=True, exist_ok=True, mode=MIRROR_MODE)
    # `parents=True` creates `team/` with the umask's mode, not this one, so both levels are set explicitly:
    # the mirror holds names and voice vectors and is nobody else's business.
    for path in (mirror.parent, mirror):
        try: path.chmod(MIRROR_MODE)
        except OSError: pass
    return mirror


def configured(settings, data_dir):
    """True when this Mac should use the cloud: a token exists and the user has NOT picked a team folder.
    A picked folder always wins — a team that keeps its knowledge on a NAS keeps it there."""
    try:
        if (settings.get('team_dir') or '').strip(): return False
        return token(data_dir) is not None
    except Exception: return False


def url(settings):
    base = (settings.get('team_url') or '').strip() if isinstance(settings, dict) else ''
    return (base or DEFAULT_URL).rstrip('/')


def _leave_team(data_dir, store=None):
    """What the PREVIOUS team taught this Mac, put away. Voice samples imported from a team are soft-deleted
    (`deleted_by`), never destroyed — undo is not offered here, but a hidden row can still be looked at, and
    destroying a teammate's work on a settings change is not something this app does. Team words are dropped
    outright: the table is a copy of a teammate's file, and the new team's first pull writes it again.

    Never raises and never blocks the join: a Mac that has not recorded anything has no database at all."""
    close = False
    try:
        if store is None:
            db = Path(data_dir) / 'meeting-os.sqlite'
            if not db.is_file(): return {}
            from .store import Store
            store = Store(db); close = True
        from .team_knowledge import forget_team_imports
        return forget_team_imports(store)
    except Exception: return {}
    finally:
        if close:
            try: store.close()
            except Exception: pass


def join(data_dir, tok, store=None):
    """Write `team.token` so this Mac joins the team that owns that token. 32–128 hex, 0600, never in the repo.

    Joining is a move, not a merge. The new team gets its own mirror (`team/<team id short>`) and its own sync
    state, so nothing this Mac holds for the old team is uploaded to the new one; and the rows the old team's
    pulls put in this database are put away, so the new team's first pull starts from what the NEW team knows.
    Rejoining the team this Mac is already in changes nothing."""
    tok = (tok or '').strip()
    if not TOKEN_RE.match(tok): raise ValueError('Ekip belirteci 32–128 onaltılık karakter olmalı')
    tok = tok.lower()
    data = Path(data_dir); data.mkdir(parents=True, exist_ok=True, mode=MIRROR_MODE)
    previous = token(data)
    path = _write_token(data / TOKEN_FILE, tok)
    left = _leave_team(data, store) if previous and previous != tok else {}
    return {'joined': True, 'team_id_short': team_id_short(tok), 'path': str(path), **left}


def invite_line(data_dir):
    """The one line a teammate runs on a new Mac. It carries the token, so it is shared privately — never in
    the repo, never in a public channel."""
    tok = token(data_dir)
    if not tok: return {'token': '', 'line': '', 'team_id_short': '',
                        'error': 'Bu Mac’te ekip belirteci yok (OpenRouter anahtarı ya da team.token gerekir)'}
    line = ('git clone -b v0.1 https://github.com/borankaraduman-star/meeting-os.git ~/meeting-os && '
            f'MEETING_OS_TEAM={tok} sh ~/meeting-os/scripts/install.sh')
    return {'token': tok, 'team_id_short': team_id_short(tok), 'line': line}


# ---------------------------------------------------------------- invite

# Joining a team without a terminal (Boran, 10 Sep 2026: "kullanacak insanlar terminal yazamaz").
#
# An invite is one payload in two envelopes: a `meetingos://join?…` LINK anybody can send on Slack or WhatsApp,
# and a `.meetingos-invite` FILE for the places a custom scheme does not survive. Both carry the same thing —
# the team token, the server address when it is not the default, and (only if the sender ticks the box) the
# OpenRouter key, so a teammate who was given one never meets the key step at all.
#
# The token and the key are passwords: an invite goes to a person, never into a repo, a ticket or a channel.


def _key_path(data_dir):
    return Path(data_dir) / KEY_FILE


def read_key(data_dir):
    """This Mac's OpenRouter key, or ''. Only the file the app already wrote — Python never asks the Keychain."""
    try: key = _key_path(data_dir).read_text(encoding='utf-8').strip()
    except (OSError, ValueError): return ''
    return key if key and not any(c.isspace() for c in key) else ''


def _write_key(data_dir, key):
    """0600, O_NOFOLLOW, never over an existing file — the caller checks, this is the second lock on the door."""
    data = Path(data_dir); data.mkdir(parents=True, exist_ok=True, mode=MIRROR_MODE)
    path = _key_path(data)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, PRIVATE_MODE)
    try: os.write(fd, (key.strip() + '\n').encode('utf-8'))
    finally: os.close(fd)
    try: path.chmod(PRIVATE_MODE)
    except OSError: pass
    return path


def invite_payload(data_dir, include_key=False, key=None):
    """What an invite carries: `{v, team, url?, key?}`. The address is only ever written down when it is NOT the
    default, so an invite stays short and a team that never moved server has nothing to get wrong. The key is
    included only when the sender asked for it AND this Mac actually has one."""
    tok = token(data_dir)
    if not tok:
        return {'error': 'Bu Mac’te ekip belirteci yok (önce OpenRouter anahtarını girin)'}
    payload = {'v': INVITE_VERSION, 'team': tok}
    try:
        from .reports import load_settings
        base = url(load_settings(data_dir))
    except Exception: base = DEFAULT_URL
    if base and base != DEFAULT_URL: payload['url'] = base
    # A per-person key (Boran, 11 Sep 2026: "herkese ayrı OpenRouter api key vereceğim") beats this Mac's own:
    # the invite then carries the teammate's key, never the sender's. Refused when malformed (spaces, too short).
    personal = (key or '').strip()
    if personal:
        if KEY_RE.match(personal): payload['key'] = personal
        else: return {'error': 'Kişiye özel anahtar geçersiz görünüyor (boşluksuz, en az 8 karakter)'}
    elif include_key:
        own = read_key(data_dir)
        if own: payload['key'] = own
    return payload


def invite_url(data_dir, include_key=False, key=None):
    """`meetingos://join?team=…[&url=…][&key=…]`, percent-encoded. '' when this Mac has no team to give away."""
    payload = invite_payload(data_dir, include_key=include_key, key=key)
    if payload.get('error'): return ''
    query = [(name, payload[name]) for name in ('team', 'url', 'key') if payload.get(name)]
    return f'{INVITE_SCHEME}://{INVITE_HOST}?' + urllib.parse.urlencode(query, quote_via=urllib.parse.quote)


def invite_file_text(data_dir, include_key=False, key=None):
    """The body of a `.meetingos-invite` file: the same payload as JSON, for mail and chat apps that eat links."""
    payload = invite_payload(data_dir, include_key=include_key, key=key)
    if payload.get('error'): return ''
    return json.dumps(payload, ensure_ascii=False, indent=2) + '\n'


def _safe_url(raw):
    """A team address is https, full stop — a bearer token must never travel in the clear. Loopback over http is
    the one exception, and only for a test server on this very Mac."""
    text = (raw or '').strip()
    if not text: return None
    parsed = urllib.parse.urlsplit(text)
    host = (parsed.hostname or '').lower()
    if parsed.scheme == 'https' and host: return text.rstrip('/')
    if parsed.scheme == 'http' and host in ('127.0.0.1', 'localhost', '::1'): return text.rstrip('/')
    return ''   # '' means "there was an address and it is not acceptable"; None means "there was none"


def parse_invite(text_or_url):
    """A link, the JSON of an invite file, or a bare token — whatever the user pasted. Returns the payload or
    `{'error': …}`; it never raises and it never trusts a field it did not validate."""
    raw = (text_or_url or '').strip() if isinstance(text_or_url, str) else ''
    if not raw: return {'error': 'Davet boş'}
    payload = {'v': INVITE_VERSION}
    if raw.lower().startswith(INVITE_SCHEME + '://'):
        parsed = urllib.parse.urlsplit(raw)
        if (parsed.netloc or '').lower() != INVITE_HOST: return {'error': 'Bu bağlantı bir ekip daveti değil'}
        fields = urllib.parse.parse_qs(parsed.query)
        payload['team'] = (fields.get('team') or [''])[0].strip()
        for name in ('url', 'key'):
            value = (fields.get(name) or [''])[0].strip()
            if value: payload[name] = value
    elif TOKEN_RE.match(raw):
        payload['team'] = raw
    else:
        try: data = json.loads(raw)
        except ValueError: return {'error': 'Davet bağlantısı ya da davet dosyası gerekir'}
        if not isinstance(data, dict): return {'error': 'Davet dosyası okunamadı'}
        payload['team'] = str(data.get('team') or '').strip()
        for name in ('url', 'key'):
            value = data.get(name)
            if isinstance(value, str) and value.strip(): payload[name] = value.strip()
    if not TOKEN_RE.match(payload['team']): return {'error': 'Davetteki ekip belirteci geçersiz'}
    payload['team'] = payload['team'].lower()
    if 'url' in payload:
        safe = _safe_url(payload['url'])
        if not safe: return {'error': 'Davetteki adres güvenli değil (https gerekir)'}
        payload['url'] = safe
    # A malformed key is dropped rather than refused: the team is still joinable, and the teammate simply meets
    # the key step they would have met without an invite.
    if 'key' in payload and not KEY_RE.match(payload['key']): payload.pop('key')
    return payload


def accept_invite(data_dir, text_or_url):
    """One click on an invite: write `team.token`, take the key only if the invite carries one and this Mac has
    none, remember a non-default address, then sync. NEVER raises — the caller is a URL handler, and a bad paste
    has to come back as a sentence, not a crash."""
    try:
        payload = parse_invite(text_or_url)
        if payload.get('error'): return payload
        data = Path(data_dir)
        joined = join(data, payload['team'])
        key_written = False
        if payload.get('key') and not _key_path(data).exists():
            try:
                _write_key(data, payload['key']); key_written = True
            except OSError: key_written = False   # an existing key file wins; a full disk is not a failed join
        if payload.get('url'):
            from .reports import save_settings
            save_settings(data, {'team_url': payload['url']})
        return {'joined': True, 'team_id_short': joined['team_id_short'], 'key_written': key_written,
                'synced': sync(data)}
    except Exception as exc:
        return {'error': f'Davet uygulanamadı ({type(exc).__name__})'}


# ---------------------------------------------------------------- state

def state_path(data_dir):
    """`team-cloud-state-<team id short>.json`: what was pushed and pulled is true of ONE team. A Mac that has
    no token keeps the flat name; the pre-1.2.68 file is moved under the team that wrote it."""
    data = Path(data_dir)
    short = team_id_short(token(data))
    if not short: return data / STATE_FILE
    if not (path := data / f'{STATE_PREFIX}{short}.json').exists() and _needs_migration(data):
        _migrate_layout(data, short)
    return path


def _load_state(data_dir):
    try:
        state = json.loads(state_path(data_dir).read_text(encoding='utf-8'))
        return state if isinstance(state, dict) else {}
    except (OSError, ValueError): return {}


def _save_state(data_dir, state):
    try:
        path = state_path(data_dir)
        path.parent.mkdir(parents=True, exist_ok=True, mode=MIRROR_MODE)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, PRIVATE_MODE)
        try: os.write(fd, json.dumps(state, ensure_ascii=False).encode('utf-8'))
        finally: os.close(fd)
    except (OSError, ValueError, TypeError): pass


# ---------------------------------------------------------------- outbox

# A teach or a naming used to reach the team through `sync_async`: a daemon thread inside a bridge process
# that exits the moment it has answered. Delivery was therefore a hope, and the only real guarantee was app
# launch and the hourly housekeeping pass (Codex, 10 Sep 2026, P1 #8).
#
# So every publish-worthy change now writes this file FIRST and the network second. The file is the promise:
# while it exists this Mac owes the team a pass, and something — the app's flush loop, the next launch, the
# hourly tick — will make one. A successful `sync` is the only thing that takes the promise back.


def outbox_path(data_dir): return Path(data_dir) / OUTBOX_FILE


def outbox(data_dir):
    """`{'pending': bool, 'since': <utc iso>|None, 'reasons': [...]}`. Never raises; an unreadable or absent
    file is simply "nothing owed"."""
    try: raw = json.loads(outbox_path(data_dir).read_text(encoding='utf-8'))
    except (OSError, ValueError): return {'pending': False, 'since': None, 'reasons': []}
    if not isinstance(raw, dict) or raw.get('pending') is not True:
        return {'pending': False, 'since': None, 'reasons': []}
    since = raw.get('since') if isinstance(raw.get('since'), str) else None
    reasons = [r for r in (raw.get('reasons') or []) if isinstance(r, str)][:OUTBOX_REASONS]
    return {'pending': True, 'since': since, 'reasons': reasons}


def mark_outbox(data_dir, reason, now=None):
    """One local change that the team has not seen yet. Called BEFORE `sync_async`, from the teach/naming/
    glossary/report hooks, so a bridge process that dies on the way out still leaves the promise behind.

    `since` is the moment the FIRST unsent change happened and never moves while the outbox stays pending:
    the setup card's "eşitleme bekliyor · 12:34'ten beri" has to age, not reset on every keystroke.

    Never raises and never returns anything the caller has to handle — a teach is already saved locally."""
    try:
        data = Path(data_dir)
        if token(data) is None: return None    # no team at all: nothing is owed to anybody
        current = outbox(data)
        reasons = [r for r in current['reasons'] if r != reason] + [str(reason)[:40]]
        payload = {'pending': True, 'since': current['since'] or (now or _now()),
                   'reasons': reasons[-OUTBOX_REASONS:]}
        data.mkdir(parents=True, exist_ok=True, mode=MIRROR_MODE)
        fd = os.open(outbox_path(data), os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, PRIVATE_MODE)
        try: os.write(fd, json.dumps(payload, ensure_ascii=False).encode('utf-8'))
        finally: os.close(fd)
        return payload
    except Exception: return None


def clear_outbox(data_dir, keep=None):
    """The promise is kept. `keep` is the outbox as it looked when the pass STARTED: a change made while the
    upload was in flight has a newer `since` (or one more reason) and must survive, or the very edit the user
    made during the pass would be the one that never travels."""
    try:
        current = outbox(data_dir)
        if not current['pending']: return False
        if keep is not None and (current['since'] != keep.get('since') or current['reasons'] != keep.get('reasons')):
            return False
        outbox_path(data_dir).unlink(missing_ok=True)
        return True
    except OSError: return False


def status(data_dir, settings=None):
    """What the setup card and the heartbeat show. Reads one small file; never touches the network."""
    data = Path(data_dir); state = _load_state(data); tok = token(data)
    try:
        from .reports import host_name
        host = host_name()
    except Exception: host = ''
    box = outbox(data)
    return {'configured': tok is not None, 'url': url(settings or {}) if settings else (state.get('url') or DEFAULT_URL),
            'host': host, 'device': device_id(data), 'team_id_short': state.get('team_id_short') or team_id_short(tok),
            # Honest, not green: "son eşitleme 14:20" is a lie while a word the user taught at 14:35 is still here.
            'outbox_pending_since': box['since'] if box['pending'] else None, 'outbox_reasons': box['reasons'],
            'last_ok': state.get('last_ok'), 'last_error': state.get('last_error'), 'last_attempt': state.get('last_attempt'),
            'hosts': state.get('hosts') or [], 'pushed': len(state.get('pushed') or {}), 'pulled': len(state.get('pulled') or {})}


def _short(exc):
    """`ClassName: message`, one line, home path masked, bounded — the card shows it and it reaches the team."""
    from .reports import redact_home
    message = ' '.join(str(exc).split())[:100]
    return redact_home(f'{type(exc).__name__}: {message}' if message else type(exc).__name__)[:120]


def _record_once(data_dir, state, message, moment):
    """One journal line an hour at most. A Mac on a plane would otherwise fill its own error journal with the
    same "network is down" line and bury the faults that matter."""
    last = state.get('error_recorded')
    if isinstance(last, str):
        try: age = (datetime.fromisoformat(moment) - datetime.fromisoformat(last)).total_seconds()
        except ValueError: age = None
        if age is not None and 0 <= age < ERROR_JOURNAL_EVERY: return False
    state['error_recorded'] = moment
    try:
        from .errors import record
        record('cloud', f'Ekip bulutu eşitlenemedi: {message}', context={'where': 'team_cloud'}, data_dir=str(data_dir))
    except Exception: pass
    return True


# ---------------------------------------------------------------- http

_OPENER = None


def _opener():
    global _OPENER
    if _OPENER is None:
        # No proxy handler: a corporate proxy variable in the environment must not silently redirect the team's
        # knowledge somewhere else, and it must not break a local test server either.
        _OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    return _OPENER


class _Http:
    """The whole protocol: GET /v1/index, GET|PUT|DELETE /v1/file/<path>. Bearer token, host header, ETag."""

    def __init__(self, base, tok, host, deadline, device=''):
        self.base = base.rstrip('/'); self.token = tok; self.host = host; self.deadline = deadline
        self.device = device or ''
        self.requests = 0

    def left(self):
        return self.deadline - time.monotonic()

    def _open(self, method, path, body=None, etag=None):
        headers = {'Authorization': f'Bearer {self.token}', 'X-Meeting-OS-Host': self.host, 'User-Agent': CLIENT_AGENT}
        # The host name is what the team SEES and what the server's ownership rule is built on; the device id is
        # who is actually speaking. Two Macs with the same LocalHostName are two ids here.
        if self.device: headers['X-Meeting-OS-Device'] = self.device
        if etag: headers['If-None-Match'] = f'"{etag}"'
        if body is not None: headers['Content-Type'] = 'application/octet-stream'
        request = urllib.request.Request(f'{self.base}/v1/{path}', data=body, headers=headers, method=method)
        self.requests += 1
        timeout = min(CONNECT_TIMEOUT, max(0.5, self.left()))
        try:
            with _opener().open(request, timeout=timeout) as response:
                return response.status, response.read()
        except urllib.error.HTTPError as exc:
            code = exc.code
            try: exc.read()
            except Exception: pass
            finally: exc.close()
            if code in (304, 404): return code, b''
            raise

    def index(self):
        _, body = self._open('GET', 'index')
        data = json.loads(body.decode('utf-8'))
        files = data.get('files') if isinstance(data.get('files'), dict) else {}
        hosts = [h for h in (data.get('hosts') or []) if isinstance(h, str) and HOST_RE.match(h)]
        return {p: m for p, m in files.items() if isinstance(m, dict)}, sorted(set(hosts))

    def get(self, path, etag=None):
        status_code, body = self._open('GET', 'file/' + path, etag=etag)
        return (None if status_code in (304, 404) else body)

    def put(self, path, body):
        self._open('PUT', 'file/' + path, body=body)

    def delete(self, path):
        self._open('DELETE', 'file/' + path)


class _OutOfTime(Exception):
    """The 20 s budget ran out. Whatever was already uploaded stays uploaded; the rest waits for the next pass."""


# ---------------------------------------------------------------- files

def _write_private(path, data):
    """Atomic write at 0600 inside the 0700 mirror: a reader never sees half a file and nobody else sees it."""
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(data, str): data = data.encode('utf-8')
    handle, name = tempfile.mkstemp(dir=str(path.parent), prefix='.' + path.name + '.')
    temporary = Path(name)
    try:
        os.fchmod(handle, PRIVATE_MODE)
        os.write(handle, data)
        os.fsync(handle)
        os.close(handle); handle = None
        os.replace(temporary, path); temporary = None
    finally:
        if handle is not None: os.close(handle)
        if temporary is not None: temporary.unlink(missing_ok=True)
    return path


def _lines(blob):
    text = blob.decode('utf-8', errors='replace') if isinstance(blob, bytes) else str(blob)
    return [l for l in text.splitlines() if l.strip()]


def _dump(entries):
    return (''.join(json.dumps(e, ensure_ascii=False) + '\n' for e in entries)).encode('utf-8')


def _is_real(data_dir):
    try: return Path(data_dir).resolve() == REAL_DATA_DIR.resolve()
    except OSError: return False


def _seed(data_dir, mirror, host):
    """First run only: carry over what the folder era already produced on THIS Mac, so the first sync uploads a
    working knowledge base instead of an empty one. iCloud is read (never written) and only for the real data
    folder — a test or a private copy must never touch the user's iCloud Drive."""
    if any(mirror.iterdir()) if mirror.is_dir() else False: return {'seeded': 0}
    if not _is_real(data_dir): return {'seeded': 0}
    seeded = 0
    try:
        from .team_knowledge import parse_word
        profile = SHARED_DIR / PROFILES_DIR / f'{host}.jsonl'
        if profile.is_file():
            _write_private(mirror / PROFILES_DIR / f'{host}.jsonl', profile.read_bytes()); seeded += 1
        words = SHARED_DIR / WORDS_FILE
        if words.is_file():
            mine = [e for e in (parse_word(l) for l in _lines(words.read_bytes())) if e and e['host'] == host]
            if mine: _write_private(mirror / WORDS_FILE, _dump(mine)); seeded += 1
        heartbeat = ICLOUD_REPORTS / host / HEARTBEAT_FILE
        if heartbeat.is_file():
            _write_private(mirror / REPORTS_DIR / host / HEARTBEAT_FILE, heartbeat.read_bytes()); seeded += 1
    except OSError: pass
    return {'seeded': seeded}


def _own_words(mirror, host):
    """This Mac's own lines out of the shared aggregate. The file is one file for the whole team; the server
    stores one file per host, so the split happens here — and an empty result is uploaded too, because that is
    how a `forget` reaches everybody."""
    path = mirror / WORDS_FILE
    if not path.is_file(): return None
    from .team_knowledge import parse_word
    mine = [e for e in (parse_word(l) for l in _lines(path.read_bytes())) if e and e['host'] == host]
    return _dump(mine)


def _own_glossary(data_dir):
    """The glossary this Mac contributes: its own `glossary.jsonl` plus (real data folder only) the iCloud
    shared one, merged the way `glossary.merge_into` merges — first definition of a term wins, capped."""
    from .glossary import parse_line, MAX_TERMS
    paths = [Path(data_dir) / GLOSSARY_FILE]
    if _is_real(data_dir) and ICLOUD.is_dir(): paths.append(SHARED_DIR / GLOSSARY_FILE)
    entries = []; seen = set()
    found = False
    for path in paths:
        if not path.is_file(): continue
        found = True
        for line in _lines(path.read_bytes()):
            entry = parse_line(line)
            if entry and entry['term'].casefold() not in seen and len(entries) < MAX_TERMS:
                seen.add(entry['term'].casefold()); entries.append(entry)
    return _dump(entries) if found else None


TEXT_KEYS = ('transcript',)     # what `reports.write_meeting_report` puts in a report ONLY with `share_text`
TITLE_KEYS = ('title',)
MEETING_KEY = 'meeting'


def _anonymous(report):
    """One diagnostic report with everything that names a meeting or a person taken out: the transcript gone,
    the title emptied, the meeting id replaced by its eight-character hash, the speakers back to S1, S2…

    This runs at UPLOAD time, not at write time, because the setting can change after the file was written:
    a report written while "Raporlara transkript metnini de ekle" was on must stop travelling the moment the
    user turns it off, and the file it was written from stays on this Mac untouched (Codex P0 #6)."""
    clean = {k: v for k, v in report.items() if k not in TEXT_KEYS}
    for key in TITLE_KEYS:
        if key in clean: clean[key] = None
    mid = str(report.get(MEETING_KEY) or '')
    if mid:
        from .errors import meeting_key
        clean[MEETING_KEY] = meeting_key(mid)
    speakers = report.get('speakers')
    if isinstance(speakers, dict) and speakers:
        clean['speakers'] = {f'S{i}': ({**s, 'name': None, 'suggested': None} if isinstance(s, dict) else s)
                             for i, s in enumerate(speakers.values(), 1)}
    return clean, mid


def _report_for_upload(path, share_text):
    """(name on the server, bytes) for one file in this host's report folder, or (None, None) when it must not
    leave at all. With `share_text` on the file goes as it is — that switch is the user saying so. With it off
    the payload is the anonymous one above and the file NAME loses the meeting id too: `2026-09-10_<mid>.json`
    is itself a meeting id, and the docs promise that one never travels."""
    try: raw = path.read_bytes()
    except OSError: return None, None
    if share_text: return path.name, raw
    try: report = json.loads(raw.decode('utf-8'))
    except (ValueError, UnicodeDecodeError): return None, None   # unreadable: we cannot promise what is in it
    if not isinstance(report, dict): return None, None
    clean, mid = _anonymous(report)
    if any(k in clean for k in TEXT_KEYS): return None, None      # belt and braces: never upload what we meant to drop
    if clean == report: return path.name, raw                     # a heartbeat names nothing; it travels unchanged
    # Only the `_<mid>.json` tail is the meeting id; a bare `replace` also ate matching digits inside the date
    # (a meeting called "4" turned 2026-09-04 into 2026-09-0ef2d127d).
    name = path.name[:-len(f'_{mid}.json')] + f'_{clean[MEETING_KEY]}.json' if mid and path.name.endswith(f'_{mid}.json') else path.name
    if not REPORT_RE.match(name): return None, None
    return name, json.dumps(clean, ensure_ascii=False, indent=1).encode('utf-8')


def _own_files(data_dir, mirror, host, settings, pushed):
    """Every path this Mac owns on the server, with its content. Only ever `<kind>/<this host>…`: a Mac can
    physically not write a teammate's file, so nothing here can lose somebody else's work.

    An EMPTY file is uploaded only when this Mac uploaded a full one before — that is how the last forgotten
    word or deleted profile reaches the team. A Mac that never taught anything uploads nothing at all, so it
    does not appear in the team's host list for an empty file nobody reads."""
    data = Path(data_dir)
    share_reports = settings.get('share_reports') is not False
    out = {}

    def add(path, blob):
        if blob and blob.strip() or path in pushed: out[path] = blob

    if settings.get('share_profiles') is not False:
        profile = mirror / PROFILES_DIR / f'{host}.jsonl'
        if profile.is_file(): add(f'profiles/{host}.jsonl', profile.read_bytes())
    if settings.get('share_words') is not False:
        words = _own_words(mirror, host)
        if words is not None: add(f'words/{host}.jsonl', words)
    if settings.get('share_glossary') is not False:
        glossary_blob = _own_glossary(data)
        if glossary_blob is not None: add(f'glossary/{host}.jsonl', glossary_blob)
    if share_reports:
        share_text = settings.get('share_text') is True
        folder = mirror / REPORTS_DIR / host
        if folder.is_dir():
            for path in sorted(folder.glob('*.json')):
                if not REPORT_RE.match(path.name): continue
                name, blob = _report_for_upload(path, share_text)
                if blob is not None: out[f'reports/{host}/{name}'] = blob
        # NOT the journal: the whitelisted export of it. The full `errors.jsonl` never leaves this Mac.
        from .errors import export_for_team
        add(f'errors/{host}.jsonl', export_for_team(data).encode('utf-8'))
    # A file the server would refuse (4 MB) is dropped here rather than spending the budget on a 413.
    return {path: blob for path, blob in out.items() if len(blob) <= MAX_FILE_BYTES}


def _owner(path):
    parts = path.split('/')
    if len(parts) == 2 and parts[1].endswith('.jsonl'): return parts[1][:-len('.jsonl')]
    if len(parts) == 3 and parts[0] == REPORTS_DIR: return parts[1]
    return ''


# ---------------------------------------------------------------- sync

def _push(http, own, files, pushed, result):
    for path in sorted(own):
        blob = own[path]
        digest = hashlib.sha256(blob).hexdigest()
        # Unchanged here AND present there: a server that lost its disk is re-filled on the next pass.
        if pushed.get(path) == digest and (files.get(path) or {}).get('sha256') == digest: continue
        if http.left() <= 0: raise _OutOfTime()
        http.put(path, blob)
        pushed[path] = digest; result['pushed'] += 1


def _push_deletions(http, own, pushed, host, result):
    """A report this Mac deleted locally (a deleted meeting) has to leave the team too. Only this host's own
    reports: nothing here can delete a teammate's file, and the server would refuse anyway."""
    for path in sorted(p for p in list(pushed) if p.startswith(f'{REPORTS_DIR}/{host}/')):
        if path in own: continue
        if http.left() <= 0: raise _OutOfTime()
        http.delete(path)
        pushed.pop(path, None); result['deleted'] += 1


def _pull_file(http, path, meta, target, pulled, result):
    digest = (meta or {}).get('sha256')
    if pulled.get(path) == digest and target.is_file(): return False
    if http.left() <= 0: raise _OutOfTime()
    blob = http.get(path, etag=pulled.get(path) if target.is_file() else None)
    if blob is None: return False   # 304 (unchanged) or 404 (gone between index and fetch)
    _write_private(target, blob)
    pulled[path] = digest or hashlib.sha256(blob).hexdigest(); result['pulled'] += 1
    return True


def _fetch_raw(http, mirror, paths, changed):
    """Download the changed per-host files into the mirror, atomically, one by one. Returns what is now ON DISK
    ({path: sha256}) and the failure that stopped the run, if one did — never a half-written file and never a
    digest for bytes that did not land."""
    fetched = {}; failure = None
    for path in sorted(changed):
        try:
            if http.left() <= 0: raise _OutOfTime()
            blob = http.get(path)
        except Exception as exc:
            failure = exc; break   # budget, timeout, reset: whatever landed already still counts
        if blob is None: continue   # 304 (unchanged) or 404 (gone between index and fetch)
        _write_private(mirror / path, blob)
        fetched[path] = (paths[path] or {}).get('sha256') or hashlib.sha256(blob).hexdigest()
    return fetched, failure


def _drop_raw(mirror, pulled, stale):
    for path in stale:
        pulled.pop(path, None)
        (mirror / path).unlink(missing_ok=True)


def _pull_words(http, mirror, others, pulled, host, result):
    """The mirror's `team-words.jsonl` is the whole team's file: this Mac's own lines plus every other host's.
    Rebuilt from the hosts the index still lists, so a teammate's `forget` — and a host that left — reaches
    this Mac as a line that is simply no longer there.

    Order matters more than it looks. Every download lands in `<mirror>/words/<host>.jsonl` FIRST, the merged
    file is rebuilt from those files, and only THEN is `pulled[path]` recorded. A pass that dies in the middle
    therefore leaves the files it did fetch on disk and marked as fetched, and the ones it never got unmarked:
    the next pass finishes the job instead of believing a word it never applied was already applied."""
    from .team_knowledge import parse_word, read_words
    paths = {p: m for p, m in others.items() if p.startswith(f'{WORDS_DIR}/')}
    stale = [p for p in pulled if p.startswith(f'{WORDS_DIR}/') and _owner(p) != host and p not in paths]
    changed = [p for p, m in paths.items() if pulled.get(p) != (m or {}).get('sha256') or not (mirror / p).is_file()]
    if not changed and not stale: return
    fetched, failure = _fetch_raw(http, mirror, paths, changed)
    _drop_raw(mirror, pulled, stale)
    previous = read_words(mirror / WORDS_FILE)
    entries = [e for e in previous if e['host'] == host]
    for path in sorted(paths):
        raw = mirror / path
        # A host whose file has not been downloaded yet keeps the lines the merged file already had: a slow
        # first pass must not look like "the whole team forgot everything".
        if raw.is_file(): entries += [e for e in (parse_word(l) for l in _lines(raw.read_bytes())) if e]
        else: entries += [e for e in previous if e['host'] == _owner(path)]
    _write_private(mirror / WORDS_FILE, _dump(entries))
    for path, digest in fetched.items(): pulled[path] = digest; result['pulled'] += 1
    if failure is not None: raise failure


def _pull_glossary(http, mirror, others, pulled, host, result):
    """The mirror's `glossary.jsonl` holds the OTHER Macs' terms only (this Mac reads its own file first
    anyway). A term a teammate removed has to disappear here, and entries carry no host, so the merged file is
    rebuilt from the raw per-host copies in `<mirror>/glossary/` every time one of them changes — bytes on
    disk first, merged view second, `pulled` last, exactly like the words above."""
    from .glossary import parse_line, MAX_TERMS
    paths = {p: m for p, m in others.items() if p.startswith(f'{GLOSSARY_DIR}/')}
    stale = [p for p in pulled if p.startswith(f'{GLOSSARY_DIR}/') and _owner(p) != host and p not in paths]
    changed = [p for p, m in paths.items() if pulled.get(p) != (m or {}).get('sha256') or not (mirror / p).is_file()]
    if not changed and not stale: return
    fetched, failure = _fetch_raw(http, mirror, paths, changed)
    _drop_raw(mirror, pulled, stale)
    entries = []; seen = set()
    for path in sorted(paths):
        raw = mirror / path
        if not raw.is_file(): continue
        for line in _lines(raw.read_bytes()):
            entry = parse_line(line)
            if entry and entry['term'].casefold() not in seen and len(entries) < MAX_TERMS:
                seen.add(entry['term'].casefold()); entries.append(entry)
    _write_private(mirror / GLOSSARY_FILE, _dump(entries))
    for path, digest in fetched.items(): pulled[path] = digest; result['pulled'] += 1
    if failure is not None: raise failure


def _sweep(mirror, files, host, pulled):
    """A teammate's file that is no longer in the index is gone from the mirror too: that is how their delete
    (a forgotten profile, a deleted meeting's report) reaches this Mac. This host's own files are never touched."""
    removed = 0
    profiles = mirror / PROFILES_DIR
    if profiles.is_dir():
        for path in sorted(profiles.glob('*.jsonl')):
            key = f'{PROFILES_DIR}/{path.stem}.jsonl'
            if path.stem == host or key in files: continue
            path.unlink(missing_ok=True); pulled.pop(key, None); removed += 1
    reports = mirror / REPORTS_DIR
    if reports.is_dir():
        for folder in sorted(p for p in reports.iterdir() if p.is_dir()):
            if folder.name == host: continue
            for path in sorted(folder.glob('*.json')):
                key = f'{REPORTS_DIR}/{folder.name}/{path.name}'
                if key in files: continue
                path.unlink(missing_ok=True); pulled.pop(key, None); removed += 1
            try:
                if not any(folder.iterdir()): folder.rmdir()
            except OSError: pass
    return removed


def _prune_reports(mirror, host, *, keep=None, budget=None):
    """A real disk ceiling for the reports pulled from the other Macs: the newest `keep` of them, and at most
    `budget` bytes. `PULL_REPORTS` alone only limits what ONE pass selects — pass after pass, a busy team's
    older reports pile up on every Mac and the Storage card cannot explain the difference (Codex P2 #11).

    Only files this Mac downloaded and can download again are dropped: never this host's own folder, never a
    heartbeat (that is what makes an offline teammate visible), and nothing outside `reports/`. The state's
    `pulled` digests are deliberately KEPT, so the next pass does not fetch back what this one just pruned.
    Never raises: pruning a cache is not worth failing a sync over."""
    keep = PULL_REPORTS if keep is None else keep; budget = PULL_REPORT_BYTES if budget is None else budget
    reports = Path(mirror) / REPORTS_DIR
    keeps = {HEARTBEAT_FILE, RECORDING_HEARTBEAT_FILE}
    files = []
    try:
        if not reports.is_dir(): return 0
        for folder in sorted(p for p in reports.iterdir() if p.is_dir()):
            if folder.name == host: continue   # our own reports are not a cache; losing one loses the only copy
            for path in sorted(folder.glob('*.json')):
                if path.name in keeps or not REPORT_RE.match(path.name): continue
                try: size = path.stat().st_size
                except OSError: continue
                files.append((path.name, path, size))
    # Newest first by the report's OWN date: `reports.write_report` names every file `<YYYY-MM-DD>_<meeting>.json`,
    # so the name sorts by age. The file's mtime would sort by when THIS Mac downloaded it, which within one pass
    # runs backwards — the newest report is fetched first and so carries the oldest mtime.
    except OSError: return 0
    files.sort(reverse=True)
    pruned = 0; used = 0; full = False
    for index, (_, path, size) in enumerate(files):
        if not full and index < keep and used + size <= budget: used += size; continue
        full = True   # past the ceiling everything older goes, so the cache is always a newest-first prefix
        try: path.unlink()
        except OSError: continue
        pruned += 1
    return pruned


def _run(data_dir, settings, http, mirror, host, state, result):
    files, hosts = http.index()
    state['hosts'] = hosts
    pushed = dict(state.get('pushed') or {}); pulled = dict(state.get('pulled') or {})
    incomplete = False
    try:
        own = _own_files(data_dir, mirror, host, settings, pushed)
        _push(http, own, files, pushed, result)
        _push_deletions(http, own, pushed, host, result)
        others = {p: m for p, m in files.items() if _owner(p) and _owner(p) != host and not p.startswith('errors/')}
        for path in sorted(p for p in others if p.startswith(f'{PROFILES_DIR}/')):
            _pull_file(http, path, others[path], mirror / PROFILES_DIR / f'{_owner(path)}.jsonl', pulled, result)
        _pull_words(http, mirror, others, pulled, host, result)
        _pull_glossary(http, mirror, others, pulled, host, result)
        reports = sorted(((p, m) for p, m in others.items() if p.startswith(f'{REPORTS_DIR}/')),
                         key=lambda item: ((item[1] or {}).get('updated') or '', item[0]), reverse=True)
        for path, meta in reports[:PULL_REPORTS]:
            name = path.split('/')[-1]
            if not REPORT_RE.match(name): continue
            _pull_file(http, path, meta, mirror / REPORTS_DIR / _owner(path) / name, pulled, result)
        result['removed'] = _sweep(mirror, files, host, pulled)
        result['pruned'] = _prune_reports(mirror, host)
    except _OutOfTime:
        incomplete = True
    finally:
        state['pushed'] = pushed; state['pulled'] = pulled
    return 'budget' if incomplete else None


def sync(data_dir, settings=None, budget=BUDGET):
    """One pass: upload this Mac's files, download everybody else's, write the state file. NEVER raises — the
    caller is a naming, a housekeeping tick or app launch, and none of them may fail because a server did."""
    data = Path(data_dir)
    result = {'pushed': 0, 'pulled': 0, 'deleted': 0, 'removed': 0, 'pruned': 0, 'hosts': []}
    try: seconds = float(BUDGET if budget is None else budget)
    except (TypeError, ValueError): seconds = BUDGET
    deadline = time.monotonic() + max(0.0, seconds)
    try:
        from .reports import load_settings, host_name
        if settings is None: settings = load_settings(data)
        tok = token(data)
        if tok is None or (settings.get('team_dir') or '').strip(): return {**result, 'error': 'unconfigured'}
        host = host_name()
        if not HOST_RE.match(host or ''): return {**result, 'error': 'host'}
        base = url(settings)
    except Exception as exc:
        return {**result, 'error': _short(exc)}
    # One pass at a time per process: a launch sync and a naming's background pass must not both rewrite the
    # mirror and the state file. The second caller waits (bounded by its own budget), it does not skip.
    if not _PASS.acquire(timeout=max(1.0, seconds)): return {**result, 'error': 'busy'}
    try:
        state = _load_state(data)
        moment = _now(); error = None
        owed = outbox(data)   # what this Mac owed BEFORE the pass; a change made during it must not be cleared
        try:
            mirror = ensure_mirror(data)
            _seed(data, mirror, host)
            error = _run(data, settings, _Http(base, tok, host, deadline, device_id(data)), mirror, host, state, result)
        except Exception as exc:
            error = _short(exc)
            _record_once(data, state, error, moment)
        state['url'] = base; state['team_id_short'] = team_id_short(tok); state['last_attempt'] = moment
        if error: state['last_error'] = error
        else: state['last_ok'] = moment; state['last_error'] = None
        _save_state(data, state)
        # The promise is kept only by a pass that finished. A budget-shortened one leaves the outbox alone, so
        # the next flush completes it instead of believing the team already has what it never got.
        result['outbox_cleared'] = bool(owed['pending'] and not error and clear_outbox(data, keep=owed))
        result['hosts'] = state.get('hosts') or []
        return {**result, **({'error': error} if error else {})}
    finally: _PASS.release()


_PASS = threading.Lock()   # serialises sync() itself; _LOCK/_RUNNING below only dedupe background passes


_LOCK = threading.Lock()
_RUNNING = False


def sync_async(data_dir):
    """A background pass, one at a time. The fast bridge (naming a voice, teaching a word) calls this: the
    ten-second watchdog must never wait for a network round trip. Returns the thread, or None when a pass is
    already running."""
    global _RUNNING
    with _LOCK:
        if _RUNNING: return None
        _RUNNING = True

    def run():
        global _RUNNING
        try: sync(data_dir)
        except Exception: pass
        finally:
            with _LOCK: _RUNNING = False
    thread = threading.Thread(target=run, name='team-cloud-sync', daemon=True)
    thread.start()
    return thread
