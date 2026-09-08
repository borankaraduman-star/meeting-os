# Interrupted-job classification (development checkpoint)

Recording/import/finalize jobs now persist the owning Python process PID, kernel start timestamp in microseconds, and macOS boot-session UUID. Recovery compares the full identity; a reused PID is not the original job. Inspection failures and historical PID-only metadata remain unknown. No process is signaled by recovery.

From the installed repository, with its virtual environment:

```sh
.venv/bin/python -m meeting_os recovery
.venv/bin/python -m meeting_os recovery --mark-interrupted MEETING_ID
```

The first command only lists processing rows with active/interrupted/unknown classifications. It does not load models, capture audio, modify statuses or export diagnostics. The second rechecks identity under a SQLite write transaction and changes only a confirmed interrupted processing row to incomplete. It returns false for active/unknown/already transitioned rows. The normal meetings command shows incomplete rows afterward.

Neither command finalizes audio, retries analysis, duplicates a meeting, enrolls profiles or changes corrected text/tasks. Idempotent finalization into the existing meeting, finalized-audio availability checks, GUI recovery and privacy-filtered diagnostics are separate pending checkpoints. Do not use repeated finalize commands as a substitute for that forthcoming retry flow: existing finalize creates a new meeting.

The supervisor failure callback now uses this same conservative transition rather than updating every row with a matching PID. Live capture records its Python owner, whose parent-death guardian already controls the native capture child. Startup classification does not prove every audio chunk was saved; only finalized durable files are candidates for later recovery.

Verification uses temporary databases and a short owned sleeping subprocess. No user database or recording is used. Native identity layout was checked against the installed macOS SDK sys/proc_info.h and exercised on the current M4 Mac. Other platforms return unknown; no unsupported platform claim is made.

The SDK layout probe compiled and returned size136/start-sec offset120/start-usec offset128. Current/terminated-child identity tests passed; the full Python suite passed104 tests. Classification is a snapshot of owner-process liveness, not proof of forward progress. Automatic startup reconciliation and retry are not enabled in this checkpoint.

Claude independently reviewed identity, SQLite serialization and CLI integration. Its possible zombie-owner concern is resolved for the supervisor path: `run_guarded` calls `process.wait()` before `on_failure`, now covered by a regression that confirms the PID no longer exists at callback time. General owner-process liveness remains conservative if a separate parent retains a zombie; no progress detector is claimed. Added a mocked native EPERM regression rather than assuming the injected PermissionError test exercises libproc.

## Finalized capture availability

```sh
.venv/bin/python -m meeting_os recovery --audio
```

This opt-in inspection includes incomplete/provisional/failed captures in addition to processing rows. Active or unknown processing owners are not scanned. It prefers the native finalized-chunk journal, falling back to the Python journal only when the native journal is absent. It reports available/missing/invalid counts, per-source counts, enumerated issues and `validation: header_only`; it emits no filenames, transcript or audio. Imported-file availability is explicitly unsupported in this checkpoint.

Inspection opens regular files read-only through the capture directory descriptor with no-follow/nonblocking flags. Chunk paths must name WAV files directly inside the capture directory; symlink leaves, FIFOs, missing and invalid files are rejected. It reads at most8MiB of journal data, accepts lines up to16KiB (one extra byte detects overflow), and examines at most10000 distinct chunk names; chunks above64MiB are rejected before the native audio header parser. Truncated/malformed journal entries are reported, never silently considered complete. Duplicate journal entries count once; conflicting source/timestamp entries flag uncertainty. Standard RIFF/WAVE declared container and chunk extents must fit in the file; at most1024 container chunk headers are examined with small positional reads. RF64 and other containers are conservatively unsupported. Neither waveform decoding nor checksum/content/quality validation occurs. Header availability is a preliminary recovery candidate check, not proof of complete audio.

Tests use synthetic PCM, sparse oversized files, symlinks, a FIFO and temporary SQLite stores. Captured audio, user databases, models and microphone permissions are untouched. Native parser and filesystem latency are not a hard wall-time guarantee; this is a bounded local inspection, not a memory stress test.

## Next retry transaction contract (not implemented)

Retry must acquire an exclusive attempt identity on the existing meeting, recheck owner status and audio availability, and stage inference output separately. It must never call the current finalize path, which creates another meeting. Original raw files and current segments stay intact until an atomic successful result commit. A crashed attempt can be retried with the same meeting/attempt state; no task, correction or profile enrollment writes occur as side effects.

Until stable segment reconciliation exists, meetings with text/speaker corrections, analysis or linked tasks must refuse automatic segment replacement and keep those records intact. For eligible unedited provisional records only, atomically replace segments on successful inference, clear the attempt lease and mark complete. Failure retains the original rows and marks the attempt interrupted; identity checks prevent concurrent attempts. Test kill points before inference, mid-stage, before commit and after commit, with repeated retries proving one meeting and no duplicated records. GUI retry follows this storage contract; it is not enabled yet.

Claude review accepted a concrete truncated-payload issue: a WAV with a valid header and ten missing payload bytes initially counted as available. The failing regression now passes after RIFF extent validation. Native parser TypeError is classified per chunk instead of aborting the scan. Inspection is confined to the supplied capture directory descriptor, not a hard-coded global recordings folder: the record CLI supports user-selected directories, and metadata establishes that root. It is not a sandbox for an attacker who can rewrite the local meeting database. No filesystem paths or raw errors are exported. Unknown reports may contain partial counters after interrupted inspection; consumers must honor status/issues and never infer completeness from counts alone. Journal byte limits also bound malformed events that do not enter the distinct-chunk set.

Final C2a verification:116 Python tests passed after the RIFF bounds fix; git diff whitespace check passed. No native UI or model behavior changed, and no public release was created for this intermediate recovery checkpoint.
