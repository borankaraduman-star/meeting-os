# Reliability audit — 1.2.86, before the teammate handout

**13 Eylül 2026 · adversarial read of the critical paths · read-only**

Boran: *"uygulama rock solid olmalı, ne kaldı?"* The app is about to go to 3–5 non-technical teammates as a
downloadable bundle. It is judged here against the four promises: **never lose a recording, never strand a
user, never slow a meeting, never leak text to the cloud.**

The fourth promise holds. I traced every upload and every write into the team mirror and found **no path by
which meeting text leaves the Mac without the user ticking the box** (details at the end). The first three
each have a way to break, and two of them break silently.

Fifteen findings. Five are reproduced as tests in `tests/test_audit_repro.py`, marked
`@unittest.expectedFailure` so the suite stays green until they are fixed — fixing one turns it into an
unexpected success, which unittest reports as a failure, so the marker must come off in the same commit.

Baseline: `python -m unittest discover -s tests` is **1224 tests, 40 failures, all
`MemoryPressureError`** — the known memory-pressure quirk of this Mac, not regressions.

---

## P0 — fix before the bundle goes out

### 1. The mic gate silently throws away the owner's half of every non-Zoom meeting

`meeting_os/cloud_finalize.py:338` · `desktop/Sources/MeetingOS/MicGate.swift:30` ·
`desktop/Sources/MeetingOS/ZoomMute.swift:8`

`MicGate.mode` defaults to `zoom` (`MicGate.swift:20`), and the rule is
`(zoomOpen && zoomMuted==false)`. `zoomMuted` is `nil` — treated as muted, deliberately — whenever Zoom is
not running, whenever there is no meeting, and whenever the Mac has not granted Accessibility. ZoomMute's own
docstring says so. The app then journals one `off` line at t=0 and never another. `mic_gate_windows`
(`cloud_finalize.py:752`) turns that into `[]` — an empty list, **not** `None` — and `gate_overlap([], …)`
returns `0.0`, so every mic piece is dropped as `mic_gated` at `cloud_finalize.py:338`.

**Scenario.** A teammate runs their standup on Google Meet (or Teams, or a phone call, or Zoom on a Mac where
they never found the Accessibility toggle). They record an hour. The transcript contains every other
participant and **not one word they said themselves**. Nothing warns them: `mic_gated_windows` is computed at
`cloud_finalize.py:914` but goes only into the telemetry report (`reports.py:426`) — it is on no screen.
The meeting then reaches `complete`, so re-finalizing returns early at `cloud_finalize.py:857` and there is no
way back from the UI.

Reproduced — `MicGateTests.test_a_gate_that_never_opened_still_transcribes_the_owner`:
```
windows = []   uploads = 1   sources in transcript = ['system']   mic_gated_windows = 1
```

**Smallest fix.** A gate that never opened once is not a gate. In `mic_gate_windows`, return `None` (the
"transcribe everything" answer) when the events produced no open window — the owner's track is only dropped
on evidence that the gate really was watched and really was closed:
```python
if not windows: return None
```
Worth pairing with: default `micMode` to `always` for this handout, and make the gate's mode explicit in the
welcome flow. A gate that guesses "closed" loses data just as surely as one that guesses "open" leaks it.

### 2. A finished, paid-for transcript is demoted to `incomplete` by a bookkeeping failure

`meeting_os/cloud_finalize.py:924-938`

```
924   store.status(mid,'complete');emit('complete')
925   compact_capture(store,mid)
927   archive_meeting(store,mid)
930   write_meeting_report(store,mid,data_dir,version=__version__)
933  except BaseException as exc:
934   store.status(mid,'incomplete')
936   if isinstance(exc,Exception): note_cloud_failure(store,mid,exc)
```

