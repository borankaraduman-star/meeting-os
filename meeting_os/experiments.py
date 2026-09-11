"""Silent, cheap, offline experiments: measure the candidate on evidence this Mac already has, and mostly
just write down what it found.

The review asked for a comparison that costs nothing and is never felt (Codex, 11 Sep 2026, #11: "Önce ucuz
adayları kıyaslayın: kişi eşiği, kelime sıralaması, kuyruk sıralaması"). Everything here obeys that
literally:

* **No cloud call, ever.** `quality.compare` re-uploads audio with explicit consent; that is a different tool
  and it is not reachable from this module. Every candidate here is arithmetic over rows already on disk.
* **Never while the Mac is working.** `run_due` refuses when a recording heartbeat is live, when a meeting is
  mid-job, or when the caller says so. The hourly housekeeping is the only caller and it is already the idle
  pass; the check is repeated here because a rule that lives only in the caller is a rule one refactor away
  from gone.
* **At most one experiment per device per day.** The results file is the ledger: a run whose day is already
  in it does nothing.
* **Results are not production data.** `quality/experiments.jsonl` holds counts, thresholds and verdicts. It
  is never read back into `samples`, `rejections`, `taught_words` or `actions`, and nothing in this module
  can write those tables — it has no path to them.
* **Silence is not approval.** A queue item the user never answered is not in the pool at all, and 'skipped'
  is counted as a position, never as a confirmation. The alternative ordering was never on screen, so its
  items may only be judged through decisions the user actually made about items that WERE.

Promotion is off by default (`auto_promote_policies`). With it off, a candidate that meets its pre-registered
goal is written down as a recommendation and the setup card says "otomatik uygulama kapalı". With it on, the
promotion goes through `policy.promote`, which is one `policy.rollback` away from undone.

Retention: 7 days / 20 MB (Codex, "kaynak ve saklama sınırı"), pruned on every run.
"""
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

EXPERIMENT_DIR = 'quality'       # quality.DAILY_DIR
EXPERIMENT_FILE = 'experiments.jsonl'
RETENTION_DAYS = 7
RETENTION_BYTES = 20*1024*1024

MIN_SAMPLES = 20                 # below this nothing is promoted and nothing is recommended: "veri yetersiz"
ORDER_WINDOW = 400               # the last N resolved Kontrol answers the ordering candidate is scored on
ORDER_MIN_GAIN = 1.0             # median position of the corrected items has to improve by a whole place

CANDIDATES = ('identity_bars', 'review_order', 'hint_ranking')
# What each candidate promised BEFORE it was measured. Written into the result so a verdict can never be
# re-read against a goal invented after the numbers came in.
GOALS = {
    'identity_bars': 'doğru otomatik ad ↑, yanlış ↑ değil, n≥20, eşik 0,80–0,95 · marj 0,02–0,15',
    'review_order': 'düzeltilen maddelerin ortanca sırası ≥1 basamak öne gelsin, n≥20',
    'hint_ranking': 'ham STT’de aynı hatanın tekrarı ↓, yeni hata ↑ değil, n≥20',
}


def path(data_dir):
    return Path(data_dir)/EXPERIMENT_DIR/EXPERIMENT_FILE


# ---------------------------------------------------------------- gating

def busy(store=None, data_dir=None, *, recording=None, job=None):
    """Why an experiment must not run right now, or ''. Four independent answers, because each of them has
    been the true one at some point: the caller knows, the recorder's own heartbeat knows, the job
    environment knows, and the meetings table knows."""
    if recording: return 'recording'
    if job: return 'job'
    try:
        if os.environ.get('MEETING_OS_LOW_PRIORITY'): return 'job'
    except Exception: pass
    try:
        if data_dir is not None:
            from .reports import host_dir, load_settings, read_recording_heartbeat
            if read_recording_heartbeat(host_dir(load_settings(data_dir))): return 'recording'
    except Exception: pass
    try:
        if store is not None and store.db.execute("SELECT 1 FROM meetings WHERE status IN ('processing','recording') LIMIT 1").fetchone():
            return 'job'
    except Exception: pass
    return ''


