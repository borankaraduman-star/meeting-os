"""`quality/policy.json`: the small, versioned, local record of the switches this Mac has actually earned.

Until 1.2.85 every measured improvement ended in a sentence on a card. `quality calibrate` produced a
recommendation and stopped; the review queue sorted the one way it was written to sort; a hint ranking landing
on another branch would ship as whatever its constant said. Nothing recorded WHEN a setting changed, on what
evidence, or how to put it back — and a change you cannot put back is a change nobody should make
automatically (Codex, 11 Sep 2026, #11: "geri dönüş bir politika sürümü değişikliği olsun").

This module is that record, and it is deliberately three fields wide:

* `identity` — the voice-matching bars (`threshold`, `margin`).
* `review_order` — `'severity'` (today) or `'recency'`: which key the Kontrol queue sorts on first.
* `hint_ranking` — `'ranked'` (today) or `'legacy'`: how the 900-character STT hint is filled.

Every version keeps the ones before it in `previous`, so `rollback` is one pop, not an archaeology project.

**Precedence** — one order, documented once, and `cloud_finalize.identity_bars` is the only reader of it:

1. `quality/policy.json` — a measured, dated, reversible promotion. Nothing writes it but `promote`, and
   `promote` refuses a value outside the validated range.
2. `settings.json` — `identity_threshold` / `identity_margin`, what `quality calibrate --apply` writes.
   `apply_calibration` now promotes a policy version in the same breath, so the two can never disagree about
   a bar the user deliberately applied.
3. The shipped constants (`IDENTITY_THRESHOLD`, `IDENTITY_MARGIN`).

A missing, unreadable or out-of-range policy file is simply step 2 — the same rule the settings override has
always followed, for the same reason: recognition must never change because a JSON file got edited by hand.
"""
import json
from datetime import datetime, timezone
from pathlib import Path

POLICY_DIR = 'quality'          # quality.DAILY_DIR; named here too so a read never needs that import
POLICY_FILE = 'policy.json'

REVIEW_ORDERS = ('severity', 'recency')
HINT_RANKINGS = ('ranked', 'legacy')
# What ships. `hint_ranking` defaults to 'ranked' on purpose: 1.2.84 lands the ranked hint on its own branch
# and a getter that answered 'legacy' by default would quietly switch that work off the day it merged. Only a
# measured rollback puts 'legacy' back.
DEFAULT_REVIEW_ORDER = 'severity'
DEFAULT_HINT_RANKING = 'ranked'

# Promotion bounds. The same numbers `store.IDENTITY_THRESHOLD_RANGE`/`IDENTITY_MARGIN_RANGE` hold, repeated
# here as the bound a PROMOTION is checked against: an experiment may not walk the bars outside the range a
# human is allowed to type, however good its arithmetic looked.
THRESHOLD_RANGE = (0.80, 0.95)
MARGIN_RANGE = (0.02, 0.15)

PREVIOUS_LIMIT = 20             # twenty steps back is more history than anyone will walk; the file stays small
FIELDS = ('identity', 'review_order', 'hint_ranking')


def path(data_dir):
    return Path(data_dir)/POLICY_DIR/POLICY_FILE


def _constants():
    """The shipped identity bars. Imported late: `cloud_finalize` pulls in numpy and soundfile, and reading a
    policy file must not cost a recording stack."""
    try:
        from .cloud_finalize import IDENTITY_MARGIN, IDENTITY_THRESHOLD
        return float(IDENTITY_THRESHOLD), float(IDENTITY_MARGIN)
    except Exception:
        return 0.87, 0.05


def defaults():
    """What this Mac does with no policy file at all: today's constants, and `version` 0 so a first promotion
    is version 1. `source` says which step of the precedence answered, and every caller may read it."""
    threshold, margin = _constants()
    return {'version': 0, 'since': None, 'identity': {'threshold': threshold, 'margin': margin},
            'review_order': DEFAULT_REVIEW_ORDER, 'hint_ranking': DEFAULT_HINT_RANKING,
            'evidence': None, 'previous': [], 'source': 'default'}


def _number(value, low, high):
    if isinstance(value, bool) or not isinstance(value, (int, float)): return None
    value = float(value)
    return round(value, 4) if low <= value <= high else None


def _identity(raw):
    """The identity block of a stored record, or None when it is absent or outside the validated range."""
    if not isinstance(raw, dict): return None
    threshold = _number(raw.get('threshold'), *THRESHOLD_RANGE)
    margin = _number(raw.get('margin'), *MARGIN_RANGE)
    if threshold is None or margin is None: return None
    return {'threshold': threshold, 'margin': margin}