The transcript is committed at 923–924. Everything after it is housekeeping — yet it sits inside the same
`except BaseException`, which flips the meeting back to `incomplete` and schedules a cloud retry.
`compact_capture` opens a write transaction (`cloud_finalize.py:817`) and so does `archive_meeting`
(`audio_archive.py:57`); an ordinary `database is locked` from the 2 s poll or the hourly pass is enough. So
is a `MemoryError` in the FLAC encode under pressure.

**Scenario.** The meeting finishes, the user sees it complete, and a second later it turns red with
`database is locked`. The transcript is sitting in the database, fully paid for. The team report at 930 never
runs, so the team never receives the meeting; one of the thirty retries is spent (`note_cloud_failure`).

Reproduced — `FinalizeAtomicityTests.test_a_complete_transcript_survives_a_failing_post_complete_step`:
```
raised: database is locked | status now = incomplete | segments in DB = 1 ['Tam transkript.']
cloud_error = database is locked | retry_attempt = 1
```

**Smallest fix.** Move 925–930 out of the guarded block — they are post-completion chores, each already
tolerant of its own failures:
```python
        except BaseException as exc:
            ...
            raise
        for step in (lambda: compact_capture(store,mid), lambda: archive_meeting(store,mid),
                     lambda: write_meeting_report(store,mid,data_dir,version=__version__)):
            try: step()
            except Exception: pass   # the transcript is committed; tidying may fail
        return {...}
```

### 3. One unreachable folder stops every later housekeeping step — permanently, and in silence

`meeting_os/desktop.py:810-843` · `desktop/Sources/MeetingOS/ModelActions.swift:132`

`storage_housekeeping` is one unguarded straight line: `archive_all` → **`team_sync`** → audio retention →
text retention → `prune_learning` → `calibration_refresh` → `team_effect_refresh` → experiments →
preferences → task errors. `team_knowledge.sync` at :819 touches a shared folder that may be an unmounted
network volume, a signed-out iCloud Drive or a revoked permission. When it raises, **nothing after it runs.**

And the caller throws the error away: `ModelActions.swift:132` is
`if …, let r = try? await requestSlow(["action":"storage_housekeeping"])`. The user is never told.

**Scenario.** A teammate's team folder lives on an office NAS. They work from home. Every hour, and at every
launch, the pass dies at step two. Audio retention never runs, text retention never runs, the learning event
log is never pruned, calibration never refreshes, experiments never run — for months, while the disk fills
with recordings the retention setting promised to remove. The one thing the user did configure is the one
thing that silently stopped.

Reproduced — `HousekeepingIsolationTests.test_retention_and_pruning_still_run_when_the_team_sync_fails`:
```
HOUSEKEEPING RAISED: OSError [Errno 5] Input/output error
steps that ran after the failing team sync: []
```

**Smallest fix.** Isolate each step and report what failed rather than aborting:
```python
def step(name, fn, default=None):
    try: return fn()
    except Exception as exc: failures[name]=type(exc).__name__; return default
```
Then surface `failures` in the returned dict so the Settings card can say "team sync failed 14 times".

### 4. The updater installs unverified code, and stops macOS from checking it

`meeting_os/updater.py:300,326` · `scripts/swap-update.sh:75`

`run_download` verifies a sha256 (`updater.py:326`), but the hash arrives from `latest.json` on the **same
origin over the same path** as the payload (`updater.py:300`). That is an integrity check against truncation
— not authenticity. Whoever can serve that URL serves both halves. There is no `codesign --verify` and no
`spctl --assess` anywhere in the update path (verified by grep across `updater.py`, `swap-update.sh` and
`Updater.swift`), and `swap-update.sh:75` actively strips the quarantine flag:
```sh
/usr/bin/xattr -d -r com.apple.quarantine "$TARGET" 2>/dev/null || true
```
so Gatekeeper never evaluates the signature either. `bundle_base` (`updater.py:168-174`) accepts any
`download_base` out of `runtime.json` with no scheme check, while `team_cloud._safe_url` (`team_cloud.py:400`)
is the validation pattern that exists elsewhere in this repo and is missing here.

