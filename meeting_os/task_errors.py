"""Which KIND of mistake the task inference keeps making — never which person it keeps making it about.

Codex, 11 Sep 2026, #9. A single corrected task is already kept right: the user's owner or date survives a
re-analysis. What was lost is the SHAPE of the mistake. The same four errors come back meeting after
meeting — a commitment somebody only reported ("Deniz dedi ki, ben deploy edeceğim"), a promise that was
conditional, a microphone row carrying a colleague's echo, a spoken date read wrong — and none of them
changed what the next analysis did.

This module reads the task edits the user marked `inference_error` (`memory.EDIT_REASONS`), puts each into
one FIXED class from the task's own evidence, and counts them. The first adaptation is deliberately the
smallest one that can help and the hardest one to abuse:

* **More review for the class that is going wrong, and nothing else.** When a class passes both bars
  (`MIN_ERRORS` in `WINDOW_DAYS`, and at least `MIN_SHARE` of the errors), new items of that class come
  back with `needs_review=True`. Nothing is dropped, no owner is ever rewritten, no date is ever changed.
* **No person ever enters a rule.** There is no "Ayşe always does the deploys" here and there cannot be:
  the classes are about the EVIDENCE (reported speech, a conditional, a mic row, which field moved), and a
  name is not part of any of them. That is the review's explicit prohibition.
* **Only what the user called a model error.** A change with no reason, or one marked `changed_later`, is
  the meeting doing what meetings do and is never counted. "Model yanlış çıkardı" and "iş sonradan
  devredildi" look identical in the data and mean opposite things.

Local, cheap, no model call: one indexed read of `task_edits`, recomputed by the idle housekeeping pass
into `<data_dir>/quality/task-errors.json` and only READ at analysis time.
"""
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .intelligence import commitment_doubt
from .metrics import normalize

DIR = 'quality'
FILE = 'task-errors.json'
MAX_AGE_HOURS = 24
RETENTION_DAYS = 90       # what the distribution is reported over, matching the learning log's own budget
WINDOW_DAYS = 30          # what the adaptation is decided on
MIN_ERRORS = 5            # ≥5 in the window…
MIN_SHARE = 0.30          # …and at least 30 % of them: one bad week is not a class

CLASSES = ('reported_speech', 'conditional', 'mic_echo', 'date_parse', 'owner_attribution', 'other')
LABELS = {'reported_speech': 'başkasının sözünü aktarma', 'conditional': 'koşullu söz', 'mic_echo': 'mikrofon/yankı',
          'date_parse': 'tarih yorumlama', 'owner_attribution': 'sahip ataması', 'other': 'diğer'}

# "Deniz dedi ki, ben deploy edeceğim" — the speaker is quoting somebody else's commitment. Matched on
# `normalize`d text, which has already dropped punctuation and folded İ/I.
REPORTED = re.compile(r'\bdedi(?:\s+ki)?\b|\bdiyor\b|\bsöyledi\b|\bsöylemiş\b|\bsöylüyor\b|\baktard[ıi]\b'
                      r'|\bbelirtti\b|\bifade etti\b|\bdemiş\b|\bdediği gibi\b|\bşöyle dedi\b')
OWNER_FIELDS = ('owner',)
DATE_FIELDS = ('due_date', 'due_text')


def _fields(field):
    """`task_edits.field` is what `update_action` wrote: one name, or several comma-separated."""
    return {f.strip() for f in (field or '').split(',') if f.strip()}


def _quotes(evidence):
    return ' '.join(e.get('quote') or '' for e in (evidence or []) if isinstance(e, dict))


def _from_mic(evidence, flags=()):
    """Did this task's evidence come off the microphone, or a row the pipeline itself called an echo?

    A mic row can carry an unflagged echo of a colleague, which is exactly how somebody else's promise ends
    up attributed to the owner — `validate_record` already marks that guess, and this is the same test."""
    if 'possible_echo' in set(flags or ()):
        return True
    refs = [e for e in (evidence or []) if isinstance(e, dict)]
    return bool(refs) and all((e.get('source') or '') == 'mic' for e in refs)


