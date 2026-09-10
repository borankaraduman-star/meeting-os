#!/usr/bin/env python3
"""Side-by-side table of `benchmark-analysis-cloud.py` runs made with different models (Boran, 10 Sep 2026:
"deepseek vs ile de kıyasla, en sağlam ve en ekonomik model"). Reads build/benchmark-model-*.json and prints one
row per model: checks passed, verbatim/verified evidence ratio, leaks, missing expected tasks/decisions,
duplicates, Turkish issues, mean seconds per case, measured spend and the projected cost of a 2-hour meeting.

    .venv/bin/python scripts/benchmark-compare-models.py [--json out.json] [build/benchmark-model-*.json]
"""
import argparse, glob, json, sys
from pathlib import Path

TWO_HOUR_PROMPT_TOKENS = 60_000     # ≈ 2 h Turkish transcript through the chunked analysis (measured 9 Sep: 41 min ≈ 20k)
TWO_HOUR_COMPLETION_TOKENS = 6_000


def load(path):
    d = json.loads(Path(path).read_text())
    cases = d.get('cases') or []
    checks_total = sum(len(c.get('checks') or {}) for c in cases)
    checks_ok = sum(sum(1 for v in (c.get('checks') or {}).values() if v) for c in cases)
    passed = sum(1 for c in cases if c.get('passed'))
    ev = [c.get('evidence') or {} for c in cases]
    def mean(key):
        vals = [e[key] for e in ev if isinstance(e.get(key), (int, float))]
        return round(sum(vals)/len(vals), 3) if vals else None
    leaks = sum(len(c.get('forbidden_leaks') or []) for c in cases)
    missing = sum(len(c.get('missing_expected') or []) for c in cases)
    missing_dec = sum(len(c.get('missing_decisions') or []) for c in cases)
    dups = sum(len((c.get('duplicates') or {}).get('exact') or []) + len((c.get('duplicates') or {}).get('near') or []) for c in cases)
    turkish = sum(len(c.get('turkish_issues') or []) for c in cases)
    secs = [c.get('elapsed_seconds') for c in cases if isinstance(c.get('elapsed_seconds'), (int, float))]
    spend = d.get('spend') or {}
    prices = None
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        from meeting_os.openrouter import ANALYSIS_PRICES
        prices = ANALYSIS_PRICES.get(d.get('model'))
    except Exception: pass
    two_hours = round((TWO_HOUR_PROMPT_TOKENS*prices[0] + TWO_HOUR_COMPLETION_TOKENS*prices[1])/1e6, 3) if prices else None
    errors = [c.get('error') for c in cases if c.get('error')]
    return {'model': d.get('model'), 'cases': len(cases), 'passed': passed, 'checks': f'{checks_ok}/{checks_total}',
            'verbatim': mean('verbatim_ratio'), 'verified': mean('verified_ratio'), 'leaks': leaks, 'missing_tasks': missing,
            'missing_decisions': missing_dec, 'duplicates': dups, 'turkish_issues': turkish,
            'mean_seconds': round(sum(secs)/len(secs), 1) if secs else None, 'calls': spend.get('calls'),
            'spend_usd': spend.get('estimated_cost_usd'), 'two_hour_usd': two_hours, 'errors': len(errors), 'error_sample': (errors[0] if errors else '')[:80]}


def score(r):
    """Robustness first, then cost: a model that leaks, drops a task or breaks a check is out regardless of price."""
    hard = (r['errors'] == 0, r['leaks'] == 0, r['missing_tasks'] == 0, r['missing_decisions'] == 0)
    return (sum(hard), r['passed'], r['verified'] or 0, r['verbatim'] or 0, -(r['duplicates'] + r['turkish_issues']), -(r['two_hour_usd'] or 9))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('files', nargs='*')
    ap.add_argument('--json')
    a = ap.parse_args()
    files = a.files or sorted(glob.glob(str(Path(__file__).resolve().parents[1]/'build'/'benchmark-model-*.json')))
    rows = sorted((load(f) for f in files), key=score, reverse=True)
    cols = ['model', 'cases', 'passed', 'checks', 'verified', 'verbatim', 'leaks', 'missing_tasks', 'missing_decisions', 'duplicates', 'turkish_issues', 'errors', 'mean_seconds', 'spend_usd', 'two_hour_usd']
    print('| ' + ' | '.join(cols) + ' |'); print('|' + '---|'*len(cols))
    for r in rows:
        print('| ' + ' | '.join('' if r.get(c) is None else str(r.get(c)) for c in cols) + ' |')
    if a.json: Path(a.json).write_text(json.dumps(rows, ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
