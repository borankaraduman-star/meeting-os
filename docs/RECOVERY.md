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