def classify(field, evidence, flags=()):
    """The one class a correction belongs to, from the task's evidence and the field the user moved.

    Order matters and is the review's own list. `mic_echo` additionally requires the OWNER to be what moved:
    a microphone row says nothing about a misread date, and a date correction on a mic-recorded task is a
    `date_parse` error, not an echo."""
    quotes = _quotes(evidence)
    fields = _fields(field)
    if quotes and REPORTED.search(normalize(quotes)):
        return 'reported_speech'
    if quotes and commitment_doubt(quotes):
        # `commitment_doubt` is the existing negation/conditional/delegation test. All three say the same
        # thing here: the quote does not carry a firm commitment by this person, and the task was built on it.
        return 'conditional'
    if (not fields or fields & set(OWNER_FIELDS)) and _from_mic(evidence, flags):
        return 'mic_echo'
    if fields & set(DATE_FIELDS):
        return 'date_parse'
    if fields & set(OWNER_FIELDS):
        return 'owner_attribution'
    return 'other'


def item_classes(item, rows=()):
    """Every class a NEW task could be an instance of — what `validate_record` matches against the classes
    that are currently going wrong.

    An edit has one class because one field moved; a fresh item has not been corrected yet, so it belongs
    to every class its evidence exposes it to. An item with an owner is exposed to `owner_attribution`, one
    carrying a spoken date to `date_parse`, and both at once is normal."""
    evidence = (item or {}).get('evidence') or []
    quotes = _quotes(evidence)
    flags = {f for row in (rows or []) for f in (row.get('flags') or [])}
    out = set()
    folded = normalize(quotes) if quotes else ''
    if folded and REPORTED.search(folded):
        out.add('reported_speech')
    if quotes and commitment_doubt(quotes):
        out.add('conditional')
    if (item or {}).get('owner') and _from_mic(evidence, flags):
        out.add('mic_echo')
    if ((item or {}).get('due_text') or '').strip():
        out.add('date_parse')
    if ((item or {}).get('owner') or '').strip():
        out.add('owner_attribution')
    return out


# ---------------------------------------------------------------- counting

def evidence_of(previous):
    """The task as it was before the correction: `task_edits.previous` is the whole row, evidence included."""
    try:
        old = json.loads(previous or '{}')
    except (TypeError, ValueError):
        return [], ()
    if not isinstance(old, dict):
        return [], ()
    payload = old.get('payload')
    payload = payload if isinstance(payload, dict) else {}
    evidence = payload.get('evidence') or old.get('evidence') or []
    flags = payload.get('flags') or []
    return (evidence if isinstance(evidence, list) else []), (flags if isinstance(flags, list) else [])


def counts(store, *, days=RETENTION_DAYS, now=None):
    """How many inference errors of each class in the window, and from how many distinct tasks.

    Counts only. Never a title, never an owner, never a meeting — this is what the heartbeat and the daily
    summary are allowed to carry."""
    out = {'days': int(days), 'total': 0, 'classes': {name: 0 for name in CLASSES}, 'tasks': 0, 'unreasoned': 0}
    try:
        horizon = ((now or datetime.now(timezone.utc)) - timedelta(days=max(1, int(days)))).isoformat()
        columns = {r[1] for r in store.db.execute('PRAGMA table_info(task_edits)')}
        if not {'reason', 'field'} <= columns:
            return out
        tasks = set()
        for row in store.db.execute('SELECT task,previous,field,reason,created FROM task_edits WHERE created>=?', (horizon,)):
            if (row['reason'] or '') != 'inference_error':
                if not (row['reason'] or ''):
                    out['unreasoned'] += 1
                continue
            evidence, flags = evidence_of(row['previous'])
            out['classes'][classify(row['field'], evidence, flags)] += 1
            out['total'] += 1
            tasks.add(row['task'])
        out['tasks'] = len(tasks)
    except Exception:
        return {'days': int(days), 'total': 0, 'classes': {name: 0 for name in CLASSES}, 'tasks': 0, 'unreasoned': 0}
    return out


