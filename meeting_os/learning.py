"""`learning_events`: one row per human decision, and never the content of it.

The app already learns — voice samples, rejections, personal thresholds, word rules, the glossary. What it
could not answer was "did the user actually decide this, or did the machine decide and nobody looked?".
Corrections live in one table, text edits in another, taught words in a third, and an export wrote nothing
at all, so the same question had a different answer on every screen (Codex, 11 Sep 2026, P0 #1).

This module is the missing common record. One row per SUCCESSFUL user action: what the action was, WHICH
object it was about (a meeting id, a task id, a folded word, a person's name — a reference, never a
sentence), which analysis or correction version it applied to, how wide it reached, whether a human or the
machine did it, how it ended, and the event it undoes. Nothing here stores transcript text, a quote, a
message or a path.

Two rules the rest of the code has to keep:

* **One human decision is one event, however many effects it has.** Teaching a word writes ONE `word_teach`
  at teach time; the twenty segments that rule then rewrites write nothing. Counting those twenty as twenty
  independent human confirmations is exactly the over-count this table exists to prevent.
* **A write must never be felt.** `record_event` never raises, never touches the network and never scans
  history: one indexed lookup for the dedupe and one insert, on the fast bridge, inside the caller's own
  turn. A failure to record is silent by design — the user's action already succeeded.

Retention: 90 days / 20 MB, pruned by the hourly housekeeping pass (`prune`).
"""
import json
from datetime import datetime, timedelta, timezone

# Every action that may be recorded. A name that is not on this list is not written: an enum nobody enforces
# is a free-text column with extra steps.
ACTIONS = (
    'record_start', 'record_stop',
    'name_confirm', 'name_correct', 'name_reject', 'segment_pin',
    'word_teach', 'word_forget', 'word_dismiss',
    'glossary_apply', 'glossary_dismiss',
    'review_resolve',
    'task_edit', 'task_due',
    'summary_edit',          # reserved for 1.2.81 (#2); nothing writes it yet
    'export_ok', 'team_join', 'undo',
)
SCOPES = ('segment', 'speaker', 'meeting', 'global')
# Why a decision was made, when the app can honestly tell. An enum, like the actions: a free-text "why" is a
# sentence, and this table never stores sentences. `team_conflict` is a word taught to settle two teammates'
# spellings (#7); the task reasons are the ones the edit sheet offers (#3).
REASONS = ('team_conflict', 'inference_error', 'changed_later')
SOURCES = ('human', 'auto')
OUTCOMES = ('applied', 'reverted', 'noop')

RETENTION_DAYS = 90
RETENTION_BYTES = 20*1024*1024
ROW_OVERHEAD = 48             # sqlite per-row cost on top of the text this table stores
OBJECT_LIMIT = 120            # a reference, not a sentence: a meeting id is 12 characters, a task id 20
EVENT_LIMIT = 500

SCHEMA = (
    '''CREATE TABLE IF NOT EXISTS learning_events(id INTEGER PRIMARY KEY, time TEXT, action TEXT, object TEXT,
        version TEXT, scope TEXT, source TEXT, outcome TEXT, undo_of INTEGER, app_version TEXT, reason TEXT)''',
    'CREATE INDEX IF NOT EXISTS learning_events_time ON learning_events(time)',
    'CREATE INDEX IF NOT EXISTS learning_events_dedupe ON learning_events(action,object,time)',
)


def _ensure(store):
    """Create the table the first time this store is asked for it, like every other late table here. The flag
    lives on the Store, not in a module-level set of `id()`s: a closed connection's id is handed out again."""
    if getattr(store, '_learning_ready', False): return
    with store.db:
        for statement in SCHEMA: store.db.execute(statement)
        # `reason` arrived after the table did (1.2.84). A database written by 1.2.80 gets the column here;
        # the rest of the code may then write it without asking which release made the file.
        if 'reason' not in {r[1] for r in store.db.execute('PRAGMA table_info(learning_events)')}:
            try: store.db.execute('ALTER TABLE learning_events ADD COLUMN reason TEXT')
            except Exception: pass
    try: store._learning_ready = True
    except Exception: pass   # an object that will not take an attribute simply pays for the CREATEs again


