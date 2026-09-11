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
    # Codex #6, time to value. `team_join` is a setup step and says nothing about benefit; these two say when
    # the team's knowledge actually ARRIVED and when it first produced a name a human then verified. Each is
    # written once, ever — they are the start and the end of a stopwatch, not a running count.
    'team_knowledge_ready', 'team_first_value',
)
# The stopwatch, in order. `summary` reports the two durations between them when both ends exist.
TEAM_STAGES = ('team_join', 'team_knowledge_ready', 'team_first_value')
SCOPES = ('segment', 'speaker', 'meeting', 'global')
SOURCES = ('human', 'auto')
OUTCOMES = ('applied', 'reverted', 'noop')

RETENTION_DAYS = 90
RETENTION_BYTES = 20*1024*1024
ROW_OVERHEAD = 48             # sqlite per-row cost on top of the text this table stores
OBJECT_LIMIT = 120            # a reference, not a sentence: a meeting id is 12 characters, a task id 20
EVENT_LIMIT = 500

SCHEMA = (
    '''CREATE TABLE IF NOT EXISTS learning_events(id INTEGER PRIMARY KEY, time TEXT, action TEXT, object TEXT,
        version TEXT, scope TEXT, source TEXT, outcome TEXT, undo_of INTEGER, app_version TEXT)''',
    'CREATE INDEX IF NOT EXISTS learning_events_time ON learning_events(time)',
    'CREATE INDEX IF NOT EXISTS learning_events_dedupe ON learning_events(action,object,time)',
)


def _ensure(store):
    """Create the table the first time this store is asked for it, like every other late table here. The flag
    lives on the Store, not in a module-level set of `id()`s: a closed connection's id is handed out again."""
    if getattr(store, '_learning_ready', False): return
    with store.db:
        for statement in SCHEMA: store.db.execute(statement)
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
                 outcome='applied', undo_of=None, now=None):
    """Append one event and return its id (or None). NEVER raises: the user's action already succeeded, and
    an observability row is not allowed to turn it into an error on screen.

    Retries must not double-count, so a write is deduped by (action, object, version, minute): the app's
    bridge is one process per request and a flaky call is simply made again."""
    try:
        if action not in ACTIONS: return None
        scope = scope if scope in SCOPES else 'meeting'
        source = source if source in SOURCES else 'human'
        outcome = outcome if outcome in OUTCOMES else 'applied'
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
                'INSERT INTO learning_events(time,action,object,version,scope,source,outcome,undo_of,app_version) VALUES(?,?,?,?,?,?,?,?,?)',
                (stamp, action, obj, ver, scope, source, outcome,
                 int(undo_of) if isinstance(undo_of, int) and not isinstance(undo_of, bool) else None, _version()))
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


def record_once(store, action, **fields):
    """Write an event only if this Mac has never written one of this kind. The two team milestones are
    stopwatch marks: a second `team_first_value` would not be a second benefit, it would be a wrong answer to
    "how long did it take". Returns the existing id when there already is one."""
    try:
        existing = last_event(store, action)
        if existing: return existing.get('id')
    except Exception: pass
    return record_event(store, action, **fields)


def team_stopwatch(store):
    """When the team was joined, when its knowledge first arrived, and when it first paid off — plus the two
    durations the review asked to be measured separately (Codex #6: "katılım → bilgi kullanılabilir → ilk
    doğrulanmış yarar"). Missing stages are `None`; a duration is reported only when both of its ends exist,
    and a negative one (a clock that moved, a restored database) is dropped rather than shown."""
    out = {stage: None for stage in TEAM_STAGES}
    out.update({'join_to_ready_seconds': None, 'join_to_first_value_seconds': None})
    try:
        _ensure(store)
        for stage in TEAM_STAGES:
            row = store.db.execute('SELECT time FROM learning_events WHERE action=? ORDER BY id LIMIT 1', (stage,)).fetchone()
            if row and row[0]: out[stage] = row[0]
        for key, later in (('join_to_ready_seconds', 'team_knowledge_ready'), ('join_to_first_value_seconds', 'team_first_value')):
            if not out['team_join'] or not out[later]: continue
            try: seconds = (datetime.fromisoformat(out[later]) - datetime.fromisoformat(out['team_join'])).total_seconds()
            except ValueError: continue
            if seconds >= 0: out[key] = round(seconds, 1)
    except Exception: pass
    return out


def summary(store, days=7, data_dir=None):
    """Numbers only: how many of each action in the window, how the automatic names actually ended up, and
    what the team cost or bought (Codex #6).

    This is what the heartbeat carries. There is no word in it, no name, no title and no id — the `learning`
    block of the team contract is counts and nothing else (docs/EKIP.md). The team effect is READ from the
    file the idle housekeeping measures into; an hourly heartbeat is not allowed to run two replays."""
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
    team = team_stopwatch(store)
    try:
        from pathlib import Path as _Path
        from .quality import load_team_effect
        effect = load_team_effect(data_dir or _Path(store.path).parent)
        team['profile_effect'] = {k: int(effect.get(k) or 0) for k in ('right', 'wrong', 'clusters', 'meetings', 'team_samples')}
    except Exception: pass
    out['team'] = team
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