**Scenario.** A hijacked or mistyped download host is arbitrary code execution as the user, on all 3–5 Macs
at once, delivered by the app's own auto-update. This is the single highest-blast-radius finding here.

**Smallest fix.** After `ditto` and before the swap:
```python
subprocess.run(['/usr/sbin/spctl','--assess','--type','execute',str(app)],check=True)
```
and keep the quarantine strip only on the far side of that check.

### 5. An empty analysis is saved, cached, and presented as the finished summary

`meeting_os/schemas.py:8` · `meeting_os/intelligence.py:600` · `meeting_os/assistant.py:33,68`

`schemas.py:8` sets `maxItems` on every category but no `minItems`, and `_analyze_chunk`
(`intelligence.py:600`) only checks that the keys are present. `{"summary":[],"decisions":[],…}` therefore
validates, `compact_summary` never runs (`while len([]) > target` is false), and `assistant.py:68` saves it.
Then `assistant.py:33` — `if previous and not previous['stale'] and not force: return previous` — serves that
empty payload back forever.

**Scenario.** A teammate presses **Analiz**. The summary comes back blank. They press it again. Nothing
changes, because the empty analysis is cached and not stale. There is no path forward from the UI. Note the
team already defended the analogous case for tasks at `memory.py:251`; the summary has no such guard.

**Smallest fix.** `"minItems": 1` on `summary` in `schemas.py:8` — nothing was extracted, so save nothing and
let the error say so.

---

## P1 — fix in the first week

### 6. A truncated `team.token` silently moves a Mac out of the team

`meeting_os/team_cloud.py:104-108,118-126,139`

`_write_token` is a non-atomic `O_TRUNC` write with no fsync. A crash, a full disk or a kill during `join()`
(`team_cloud.py:309`) leaves an empty file. The next `token()` call reads `''`, falls through to deriving one
from the *current* OpenRouter key (:139), and `_remember_token` — which refuses to overwrite **only when the
existing content already matches `TOKEN_RE`** (:124) — happily writes the derived value over the blank.