def review_classes(store, *, now=None, window_days=WINDOW_DAYS, min_errors=MIN_ERRORS, min_share=MIN_SHARE):
    """The classes the next analysis should be more careful about: at least `min_errors` in the window AND
    at least `min_share` of that window's errors. Both bars, because five errors out of two hundred is not
    a pattern and three out of four is not a sample."""
    window = counts(store, days=window_days, now=now)
    total = window['total']
    if not total:
        return ()
    return tuple(name for name in CLASSES
                 if name != 'other' and window['classes'][name] >= min_errors and window['classes'][name] / total >= min_share)


# ---------------------------------------------------------------- the file

def path(data_dir):
    return Path(data_dir) / DIR / FILE


def load(data_dir):
    try:
        record = json.loads(path(data_dir).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}
    return record if isinstance(record, dict) else {}


def active_classes(data_dir):
    """What the last housekeeping pass measured, for the analysis to read. Unknown names are dropped: this
    value decides whether an item is flagged, so it is checked against the enum, not trusted."""
    saved = load(data_dir).get('review') or []
    return tuple(name for name in CLASSES if name in set(saved) and name != 'other')


def save(data_dir, record):
    from .reports import publish
    target = path(data_dir)
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        publish(target, json.dumps(record, ensure_ascii=False, indent=1))
    except OSError:
        pass
    return record


def measure(store, *, now=None):
    """The 90-day distribution, the 30-day window the adaptation is decided on, and the decision itself."""
    moment = now or datetime.now(timezone.utc)
    window = counts(store, days=WINDOW_DAYS, now=moment)
    record = {'version': 1, 'computed': moment.isoformat(),
              'distribution': counts(store, days=RETENTION_DAYS, now=moment),
              'window': window,
              'review': list(review_classes(store, now=moment)),
              'min_errors': MIN_ERRORS, 'min_share': MIN_SHARE, 'window_days': WINDOW_DAYS}
    return record


def refresh(store, data_dir, *, max_age_hours=MAX_AGE_HOURS, now=None):
    """Recompute at most once a day, on the idle housekeeping pass. Never raises."""
    try:
        existing = load(data_dir)
        moment = now or datetime.now(timezone.utc)
        stamp = existing.get('computed')
        if stamp:
            try:
                if datetime.fromisoformat(stamp) > moment - timedelta(hours=max(1, int(max_age_hours))):
                    return {**existing, 'fresh': False}
            except ValueError:
                pass
        record = measure(store, now=moment)
        save(data_dir, record)
        return {**record, 'fresh': True}
    except Exception:
        return {'fresh': False}


def line(record):
    """One Turkish line for the setup card and the CLI."""
    distribution = (record or {}).get('distribution') or {}
    total = int(distribution.get('total') or 0)
    if not total:
        return 'görev hata sınıfları: kayıtlı çıkarım hatası yok'
    ranked = sorted(((n, c) for n, c in (distribution.get('classes') or {}).items() if c), key=lambda x: -x[1])[:3]
    text = 'görev hata sınıfları: ' + ', '.join(f'{LABELS.get(n, n)} {c}' for n, c in ranked)
    review = [LABELS.get(n, n) for n in (record or {}).get('review') or []]
    return text + (f" · daha çok inceleme: {', '.join(review)}" if review else '')


__all__ = ['CLASSES', 'LABELS', 'MIN_ERRORS', 'MIN_SHARE', 'WINDOW_DAYS', 'active_classes', 'classify',
           'counts', 'evidence_of', 'item_classes', 'line', 'load', 'measure', 'path', 'refresh', 'review_classes', 'save']