def _version():
    try:
        from . import __version__
        return __version__
    except Exception: return None


def _text(value, limit=OBJECT_LIMIT):
    """One reference field. Never a sentence: one line, bounded, and nothing that is not already a string
    (a dict, a payload, a list of quotes) survives at all."""
    if value is None: return None
    if isinstance(value, bool): return None
    if isinstance(value, (int, float)): return str(value)[:limit]
    if not isinstance(value, str): return None
    text = ' '.join(value.split())
    return text[:limit] or None


def record_event(store, action, *, object=None, version=None, scope='meeting', source='human',
                 outcome='applied', undo_of=None, reason=None, now=None):
    """Append one event and return its id (or None). NEVER raises: the user's action already succeeded, and
    an observability row is not allowed to turn it into an error on screen.

    Retries must not double-count, so a write is deduped by (action, object, version, minute): the app's
    bridge is one process per request and a flaky call is simply made again."""
    try:
        if action not in ACTIONS: return None
        scope = scope if scope in SCOPES else 'meeting'
        source = source if source in SOURCES else 'human'
        outcome = outcome if outcome in OUTCOMES else 'applied'
        reason = reason if reason in REASONS else None
        moment = now or datetime.now(timezone.utc)
        stamp = moment.isoformat()
        obj = _text(object); ver = _text(version, 40)
        _ensure(store)
        minute = stamp[:16]   # ISO to the minute: the natural window for "the same click, tried twice"
        # The outcome is part of the key: a retry repeats it, while "bu doğru" followed by "hayır, düzelt" in
        # the same minute is two opposite decisions about the same word and must stay two rows.
        row = store.db.execute(
            'SELECT id FROM learning_events WHERE action=? AND object IS ? AND version IS ? AND outcome=? AND substr(time,1,16)=? LIMIT 1',
            (action, obj, ver, outcome, minute)).fetchone()
        if row is not None: return row[0]
        with store.db:
            cur = store.db.execute(
                'INSERT INTO learning_events(time,action,object,version,scope,source,outcome,undo_of,app_version,reason) VALUES(?,?,?,?,?,?,?,?,?,?)',
                (stamp, action, obj, ver, scope, source, outcome,
                 int(undo_of) if isinstance(undo_of, int) and not isinstance(undo_of, bool) else None, _version(), reason))
        return cur.lastrowid
    except Exception:
        return None


def events(store, since=None, limit=EVENT_LIMIT):
    """The newest `limit` events, oldest first. `since` is an ISO timestamp or a datetime. Never raises."""
    try:
        _ensure(store)
        limit = limit if isinstance(limit, int) and not isinstance(limit, bool) and 0 < limit <= 10000 else EVENT_LIMIT
        if isinstance(since, datetime): since = since.isoformat()
        if since:
            rows = store.db.execute('SELECT * FROM learning_events WHERE time>=? ORDER BY id DESC LIMIT ?', (str(since), limit))
        else:
            rows = store.db.execute('SELECT * FROM learning_events ORDER BY id DESC LIMIT ?', (limit,))
        return [dict(r) for r in rows][::-1]
    except Exception:
        return []


def last_event(store, action, object=None):
    """The most recent event of one kind about one object — what `undo` points its `undo_of` at."""
    try:
        _ensure(store)
        obj = _text(object)
        row = store.db.execute('SELECT * FROM learning_events WHERE action=? AND (? IS NULL OR object=?) ORDER BY id DESC LIMIT 1',
                               (action, obj, obj)).fetchone()
        return dict(row) if row else None
    except Exception:
        return None


