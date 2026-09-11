"""The user's layer over model output: a correction, a removal or an approval on a summary item.

The model's payload is never rewritten. What the user decided lives in its own table, keyed by the item's
persistent `item_id`, and is applied on top every time the analysis is read — so a re-analysis can reword,
reorder or drop a bullet without silently throwing the user's decision away. A decision whose item no longer
appears is not deleted either: it is handed back as "eşleşmedi" so the person can see what became orphaned.

Everything here is local. Edited wording is the user's own text about their own meeting and is never put in a
report, a diagnostic payload or anything that leaves the Mac.
"""
import copy

from .intelligence import SECTION_LISTS, ensure_item_ids, item_text

try:   # the metrics half of the learning loop lands on its own branch; the merge must not need this file changed
    from .learning import record_event
except ImportError:   # pragma: no cover - exercised only before that branch merges
    record_event = None

ACTIONS = ('edit', 'remove', 'confirm')
REASONS = ('wrong', 'duplicate', 'too_detailed')
REASON_LABELS = {'wrong': 'Yanlış', 'duplicate': 'Tekrar', 'too_detailed': 'Gereksiz ayrıntı'}
ACTION_LABELS = {'edit': 'düzeltme', 'remove': 'kaldırma', 'confirm': 'onay'}
MAX_TEXT = 2000   # a summary bullet the user rewrote, not a document


def event(store, action, **fields):
    """One learning event, if the module that records them is present.

    A metrics hook must never be able to fail a user action, so anything it raises is dropped. The recorder
    lands on its own branch: keyword names it does not know are retried away rather than silently losing the
    event, and the bare (store, action) call is the last thing tried."""
    if record_event is None: return None
    try: return record_event(store, action, **fields)
    except TypeError:
        try: return record_event(store, action)
        except Exception: return None
    except Exception: return None


def ensure_table(store):
    """`insight_edits` is created by Memory alongside `analyses`; a store that was opened without it still works."""
    store.db.executescript('''
    CREATE TABLE IF NOT EXISTS insight_edits(id INTEGER PRIMARY KEY,meeting TEXT,item_id TEXT,section TEXT,action TEXT,text TEXT,reason TEXT,created TEXT,analysis_version INTEGER);
    CREATE UNIQUE INDEX IF NOT EXISTS insight_edits_item ON insight_edits(meeting,item_id,action);
    ''')


def _now():
    from .memory import now
    return now()


def _analysis_version(store, mid):
    row = store.db.execute('SELECT id FROM analyses WHERE meeting=? ORDER BY id DESC LIMIT 1', (mid,)).fetchone()
    return row['id'] if row else None


def edits(store, mid):
    """Every decision the user made about this meeting's items, oldest first.

    Every analysis read passes through here, so the table is created only when it turns out to be missing —
    a schema statement on each read would be a write on what is meant to be a read."""
    import sqlite3
    try: return [dict(r) for r in store.db.execute('SELECT * FROM insight_edits WHERE meeting=? ORDER BY id', (mid,))]
    except sqlite3.OperationalError:
        ensure_table(store)
        return [dict(r) for r in store.db.execute('SELECT * FROM insight_edits WHERE meeting=? ORDER BY id', (mid,))]


def record(store, mid, item_id, section, action, text=None, reason=None):
    """Write one user decision. One row per (item, action): editing twice replaces the wording, and
    confirming twice is still one approval."""
    item_id = (item_id or '').strip()
    if not item_id: raise ValueError('Madde kimliği gerekli')
    if action not in ACTIONS: raise ValueError('Geçersiz madde işlemi')
    section = (section or '').strip() or 'summary'
    if reason is not None and reason not in REASONS: raise ValueError('Geçersiz kaldırma nedeni')
    if action == 'edit':
        if not isinstance(text, str) or not text.strip(): raise ValueError('Düzeltilmiş metin boş olamaz')
        if len(text) > MAX_TEXT: raise ValueError('Düzeltilmiş metin çok uzun')
        text = text.strip()
    else:
        text = None
    if action != 'remove': reason = None
    ensure_table(store)
    version = _analysis_version(store, mid)
    with store.db:
        store.db.execute('''INSERT INTO insight_edits(meeting,item_id,section,action,text,reason,created,analysis_version) VALUES(?,?,?,?,?,?,?,?)
                            ON CONFLICT(meeting,item_id,action) DO UPDATE SET section=excluded.section,text=excluded.text,reason=excluded.reason,created=excluded.created,analysis_version=excluded.analysis_version''',
                         (mid, item_id, section, action, text, reason, _now(), version))
    event(store, f'summary_{action}', object=item_id, outcome=reason or action, scope=section, meeting=mid)
    return {'item_id': item_id, 'section': section, 'action': action, 'text': text, 'reason': reason, 'analysis_version': version}