def _day(moment):
    """The LOCAL calendar day, the same one `quality.daily_summary` means by a day. A UTC day would give two
    experiments on one evening in Istanbul and none on the next."""
    try: return moment.astimezone().date().isoformat()
    except Exception: return moment.date().isoformat()


def records(data_dir, limit=200):
    """The last `limit` experiment results, oldest first. Never raises; a missing file is no results."""
    try: text = path(data_dir).read_text(encoding='utf-8')
    except OSError: return []
    out = []
    for raw in text.splitlines()[-limit:]:
        raw = raw.strip()
        if not raw: continue
        try: row = json.loads(raw)
        except ValueError: continue
        if isinstance(row, dict): out.append(row)
    return out


def ran_today(data_dir, now=None):
    day = _day(now or datetime.now(timezone.utc))
    return any(row.get('day') == day for row in records(data_dir, limit=400))


# ---------------------------------------------------------------- candidate: identity bars

def _identity_candidate(store, data_dir):
    """The threshold/margin grid, judged by `quality.calibrate` — time-ordered, human-verified clusters only,
    and already constrained so a candidate may not buy names by inventing them. Nothing is measured twice
    here: this IS the calibration, run without saving over the daily recommendation file."""
    from . import policy as P
    from .quality import calibrate
    report = calibrate(store, data_dir, save=False)
    rec = report.get('recommendation') or {}
    n = int(report.get('n') or 0)
    threshold, margin = rec.get('threshold'), rec.get('margin')
    within = (P.THRESHOLD_RANGE[0] <= float(threshold or 0) <= P.THRESHOLD_RANGE[1]
              and P.MARGIN_RANGE[0] <= float(margin or 0) <= P.MARGIN_RANGE[1])
    meets = bool(rec.get('change')) and n >= MIN_SAMPLES and int(rec.get('wrong_delta') or 0) <= 0
    return {'candidate': 'identity_bars', 'goal': GOALS['identity_bars'], 'n': n,
            'current': report.get('current'), 'proposal': {k: rec.get(k) for k in ('threshold', 'margin', 'correct', 'wrong', 'unknown_named', 'correct_gain', 'wrong_delta')},
            'within_bounds': within, 'meets_goal': bool(meets and within),
            'changes': {'identity_threshold': threshold, 'identity_margin': margin} if meets and within else {}}


# ---------------------------------------------------------------- candidate: review queue ordering

def _resolved(store, limit=ORDER_WINDOW):
    """The last `limit` answered Kontrol items, with the day their meeting was recorded. Only items a person
    actually answered: an item nobody saw contributes no evidence in either direction."""
    import sqlite3
    from .review import severity_of
    try:
        rows = store.db.execute('''SELECT r.meeting AS meeting, r.item_key AS item_key, r.kind AS kind, r.result AS result,
                                          m.created AS created FROM review_results r LEFT JOIN meetings m ON m.id=r.meeting
                                   ORDER BY r.id DESC LIMIT ?''', (int(limit),)).fetchall()
    except (sqlite3.OperationalError, sqlite3.DatabaseError): return []
    out = [{'meeting': r['meeting'] or '', 'item_key': r['item_key'] or '', 'result': r['result'] or '',
            'created': r['created'] or '', 'severity': severity_of(r['kind'] or (r['item_key'] or '')),
            'start': None} for r in rows]
    # Deterministic input order: the ranking below is stable, so the list it starts from decides every tie.
    out.sort(key=lambda row: (row['meeting'], row['item_key']))
    return out


def _median(values):
    if not values: return None
    rows = sorted(values); half = len(rows)//2
    return float(rows[half]) if len(rows) % 2 else (rows[half-1]+rows[half])/2.0


def _positions(pool, order):
    from .review import order_debt
    return {(row['meeting'], row['item_key']): i+1 for i, row in enumerate(order_debt(pool, order))}