def _bytes(store):
    """Roughly what this table costs on disk. Cheap enough for an hourly pass over 90 days of rows."""
    row = store.db.execute('''SELECT count(*), total(length(coalesce(time,''))+length(coalesce(action,''))
        +length(coalesce(object,''))+length(coalesce(version,''))+length(coalesce(scope,''))
        +length(coalesce(source,''))+length(coalesce(outcome,''))+length(coalesce(app_version,''))) FROM learning_events''').fetchone()
    return int(row[0]), int(row[1] or 0) + int(row[0])*ROW_OVERHEAD


def prune(store, *, days=RETENTION_DAYS, max_bytes=RETENTION_BYTES, now=None):
    """90 days / 20 MB, oldest first (Codex, "kaynak ve saklama sınırı"). Hourly, idle, never raises."""
    try:
        _ensure(store)
        moment = now or datetime.now(timezone.utc)
        horizon = (moment - timedelta(days=max(1, int(days)))).isoformat()
        with store.db:
            removed = store.db.execute('DELETE FROM learning_events WHERE time<?', (horizon,)).rowcount or 0
        count, size = _bytes(store)
        while size > max_bytes and count:
            # A tenth of the table at a time: a budget overrun is a slow leak, not a thing to fix row by row.
            batch = max(1, count//10)
            with store.db:
                removed += store.db.execute('DELETE FROM learning_events WHERE id IN (SELECT id FROM learning_events ORDER BY id LIMIT ?)', (batch,)).rowcount or 0
            count, size = _bytes(store)
        return {'removed': removed, 'rows': count, 'bytes': size}
    except Exception:
        return {'removed': 0, 'rows': 0, 'bytes': 0}


def summary(store, days=7):
    """Numbers only: how many of each action in the window, and how the automatic names actually ended up.

    This is what the heartbeat carries. There is no word in it, no name, no title and no id — the `learning`
    block of the team contract is counts and nothing else (docs/EKIP.md)."""
    out = {'days': int(days), 'events': 0, 'actions': {}, 'undo': 0,
           'names': {'verified': 0, 'falsified': 0, 'unreviewed': 0}}
    try:
        _ensure(store)
        horizon = (datetime.now(timezone.utc) - timedelta(days=max(1, int(days)))).isoformat()
        for action, count in store.db.execute('SELECT action,count(*) FROM learning_events WHERE time>=? GROUP BY action', (horizon,)):
            if action not in ACTIONS: continue
            out['actions'][action] = int(count); out['events'] += int(count)
        out['undo'] = int(out['actions'].get('undo', 0))
    except Exception: pass
    try:
        from .quality import identity_report
        report = identity_report(store)
        out['names'] = {'verified': report['auto_verified'], 'falsified': report['auto_falsified'],
                        'unreviewed': report['auto_unreviewed']}
    except Exception: pass
    return out


# ---------------------------------------------------------------- naming: which decision was this?

def naming_action(store, mid, speaker, name):
    """Which of `name_confirm` / `name_correct` / `name_reject` a naming is — read BEFORE the naming is
    applied, because applying it is what settles the automatic verdict.

    An automatic name the user writes over is a correction. A suggestion typed back is a confirmation
    (folded, so "Ayse" over "Ayşe" confirms the person rather than convicting them — `store.fold_name` is
    the rule). A suggestion replaced by a different person is a rejection. An empty cluster the user simply
    names is a confirmation of nothing automatic, and is recorded as one decision all the same."""
    try:
        from .store import fold_name
        key = fold_name(name)
        auto = set(); suggested = set()
        for row in store.db.execute("SELECT payload FROM segments WHERE meeting=? AND speaker=?", (mid, speaker)):
            identity = ((json.loads(row[0]).get('metrics') or {}).get('identity')) or {}
            if identity.get('settled'): continue          # judged once already; this naming says nothing new
            if identity.get('name'): auto.add(identity['name'])
            if identity.get('suggested'): suggested.add(identity['suggested'])
        if any(fold_name(n) != key for n in auto): return 'name_correct'
        if any(fold_name(n) != key for n in suggested): return 'name_reject'
        return 'name_confirm'
    except Exception:
        return 'name_confirm'
