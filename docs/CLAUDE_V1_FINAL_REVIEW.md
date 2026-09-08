Reviewed the consolidation and draft-lifecycle code. Three concrete issues:

**1. `prepare()` — race condition allows duplicate drafts** (`meeting_os/assistant.py`)
The "return existing draft if present" check (`existing=[...]`) runs *before* the LLM call and *before* the write transaction. The transaction later re-validates only that the task itself hasn't changed (`current['stale']`, state, `task_hash`) — it never re-checks whether another concurrent `prepare()` call already inserted a non-stale draft. Two overlapping calls for the same task (double-click, retried request after a slow LLM response) will both pass the initial check, both call the LLM, and both insert distinct drafts with different `did`s. This breaks the "single active draft per task" invariant `existing[0]`/`prepared[0]` rely on elsewhere, and wastes an extra local LLM inference. Fix: re-query for an existing non-stale draft for `tid` inside the `BEGIN IMMEDIATE` block before inserting.

**2. `reconcile_actions` — empty-token titles can never be reconciled** (top of file)
```python
tokens=[t for t in normalize(action['title']).split() if len(t)>=4]
later=[r for r in rows if r['start']>last and reversal.search(r['text']) and any(t in normalize(r['text']) for t in tokens)]
```
If every word in `action['title']` is under 4 characters (plausible for terse titles), `tokens` is empty, so `any(...)` over an empty sequence is always `False`. `later` is then always empty regardless of what happens later in the transcript, so `retain` stays `True` unconditionally — the task can never be detected as cancelled/completed/transferred, silently defeating the retraction safety net for short-titled tasks.

**3. `handoff()` doesn't block done/dismissed tasks** (`meeting_os/assistant.py`)
`prepare()` explicitly refuses to build a draft for a task in `('done','dismissed')`, but `handoff()` only checks `task['stale']`:
```python
def handoff(store,tid,path):
    mem=Memory(store);task=mem.task(tid)
    if task['stale']:raise ValueError(...)
```
A task marked done or dismissed (but not stale) can still be exported as a "package to hand off" to Codex/ChatGPT/Claude Code, producing an actionable file for work the user already completed or explicitly discarded. This is inconsistent with `prepare()`'s lifecycle guard and should carry the same `state in ('done','dismissed')` check.