def _order_candidate(store, data_dir):
    """Would the other ordering have put the items the user actually CORRECTED earlier in the queue?

    The pool is every answered item, in the positions each ordering would have given it. The score is the
    median position of the items answered 'corrected' — the ones that turned out to be real work. 'correct'
    and 'skipped' items hold positions and are never counted as a win: passing on an item says nothing, and
    an item that was already right was not work the ordering should have hurried."""
    from . import policy as P
    from .review import CORRECTED
    pool = _resolved(store)
    live = P.current(data_dir)['review_order']
    other = next(name for name in P.REVIEW_ORDERS if name != live)
    corrected = [row for row in pool if row['result'] == CORRECTED]
    n = len(pool)
    result = {'candidate': 'review_order', 'goal': GOALS['review_order'], 'n': n, 'corrected': len(corrected),
              'current': {'order': live}, 'proposal': {'order': other}, 'within_bounds': True,
              'meets_goal': False, 'changes': {}}
    if not corrected or n < MIN_SAMPLES:
        result['reason'] = f'veri yetersiz (n={n}, düzeltilen={len(corrected)}, en az {MIN_SAMPLES})'
        return result
    here = _positions(pool, live); there = _positions(pool, other)
    keys = [(row['meeting'], row['item_key']) for row in corrected]
    live_median = _median([here[key] for key in keys]); other_median = _median([there[key] for key in keys])
    gain = round(live_median-other_median, 2)
    result['current']['median_position'] = live_median
    result['proposal']['median_position'] = other_median
    result['proposal']['gain'] = gain
    result['meets_goal'] = gain >= ORDER_MIN_GAIN
    if result['meets_goal']: result['changes'] = {'review_order': other}
    return result


# ---------------------------------------------------------------- candidate: hint ranking

def _hint_candidate(store, data_dir):
    """1.2.84's ranked STT hint, replayed against the old insertion order. `quality.replay_rules` is that
    replay and it lands on the words branch; until it does, this candidate reports that it could not be
    measured, which is a different answer from "measured and no good"."""
    from . import policy as P
    from . import quality
    replay = getattr(quality, 'replay_rules', None)
    live = P.current(data_dir)['hint_ranking']
    if not callable(replay):
        return {'candidate': 'hint_ranking', 'goal': GOALS['hint_ranking'], 'n': 0, 'available': False,
                'current': {'ranking': live}, 'within_bounds': True, 'meets_goal': False, 'changes': {},
                'reason': 'quality.replay_rules bu dalda yok; ölçülemedi'}
    out = replay(store) or {}
    n = int(out.get('n') or 0)
    better = out.get('ranked') or {}; baseline = out.get('legacy') or {}
    repeats_down = int(better.get('repeat_errors') or 0) <= int(baseline.get('repeat_errors') or 0)
    new_errors_flat = int(better.get('new_errors') or 0) <= int(baseline.get('new_errors') or 0)
    meets = n >= MIN_SAMPLES and repeats_down and new_errors_flat and int(better.get('repeat_errors') or 0) < int(baseline.get('repeat_errors') or 0)
    proposed = 'ranked' if meets else live
    return {'candidate': 'hint_ranking', 'goal': GOALS['hint_ranking'], 'n': n, 'available': True,
            'current': {'ranking': live, **baseline}, 'proposal': {'ranking': 'ranked', **better},
            'within_bounds': True, 'meets_goal': bool(meets and proposed != live),
            'changes': {'hint_ranking': proposed} if meets and proposed != live else {}}


# ---------------------------------------------------------------- the run

def auto_promote(data_dir):
    """Is this Mac allowed to APPLY what an experiment measured? Off unless the user turned it on."""
    try:
        from .reports import load_settings
        return bool(load_settings(data_dir).get('auto_promote_policies'))
    except Exception:
        return False


def run_due(store, data_dir, now=None, *, recording=None, job=None):
    """The whole experiment pass, called once an hour from `storage_housekeeping` and doing something at most
    once a day. Never raises: a measurement is not worth failing housekeeping for."""
    moment = now or datetime.now(timezone.utc)
    data_dir = Path(data_dir)
    try:
        blocked = busy(store, data_dir, recording=recording, job=job)
        if blocked: return {'ran': False, 'reason': blocked, 'results': [], 'promoted': []}
        if ran_today(data_dir, moment): return {'ran': False, 'reason': 'daily_cap', 'results': [], 'promoted': []}
        allowed = auto_promote(data_dir)
        results = []; promoted = []
        for name, measure in (('identity_bars', _identity_candidate), ('review_order', _order_candidate), ('hint_ranking', _hint_candidate)):
            try: result = measure(store, data_dir)
            except Exception as exc: result = {'candidate': name, 'goal': GOALS[name], 'n': 0, 'meets_goal': False,
                                               'changes': {}, 'error': type(exc).__name__}
            result['auto_promote'] = allowed
            result['verdict'] = _verdict(result, allowed)
            if result['verdict'] == 'promoted':
                applied = _promote(store, data_dir, result, moment)
                result['policy_version'] = applied
                result['verdict'] = 'promoted' if applied else 'recommended'
                if applied: promoted.append(name)
            results.append(result)
        _append(data_dir, results, moment)
        prune(data_dir, now=moment)
        return {'ran': True, 'reason': '', 'day': _day(moment), 'results': results, 'promoted': promoted,
                'auto_promote': allowed}
    except Exception:
        return {'ran': False, 'reason': 'error', 'results': [], 'promoted': []}