def _normalize(raw, previous=True):
    """One stored record → a full record. Unknown or out-of-range fields fall back to the default, field by
    field: half a readable policy is still worth reading."""
    base = defaults()
    if not isinstance(raw, dict): return base
    identity = _identity(raw.get('identity'))
    out = {'version': int(raw['version']) if isinstance(raw.get('version'), int) and not isinstance(raw.get('version'), bool) else 0,
           'since': raw.get('since') if isinstance(raw.get('since'), str) else None,
           'identity': identity or base['identity'],
           'review_order': raw.get('review_order') if raw.get('review_order') in REVIEW_ORDERS else base['review_order'],
           'hint_ranking': raw.get('hint_ranking') if raw.get('hint_ranking') in HINT_RANKINGS else base['hint_ranking'],
           'evidence': raw.get('evidence') if isinstance(raw.get('evidence'), dict) else None,
           'source': 'policy', 'identity_set': identity is not None}
    if previous:
        stack = raw.get('previous')
        out['previous'] = [_normalize(entry, previous=False) for entry in stack][-PREVIOUS_LIMIT:] if isinstance(stack, list) else []
    return out


def _read(data_dir):
    try: data = json.loads(path(data_dir).read_text(encoding='utf-8'))
    except (OSError, ValueError): return None
    return data if isinstance(data, dict) else None


def current(data_dir):
    """The policy in force. Never raises: a missing or broken file is the shipped default, said out loud
    (`source == 'default'`), which is exactly what every caller has to do with it anyway."""
    raw = _read(data_dir)
    if raw is None: return defaults()
    record = _normalize(raw)
    if not record['version']: record['source'] = 'default'   # a file that says nothing is not a policy
    return record


def identity(data_dir):
    """(threshold, margin) the policy states, or None when there is no policy to state them. Step 1 of the
    precedence and nothing else — `cloud_finalize.identity_bars` owns steps 2 and 3."""
    record = current(data_dir)
    if record['source'] != 'policy' or not record.get('identity_set'): return None
    return record['identity']['threshold'], record['identity']['margin']


def review_order(data_dir):
    """Which key the Kontrol queue sorts on first: `'severity'` (the shipped answer) or `'recency'`."""
    return current(data_dir)['review_order']


def hint_ranking(data_dir):
    """`'ranked'` or `'legacy'` for the STT hint. 1.2.84 owns the ranking itself on another branch; this is
    the switch it reads, and until it merges nothing calls this but the CLI and the tests."""
    return current(data_dir)['hint_ranking']


def _changes(changes):
    """Validate a promotion. Raises ValueError rather than dropping a field: a promotion that silently kept
    the old value would be recorded as evidence for a change that never happened."""
    out = {}
    for key, value in (changes or {}).items():
        if key == 'identity_threshold':
            number = _number(value, *THRESHOLD_RANGE)
            if number is None: raise ValueError(f'Eşik {THRESHOLD_RANGE[0]}–{THRESHOLD_RANGE[1]} aralığında olmalı')
            out['identity_threshold'] = number
        elif key == 'identity_margin':
            number = _number(value, *MARGIN_RANGE)
            if number is None: raise ValueError(f'Marj {MARGIN_RANGE[0]}–{MARGIN_RANGE[1]} aralığında olmalı')
            out['identity_margin'] = number
        elif key == 'review_order':
            if value not in REVIEW_ORDERS: raise ValueError('Kuyruk sırası severity ya da recency olmalı')
            out['review_order'] = value
        elif key == 'hint_ranking':
            if value not in HINT_RANKINGS: raise ValueError('İpucu sıralaması ranked ya da legacy olmalı')
            out['hint_ranking'] = value
        else:
            raise ValueError(f'Bilinmeyen politika alanı: {key}')
    if not out: raise ValueError('Değişiklik yok')
    return out


def _write(data_dir, record):
    from .reports import publish
    target = path(data_dir); target.parent.mkdir(parents=True, exist_ok=True)
    publish(target, json.dumps(record, ensure_ascii=False, indent=1))
    return record


def _stored(record):
    """A record as it goes on the `previous` stack: everything but the stack itself.

    `identity` becomes None when that version did not PIN the bars. The difference matters on the way back:
    rolling onto a version that never stated a threshold has to hand the question back to settings.json, not
    freeze whatever the constants happened to be on the day the stack entry was written."""
    out = {k: record[k] for k in ('version', 'since', 'identity', 'review_order', 'hint_ranking', 'evidence')}
    if not record.get('identity_set'): out['identity'] = None
    return out


def _effective_bars(data_dir, record):
    """The bars in force right now: the policy's when it pins them, otherwise whatever step 2 and step 3 of
    the precedence answer. A promotion that changes only the margin must keep the threshold the user is
    actually running, not the constant."""
    if record.get('identity_set'): return dict(record['identity'])
    try:
        from .cloud_finalize import identity_bars
        threshold, margin = identity_bars(data_dir)
        return {'threshold': round(float(threshold), 4), 'margin': round(float(margin), 4)}
    except Exception:
        return dict(record['identity'])


