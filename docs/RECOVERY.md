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

## Retry transaction contract (storage implemented; orchestration pending)

Retry must acquire an exclusive attempt identity on the existing meeting, recheck owner status and audio availability, and stage inference output separately. It must never call the current finalize path, which creates another meeting. Original raw files and current segments stay intact until an atomic successful result commit. A crashed attempt can be retried with the same meeting/attempt state; no task, correction or profile enrollment writes occur as side effects.

Until stable segment reconciliation exists, meetings with text/speaker corrections, analysis or linked tasks must refuse automatic segment replacement and keep those records intact. For eligible unedited provisional records only, atomically replace segments on successful inference, clear the attempt lease and mark complete. Failure retains the original rows and marks the attempt interrupted; identity checks prevent concurrent attempts. Test kill points before inference, mid-stage, before commit and after commit, with repeated retries proving one meeting and no duplicated records. GUI retry follows this storage contract; it is not enabled yet.

Claude review accepted a concrete truncated-payload issue: a WAV with a valid header and ten missing payload bytes initially counted as available. The failing regression now passes after RIFF extent validation. Native parser TypeError is classified per chunk instead of aborting the scan. Inspection is confined to the supplied capture directory descriptor, not a hard-coded global recordings folder: the record CLI supports user-selected directories, and metadata establishes that root. It is not a sandbox for an attacker who can rewrite the local meeting database. No filesystem paths or raw errors are exported. Unknown reports may contain partial counters after interrupted inspection; consumers must honor status/issues and never infer completeness from counts alone. Journal byte limits also bound malformed events that do not enter the distinct-chunk set.

Final C2a verification:116 Python tests passed after the RIFF bounds fix; git diff whitespace check passed. No native UI or model behavior changed, and no public release was created for this intermediate recovery checkpoint.

## C2b internal retry storage

`RetryStore` now implements begin/stage/finish/abort on the existing meeting. One running attempt per meeting is enforced by a partial unique index and SQLite write transactions. Begin requires a known live owner and refuses active/unknown previous owners; a confirmed dead attempt can be replaced. Old tokens cannot stage or commit after replacement. The original rows remain readable during staging; finish checks a snapshot of metadata/title/all segment columns and rechecks protected corrections, text edits, analyses/tasks and final segments before replacing anything.

Stage sequence numbers are unique; identical repeats are no-ops and conflicting repeats fail. Finish requires the caller's explicit completed segment count and a contiguous sequence; it refuses empty or incomplete staging. All replacement inserts, meeting completion and attempt completion occur in one transaction. Repeating successful finish is a no-op. Abort preserves original segments. No task/profile enrollment or audio writes occur. Staging is limited to10000 segments,1MiB per serialized segment and32MiB total payload per attempt; failed/dead/successful attempt payloads are cleared when finalized/replaced/aborted.

Tests cover linked analysis/final row refusal, edits and metadata/source changes during retry, simultaneous/unknown owners, duplicate/gapped staging, aborted attempts, SQL insertion failure after deletion, and abrupt owned child-process exit after staging and mid-commit. Reopening the temporary database retains original rows; a new attempt completes the same single meeting. These are transactional fault tests, not real-model or GUI acceptance.

This class is not exposed to the production CLI/UI. The next checkpoint must inspect audio immediately before claiming/processing, keep assembly output in a separate attempt directory, supervise one inference process, and call finish only after the entire capture completes. Source-file identity/checksum revalidation is still required around that orchestration; a database snapshot alone does not detect changed audio. Existing `finalize` is unchanged and must not be used as the retry implementation. No retry button is enabled until the orchestration and cancellation tests pass.

Claude independently reviewed retry ownership/idempotency/transactions and found no atomicity gaps. Its claimed missing audit for `Store.correct_segment` was contradicted by the full method: it already inserts into corrections. The small review excerpt had ended before that line; future compact reviews must include complete methods. A new preexisting segment-rename test confirms begin refuses replacement and preserves the name. No unnecessary change was made to correction logic. Empty-result commit remains deliberately unsupported: the future orchestrator must retain prior content and report no confirmed speech, not erase it based on an empty inference result.

Final C2b verification:129 Python tests passed; diff whitespace check passed. Internal storage only, no native UI or production inference changes and no release publication.

## C2c guarded CLI retry

```sh
.venv/bin/python -m meeting_os retry MEETING_ID
```