def _verdict(result, allowed):
    if result.get('error'): return 'error'
    if result.get('available') is False: return 'unavailable'
    if not result.get('meets_goal'): return 'insufficient' if int(result.get('n') or 0) < MIN_SAMPLES else 'recorded'
    return 'promoted' if allowed else 'recommended'


def _promote(store, data_dir, result, moment):
    """Apply one candidate. `policy.promote` re-checks the bounds: this module having decided a number is
    inside the range is not the same as it being inside the range."""
    from . import policy as P
    try:
        evidence = {'experiment': result.get('candidate'), 'goal': result.get('goal'), 'n': result.get('n'),
                    'measured': _day(moment), 'current': result.get('current'), 'proposal': result.get('proposal')}
        return P.promote(data_dir, result.get('changes') or {}, evidence, store=store)['version']
    except Exception:
        return None


def _append(data_dir, results, moment):
    """One line per candidate, appended at 0600. Counts, thresholds and verdicts — no meeting id, no word, no
    name: this file is a measurement log, not a second copy of the meeting database."""
    try:
        from . import __version__
    except Exception: __version__ = None
    target = path(data_dir)
    try:
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        exists = target.exists()
        with open(target, 'a', encoding='utf-8') as handle:
            for result in results:
                handle.write(json.dumps({'time': moment.isoformat(), 'day': _day(moment),
                                         'app_version': __version__, **result}, ensure_ascii=False)+'\n')
        if not exists:
            try: os.chmod(target, 0o600)
            except OSError: pass
    except OSError:
        pass


def prune(data_dir, *, days=RETENTION_DAYS, max_bytes=RETENTION_BYTES, now=None):
    """7 days / 20 MB, oldest first. Experiment results are the shortest-lived thing this app keeps: they are
    evidence for a decision that has already been made or declined, and a week is long enough to read them."""
    target = path(data_dir)
    try: lines = target.read_text(encoding='utf-8').splitlines()
    except OSError: return {'removed': 0, 'rows': 0, 'bytes': 0}
    moment = now or datetime.now(timezone.utc)
    horizon = (moment-timedelta(days=max(1, int(days)))).isoformat()
    kept = []
    for raw in lines:
        if not raw.strip(): continue
        try: stamp = json.loads(raw).get('time')
        except ValueError: continue                      # an unparseable line is not kept: it cannot be aged
        if isinstance(stamp, str) and stamp < horizon: continue
        kept.append(raw)
    removed = len([raw for raw in lines if raw.strip()])-len(kept)
    size = sum(len(raw.encode('utf-8'))+1 for raw in kept)
    while size > max_bytes and kept:
        drop = max(1, len(kept)//10)
        kept = kept[drop:]; removed += drop
        size = sum(len(raw.encode('utf-8'))+1 for raw in kept)
    try:
        from .reports import publish
        publish(target, ''.join(raw+'\n' for raw in kept))
    except OSError: pass
    return {'removed': removed, 'rows': len(kept), 'bytes': size}


def summary(data_dir, limit=len(CANDIDATES)):
    """The most recent verdict per candidate, for the setup card and the CLI. Counts only."""
    latest = {}
    for row in records(data_dir, limit=200):
        name = row.get('candidate')
        if name in CANDIDATES: latest[name] = row
    return {'day': max((row.get('day') or '' for row in latest.values()), default=''),
            'candidates': [latest[name] for name in CANDIDATES if name in latest][:max(1, int(limit))]}