def promote(data_dir, changes, evidence=None, *, store=None, now=None):
    """Write a new policy version, keeping every one before it.

    `changes` is flat and closed: `identity_threshold`, `identity_margin`, `review_order`, `hint_ranking`.
    Anything else, or a number outside the validated range, is a ValueError — an experiment checks its bounds
    before it gets here, and a caller that did not check should hear about it.

    `evidence` is the snapshot the promotion rests on (n, the goal, the before/after numbers). It is stored
    with the version so "why is my threshold 0.85?" has an answer that is not a guess. Counts only: this file
    is not allowed to carry a word, a name or a meeting id."""
    picked = _changes(changes)
    record = current(data_dir)
    pins = bool(record.get('identity_set')) or 'identity_threshold' in picked or 'identity_margin' in picked
    identity_block = _effective_bars(data_dir, record)
    if 'identity_threshold' in picked: identity_block['threshold'] = picked['identity_threshold']
    if 'identity_margin' in picked: identity_block['margin'] = picked['identity_margin']
    if not pins: identity_block = None     # a queue-ordering promotion does not quietly freeze the bars
    moment = now or datetime.now(timezone.utc)
    # The record being replaced always goes on the stack — INCLUDING version 0, the shipped defaults. The
    # first promotion has to be as reversible as the tenth; a policy you can only roll back once you have two
    # of them is exactly the promotion nobody should have trusted.
    # `_stored` on the way in as well as on the way out: `current` re-hydrates an unpinned `identity` to the
    # constants so every reader gets a complete record, and writing THAT back would turn "this version said
    # nothing about the bars" into "this version pinned 0.87" one promotion later.
    stack = [_stored(entry) for entry in (record.get('previous') or [])]
    stack.append(_stored(record))
    new = {'version': record['version']+1, 'since': moment.isoformat(), 'identity': identity_block,
           'review_order': picked.get('review_order', record['review_order']),
           'hint_ranking': picked.get('hint_ranking', record['hint_ranking']),
           'evidence': evidence if isinstance(evidence, dict) else None,
           'previous': stack[-PREVIOUS_LIMIT:]}
    _write(data_dir, new)
    _event(store, 'policy_promote', new['version'])
    return {**_normalize(new), 'changed': sorted(picked)}


def rollback(data_dir, *, store=None, now=None):
    """One step back. The top of `previous` becomes the policy in force under a NEW version number — history
    only ever grows forwards, so "which bars were live on the 12th?" stays answerable after a rollback.

    Nothing to go back to is not an error: `{'rolled_back': False}` and the policy stays exactly as it was."""
    record = current(data_dir)
    stack = [_stored(entry) for entry in (record.get('previous') or [])]
    if record['source'] != 'policy' or not stack: return {'rolled_back': False, 'reason': 'geri alınacak sürüm yok', 'policy': record}
    # Going back to version 0 means going back to the constants, and `_normalize` would not know the
    # difference — so the restored record says which version it came from and `identity_set` keeps step 1 of
    # the precedence honest either way.
    target = stack.pop()
    moment = now or datetime.now(timezone.utc)
    new = {'version': record['version']+1, 'since': moment.isoformat(),
           'identity': dict(target['identity']) if target.get('identity') else None,
           'review_order': target['review_order'], 'hint_ranking': target['hint_ranking'],
           'evidence': {'rollback_of': record['version'], 'restored': target['version']},
           'previous': stack[-PREVIOUS_LIMIT:]}
    _write(data_dir, new)
    _event(store, 'policy_rollback', new['version'])
    return {'rolled_back': True, 'from_version': record['version'], 'restored_version': target['version'],
            'policy': _normalize(new)}


def _event(store, action, version):
    """One row in `learning_events`, and never a reason for a policy write to fail."""
    if store is None: return None
    try:
        from .learning import record_event
        return record_event(store, action, object=f'policy:{version}', version=str(version), scope='global', source='auto')
    except Exception:
        return None


def versions(data_dir):
    """Every version this Mac has held, newest first — what `quality policy` prints."""
    record = current(data_dir)
    if record['source'] != 'policy': return []
    return [_stored(record)]+[_stored(entry) for entry in reversed(record.get('previous') or [])]


def line(record=None, data_dir=None):
    """One line for the setup card: which policy version is live and what it says. Empty when this Mac has
    never promoted one — a card row reading "politika v0" would be noise about a thing that never happened."""
    record = record if isinstance(record, dict) else current(data_dir)
    if record.get('source') != 'policy' or not record.get('version'): return ''
    bars = record.get('identity') or {}
    parts = [f"politika v{record['version']}"]
    if record.get('identity_set'):
        try: parts.append(f"eşik {float(bars['threshold']):.2f} · marj {float(bars['margin']):.2f}")
        except (KeyError, TypeError, ValueError): pass
    if record.get('review_order') != DEFAULT_REVIEW_ORDER: parts.append(f"kuyruk {record['review_order']}")
    if record.get('hint_ranking') != DEFAULT_HINT_RANKING: parts.append(f"ipucu {record['hint_ranking']}")
    return ' · '.join(parts)
