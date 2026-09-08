# Private local diagnostic snapshot

From the repository virtual environment:

```sh
.venv/bin/python -m meeting_os diagnostics
.venv/bin/python -m meeting_os diagnostics --output ./meeting-os-diagnostics.json
```

An optional `--progress /absolute/path/to/progress.json` reads the explicitly selected local progress file. No progress file, error log or meeting database is opened by default. The app's progress path varies per job; GUI integration will supply it in a later checkpoint.

The report includes only a fixed schema: application/Python/macOS numeric versions, arm64/x86_64 architecture, physical RAM rounded toGiB, current OS memory pressure, this diagnostic process's footprint inMiB, free disk rounded toGiB, enumerated progress stage/source/freshness with bounded integer counters, and enumerated probe failure codes. Recent means the supplied progress file was modified within60seconds; this is not proof its owner is alive. Absolute timestamps are excluded. The disk sample refers to the output directory's volume (repository volume when printing only).

The report never copies raw logs, exception strings, process command lines, filesystem paths, host/user names, audio, transcripts, speaker embeddings/profiles, meeting IDs/titles, credentials, environment variables, signed URLs or arbitrary metadata. Unknown/malformed fields are discarded. Booleans, negative values and non-finite numbers cannot masquerade as integer counters. The export function applies the allowlist again even when called with arbitrary caller input.

Progress input is limited to16KiB and regular non-symlink files opened without blocking on FIFOs. Malformed/unavailable input produces unknown progress. Export writes and fsyncs a private0600 temporary file, then atomically links it to a new destination without replacing existing files or symlinks. No request is sent anywhere; the CLI prints the snapshot or writes the user-selected local file. Destination parents must already exist. Filesystems that cannot create hard links may reject export safely; printing remains available.

This is a current diagnostic-collector snapshot, not a job history, crash report, active model's peak footprint or a claim of root-cause diagnosis. Detailed structured job outcomes and GUI export remain future work; no raw-log fallback is allowed. Tests use fake secrets, malformed values, symlink/FIFO inputs, existing destinations, probe failures and an isolated CLI export without creating/opening the meeting database.

Claude reviewed the compact implementation and found no accidental private-data path in the allowlist/export flow. Follow-up verification confirmed `footprint(os.getpid())` uses proc_pid_rusage for that PID only, physical RAM uses static hw.memsize, and the CLI's outer exception handler emits a short error/exit1 for existing destinations. A dedicated existing-file CLI regression confirms no traceback or overwrite. Full suite144 tests passed before that final extra regression; all9 diagnostics tests passed afterward. No user data, model inference or UI behavior was involved.