def undo(store, mid, item_id, action):
    """Take one decision back: restoring a removed item, or clearing an approval/edit."""
    if action not in ACTIONS: raise ValueError('Geçersiz madde işlemi')
    ensure_table(store)
    with store.db:
        cur = store.db.execute('DELETE FROM insight_edits WHERE meeting=? AND item_id=? AND action=?', (mid, item_id, action))
    if cur.rowcount: event(store, f'summary_{action}', object=item_id, outcome='undo', scope=action, meeting=mid)
    return {'item_id': item_id, 'action': action, 'undone': bool(cur.rowcount)}


def toggle_confirm(store, mid, item_id, section, on=None):
    """"Doğru" is a switch: pressing it on an item that already carries the check takes the check off."""
    ensure_table(store)
    has = store.db.execute('SELECT 1 FROM insight_edits WHERE meeting=? AND item_id=? AND action=?', (mid, item_id, 'confirm')).fetchone() is not None
    want = (not has) if on is None else bool(on)
    if want: return {**record(store, mid, item_id, section, 'confirm'), 'confirmed': True}
    return {**undo(store, mid, item_id, 'confirm'), 'confirmed': False}


def apply_layer(payload, rows):
    """The payload as the person should see it: their wording where they corrected one, `removed` on the
    items they took out (never dropped here — the app offers "N madde kaldırıldı · göster"), a check on the
    ones they approved, and the decisions that no longer match any item in `unmatched`.

    The model's own sentence stays on every item as `model_text`, so evidence, history and the export can
    still be lined up against what the analysis actually said."""
    payload = ensure_item_ids(copy.deepcopy(payload or {}))
    by_item = {}
    for r in rows: by_item.setdefault(r['item_id'], {})[r['action']] = r
    seen = set()
    counts = {}
    for section, key in SECTION_LISTS:
        items = payload.get(key)
        if not isinstance(items, list): continue
        removed = 0
        for it in items:
            if not isinstance(it, dict): continue
            layer = by_item.get(it.get('item_id'))
            it['model_text'] = item_text(it)
            it['section'] = section
            if not layer: continue
            seen.add(it['item_id'])
            edit = layer.get('edit')
            if edit and (edit.get('text') or '').strip():
                it['text'] = edit['text']; it['user_edited'] = True
            gone = layer.get('remove')
            if gone:
                it['removed'] = True; it['remove_reason'] = gone.get('reason'); removed += 1
            if layer.get('confirm'): it['confirmed'] = True
        if removed: counts[key] = removed
    payload['removed_counts'] = counts
    payload['unmatched'] = [{'item_id': r['item_id'], 'section': r['section'], 'action': r['action'], 'text': r['text'],
                             'reason': r['reason'], 'created': r['created'], 'analysis_version': r['analysis_version'],
                             'label': unmatched_label(r)}
                            for r in rows if r['item_id'] not in seen]
    return payload


def unmatched_label(row):
    """What an orphaned decision reads as under its section: "kaldırma · Tekrar", "düzeltme"…"""
    parts = [ACTION_LABELS.get(row['action'], row['action'])]
    if row.get('reason'): parts.append(REASON_LABELS.get(row['reason'], row['reason']))
    return ' · '.join(parts)


def layered(store, mid, payload):
    """`apply_layer` for a stored analysis: reads this meeting's decisions and returns (payload, unmatched)."""
    try: rows = edits(store, mid)
    except Exception: rows = []   # a read must never fail because the layer table is missing or locked
    result = apply_layer(payload, rows)
    return result, result.get('unmatched') or []


def visible(items):
    """The items an export or a report prints: what the user removed is not part of their summary any more."""
    return [i for i in (items or []) if isinstance(i, dict) and not i.get('removed')]


def dispatch_action(store, action, request):
    """The four bridge actions behind the ⋯ menu on a summary item."""
    mid = request.get('meeting') or ''
    if not mid: raise ValueError('Toplantı gerekli')
    item = request.get('item_id') or request.get('item') or ''
    section = request.get('section') or 'summary'
    if action == 'insight_edit': return record(store, mid, item, section, 'edit', text=request.get('text'))
    if action == 'insight_remove': return record(store, mid, item, section, 'remove', reason=request.get('reason'))
    if action == 'insight_confirm': return toggle_confirm(store, mid, item, section, on=request.get('on'))
    if action == 'insight_restore':
        target = request.get('what') or 'remove'
        return undo(store, mid, item, target)
    raise ValueError('Unknown insight action')


__all__ = ['ACTIONS', 'REASONS', 'REASON_LABELS', 'apply_layer', 'dispatch_action', 'edits',
           'ensure_table', 'layered', 'record', 'toggle_confirm', 'undo', 'visible']