If the user has rotated their API key since joining (the case the function's own docstring exists for), they
get a *different* team id. `mirror_dir` (:246) and `state_path` (:479) both move to a new folder, abandoning
every pulled report and all push/pull state. Nobody is told. `token()` is called from nearly every path
(`configured` :265, `status` :566, `mark_outbox` :537) across three concurrent one-shot processes, so it is
also reachable as a plain race against `join()`'s truncate window.

**Smallest fix.** Two lines: route `_write_token` through the atomic `_write_private` (`team_cloud.py:673`,
already in this file), and open with `O_CREAT|O_EXCL` in `_remember_token` so it can never overwrite anything.

### 7. Opening an upgraded database holds the write lock and loses the migration

`meeting_os/store.py:67,103-111`

`_backfill_sample_dates` ends in a bare `executemany` with no `with self.db:` — unlike `_backfill_feedback`
(`store.py:275`), which gets it right. The implicit transaction is never committed.

Precision worth recording: on a true 1.2.64 database this is **masked**, because the very next migration
(`store.py:76`) runs `_backfill_feedback`, whose `with self.db:` commits the pending transaction by accident.
It bites on a database that already has `corrections.feedback` but not `samples.created`:
```
in_transaction right after Store.__init__ : True
second process write FAILED after 1.1s: database is locked
samples.created after close(): [(1, None)]   samples has `created` column now? True
```
So the lock is held for the life of the process — including the recorder supervisor, which keeps a Store open
for the whole meeting — and the backfill is rolled back while the column survives, so the
`if 'created' not in sample_columns` guard never fires again and the dates are gone for good.

Reproduced — `MigrationTests.test_upgrading_an_old_database_does_not_hold_the_write_lock`.

**Smallest fix.** `with self.db:` around the `executemany` at `store.py:111`.

### 8. Every parallel chunk's cost is silently dropped, and the wrong model is recorded

`meeting_os/store.py:39` · `meeting_os/assistant.py:19` · `meeting_os/openrouter.py:320,333-343`

`contextvars` propagation is correct — `intelligence.py:627` does use `copy_context().run`. The bug is one
layer down: `store.py:39` is `sqlite3.connect(path)` with no `check_same_thread=False`, so the usage sink
(`assistant.py:19`) raises `ProgrammingError` in every worker thread, swallowed at `store.py:668` and again at
`openrouter.py:343`. Measured: `recorded usage rows: 0, suppressed sink errors: 2`. Every meeting long enough
to chunk — i.e. every real meeting — reports the bulk of its spend as **$0**.

Two more in the same neighbourhood: `openrouter.py:320` mutates `self.model_id` on fallback, and that object
is shared by all workers (`intelligence.py:627`), so one chunk hitting a 429 rewrites the model for every
chunk still in flight and `assistant.py:68` records the analysis as 100 % fallback model (masked today only
because default == fallback, `openrouter.py:284-285`). And the retries at `openrouter.py:327-337` re-`_post`
and overwrite `result`, while the sink at :338 reads only the final one — the first call is paid for and
invisible (measured: 2 upstream calls, 1 usage row, 0.006 recorded against 0.056 spent).

**Smallest fix.** `check_same_thread=False` plus a `threading.Lock` around `record_analysis_usage`
(`store.py:658`); return the model that answered instead of mutating `self`; record after each `_post`.

### 9. One bad chunk throws away every chunk the user already paid for

`meeting_os/intelligence.py:627-630,660-703`

Good news: no partial analysis is ever written — `fut.result()` re-raises before `save_analysis`, and
ordering is safe. The cost is the problem. The `with ThreadPoolExecutor` exit calls `shutdown(wait=True)`
with no `cancel_futures`, so after the first failure **all remaining chunks run and bill anyway** (measured:
5 of 5 chunks paid, analysis raised). Worse, `compact_summary` (:660-680) and `reconcile_actions` (:690-703)
raise with no retry at all — so a cheap 160-token follow-up call coming back malformed discards six paid
chunks. `_analyze_chunk` gets a schema-nudge retry (:596-603); the follow-ups get nothing.

**Smallest fix.** `cancel_futures=True` on the failure path, and on a merge failure fall back to the
already-validated `result['summary']` truncated to target. Degraded output beats losing the whole analysis.

### 10. The heaviest pass in the product runs at every launch and does not stop for a recording

`desktop/Sources/MeetingOS/ModelActions.swift:122-132`

`lastHeartbeat` (`App.swift:790`) is a plain in-memory var, nil at launch, so `heartbeatIfDue()` is due on the
first poll of every run. It then calls `storage_housekeeping` — FLAC re-encode of the whole library, team
sync, retention, two calibration replays, experiments. The `!recording, recordProcess==nil, job==nil` guard is
evaluated only *before* the call (:123 and :132); nothing re-checks, and `callSlow`'s 600 s watchdog has no
cancellation.

**Scenario.** Teammate opens the app at 08:59, the sweep starts, they press ⌃⌥R at 09:00 and record their
first meeting while the Mac re-encodes every recording they own. Three restarts a day, three sweeps.

**Smallest fix.** Persist `lastHeartbeat` in `UserDefaults` so a restart does not re-arm it, and have the
Python pass check for an active recording between steps (the heartbeat file at `reports.py:331` already says).

### 11. A concurrent recording and job share one log file and truncate it under each other

`desktop/Sources/MeetingOS/App.swift:488-490`

`createFile` truncates, the handle is not `O_APPEND`, and recording + job are explicitly allowed to run
together (`App.swift:479-484`). Two children then write at independent offsets into one inode. Since
`ErrorPresentation.logSummary(log)` (`App.swift:499`) reads the tail of that shared file, **a failed finalize
can report the recorder's last line as its error** — the user is shown a diagnosis belonging to a different
process. Reproduces on: stop meeting A → finalize starts → start meeting B.

**Smallest fix.** One log per job: `last-job-<uuid>.log`, or open with `O_APPEND` and prefix each line.

### 12. A dead download leaves the update spinning forever, with retry blocked

`desktop/Sources/MeetingOS/App.swift:1147-1154` · `desktop/Sources/MeetingOS/Updater.swift:50-51,76-78`

The poll loop is `while true` with `continue` on failure and **no deadline**. If the detached download worker
dies (logout, OOM, sleep), `update-status.json` stays at `downloading`, the UI shows
"Yeni sürüm indiriliyor · %37" indefinitely, and `updating` stays `true` — so the `guard … !updating` at
:1136 means the user can never press the button again without quitting. The stall detector exists
(`Updater.swift:50-51`) but is wired only to the git channel's `running` state (:76-78); `downloading`,
`verifying`, `extracting` and `swapping` have no staleness handling.

**Smallest fix.** Apply the same `stallSeconds` check to the bundle states, and reset `updating` when the
status timestamp stops moving.

### 13. ⌘Q blocks the main thread on a bridge call, and can never finish

`desktop/Sources/MeetingOS/App.swift:1093-1099,1285,570`

`saveUserNameOnQuit()` calls `invoke(...)` directly from `@MainActor`, spawning a Python interpreter and
blocking the main thread until it answers or is SIGTERMed at 10 s. It triggers in exactly the first-launch
flow: Ayarlar → Genel → type your name → ⌘Q. Meanwhile `.terminateLater` (:1285) has no deadline — the only
`reply(toApplicationShouldTerminate:true)` is at :514, inside a child's termination handler, behind another
bridge round-trip. And `stop()` (:570) sends SIGINT once, never escalates, and flips `recording` false on the
same line, so a second press is a no-op and every stop control is disabled. A teammate whose supervisor is
wedged has one move: Force Quit.

**Smallest fix.** Make the name save fire-and-forget on field change rather than on quit; add a deadline to
`.terminateLater`; escalate `stop()` to SIGTERM after a few seconds.

### 14. Every summary and Kontrol decision is recorded blank — the learning loop measures nothing

`meeting_os/insight_layer.py:92` · `meeting_os/review.py:138` · `meeting_os/learning.py:30-48,105`

Both call sites pass `meeting=mid`, which `record_event` has no parameter for. The `TypeError` lands on the
defensive fallback at `insight_layer.py:34-36`, which retries as `record_event(store, action)` — **no object,
no outcome, no scope**:
```
{'action': 'summary_edit', 'object': None, 'scope': 'meeting', 'outcome': 'applied'}
```
Independently, `summary_remove` and `summary_confirm` are not in `learning.ACTIONS` (`learning.py:30-48`) and
are dropped entirely, and the comment at `learning.py:37` ("reserved for 1.2.81; nothing writes it yet") is
stale — 1.2.81 does write it. The learning loop shipped in 1.2.80–1.2.86 is recording nothing usable here.

Reproduced — `LearningLoopTests.test_a_summary_decision_records_which_item_it_was`.

**Smallest fix.** Drop `meeting=` from both call sites, add the two missing actions to `ACTIONS`, and pass the
reason via `reason=` rather than `outcome=`.

### 15. Joining a team runs a 20 s network sync behind the 10 s watchdog

`meeting_os/team_cloud.py:466,90` · `meeting_os/desktop.py:402-413` ·
`desktop/Sources/MeetingOS/ModelActions.swift:456`

`accept_invite` ends with `'synced': sync(data)`, whose budget is 20 s plus up to 20 s waiting on `_PASS`.
`team_join` is dispatched from the **fast** block and called with `request(...)` — the default 10 s SIGTERM
watchdog. On a new teammate's very first launch, a slow server means the process is killed at 10 s: the sheet
reports a failure, **but the token was already written at :309, so the Mac is joined.** The user retries or
gives up, with the app's story and reality disagreeing. Worst case the kill lands inside `_save_state`'s
non-atomic truncate window (`team_cloud.py:495-496`), and the next pass re-downloads up to 300 reports.

**Smallest fix.** `sync(data, budget=6)` at `team_cloud.py:466`, or route `team_join` through `requestSlow`.

---

## Also noted, not worth a numbered slot

- **Unbounded tables.** `analyses` keeps one full summary JSON per re-analysis with no cap;
  `review_results` is keyed on the transcript hash (`review.py:85`), so every correction makes every
  answered item a new row forever. Only `learning_events` is pruned — and that prune is reachable only from
  the housekeeping pass that finding 3 can stop.
- **Pruned teammate reports are re-downloaded every pass, forever** (`team_cloud.py:893` vs `:1010`): prune
  keeps the digest but deletes the file, and `_pull_file` requires both.
- **Updater swap on a second volume** (`scripts/swap-update.sh:63-68`): `mv` degrades to copy-then-delete, so
  the disappear window becomes minutes and the rollback moves the old app *inside* a partial target. On the
  normal same-volume install the script is sound — two renames, with a working restore.
- **`similarity` treats containment as identity** (`intelligence.py:417`), so a re-analysis bullet that
  *extends* a bullet the user removed inherits its id and stays hidden. The new fact never surfaces.
- **SIGPIPE is not ignored** in `desktop/Sources` (`App.swift:113`), unlike the capture helper
  (`capture/.../main.swift:188`); a child that exits in the write window kills the app with exit 141.
- **`Bundle.main.resourceURL!`** (`App.swift:161`) is a force unwrap one line above the code whose whole
  purpose is surviving a broken bundle.
- **`Memory.search`** (`memory.py:320`) scans every segment of every meeting with no index or LIMIT, and
  `Memory.task` makes `drafts()` O(n²). Latency grows with the library forever — worth a ticket given
  "yıllarca dokunmadan".

## Verified clean

- **Text never leaves the Mac outside the whitelist.** All five upload kinds go through `_own_files`
  (`team_cloud.py:823-858`). With `share_text` off, `_anonymous` (:762) drops the transcript, nulls the title
  and hashes both the meeting id and the filename, then rebuilds through `telemetry_schema.filter` — a strict
  positive whitelist in which **no type accepts a sentence** (`telemetry_schema.py:15-19,159-183`). Summaries,
  task titles, quotes and error strings have no field to travel in. Taught words come only from explicit user
  corrections (`correction_memory.py:228-240`) and glossary entries only from an explicit import
  (`desktop.py:623`); nothing auto-harvests transcript text into either.
- **The 10 s bridge watchdog is sound.** `desktop.py:1004` calls `os.setpgrp()`, so the group kill at
  `App.swift:110` really does take a stuck child with it.
- **An app crash mid-recording is handled.** `live.py:197` (`os.getppid()==1`) stops cleanly, the `finally`
  at `live.py:261-278` always writes a receipt, and `supervisor.py:48-60` SIGKILLs the helper's group if the
  supervisor itself dies.
- **Memory pressure never stops a recording**, and the partial is preserved (`App.swift:381-387`,
  `ResourceGuard.swift:15-18`). One gap: `ResourceGuard.stopsOnPressure` exempts
  `openrouter-finalize`/`openrouter-import`, which is the only job these users will ever run.
- **The database is not in a synced folder** (`cli.py:9`); WAL and `busy_timeout=5000` are set correctly
  (`store.py:42-43`), and the resumable upload checkpoints in `transcribe_sources` are genuinely atomic.
- **No partial analysis is ever saved** (`intelligence.py:630`, `assistant.py:68`), and a truncated model
  response surfaces as an error rather than being silently accepted (`openrouter.py:345-347`).