The CLI now runs retry through the same independent process/pressure/footprint supervisor as transcription. It claims the existing meeting, requires available finalized capture headers, copies journal-declared audio into a private attempt directory, assembles only those copies, processes sources sequentially, stages every result, and commits only after complete generator exhaustion and source revalidation. Model options match transcription and default to the existing CPU engine on this16GiB Mac. No automatic model download or analysis is introduced.

Source reads use no-follow regular-file descriptors,64KiB streaming SHA256, before/after inode/size/mtime/ctime checks and a pinned directory descriptor. Before committing, retry rechecks the root identity, journal selection/content, original chunk identity/content and processed-copy hashes. A source digest is retained in meeting metadata. This is a check immediately before the database commit, not an atomic filesystem+SQLite transaction or protection against a hostile writer that rewrites and restores files between checks. Results correspond to the processed private snapshot.

Limits:2GiB total copied source,64MiB per chunk, at least1GiB free disk reserved before each copy, and a four-hour maximum source timeline before assembly. Existing supervisor limits still apply during whole-source assembly/processing. CLI cancellation/timeout terminates the owned worker; original rows remain recoverable. Normal failures remove temporary copies and abort staging. Abrupt SIGKILL can leave a private temporary directory named with its attempt token; automatic orphan-file cleanup is not yet implemented. Admission checks prevent starting another copy when free space is insufficient.

Incomplete/unknown header reports, edited/analyzed/final rows, empty results or changed sources are refused rather than partially replacing prior content. Imported audio retry is not supported here. Full long-recording/resource, model-quality and GUI recovery acceptance remain pending. Tests use tiny fictional PCM files, a fake pipeline through actual CLI assembly, and an externally supervised sleeping worker; no real model or user recording is loaded.

Claude C2c review disposition: retained the final path-to-pinned-directory comparison. Replacing `root.stat()` with `fstat(root_fd)` as suggested would merely compare the held directory to itself and fail to detect replacement of the original path. A directory-replacement regression confirms the existing check rejects that case; all file reads remain descriptor-relative. Cooperative cancel callbacks run during copy/stage/verification; real CLI native processing is interrupted by the external supervisor, not by a claim of streaming per-segment cancellation. The added actual guarded sleeping-worker timeout test confirms old rows survive and a later retry reclaims the same meeting. RetryStore atomicity/ownership had already been independently reviewed in C2b and remains covered by its fault/race tests. A4-hour pre-assembly timeline check and2GiB copy cap were added during this iteration; they are admission ceilings, not evidence of acceptable four-hour performance. Orphan temporary files after SIGKILL and GUI recovery remain explicit follow-ups.

## Native recovery/cancel controls

Manual recovery now launches guarded `retry` with the selected meeting ID, retaining that ID throughout the job. A successful retry does not automatically start an analysis model. The recovery action is visible for captured incomplete/provisional/failed meetings and confirmed interrupted processing owners; active/unknown owners and complete/canceled records cannot trigger it. Snapshot polling classifies owner identity read-only. Backend eligibility/correction/source checks still run at launch, so a stale UI snapshot cannot authorize an unsafe replacement.

A separate cancel control interrupts guarded retry jobs through their external supervisor; other legacy inference jobs do not expose this new control until their result/recovery semantics are consolidated. Native capture uses its existing stop/drain flow and cannot be interrupted a second time through this button. Cancellation requests are remembered so an expected nonzero exit is not presented as an unexpected model error. Source/transaction safety is enforced by the already tested CLI path.

This changes manual recovery only. The preexisting normal-recording automatic finalize flow still creates a separate final record; consolidating that flow is an explicit remaining integration task. No native visual/click automation is available in this session, so successful compilation and state-policy tests are not a claim of visual/accessibility QA.

Claude C4 review disposition: restricted cancellation to retry after review highlighted that legacy finalize retains partial final rows rather than the retry transaction semantics. Published job/cancel properties now explicitly drive UI updates. The diagnostics destination-folder concern was rejected against `collect(disk_root, progress_path)`: it measures free space there and scans no folders. Added bridge assertions for that argument, missing-progress handling and the actual worker_identity metadata key. Save-panel deletion races yield unknown progress; they do not read alternate logs or meeting data.

Final C4 verification:148 Python tests,11 Swift tests and production build passed; local preview bundle at build/recovery-preview/Meeting OS.app signed and verified. The currently running app was not replaced or restarted. Preview uses this Mac’s existing runtime/repo; it is not a portable installer.
