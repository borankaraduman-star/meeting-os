# Live optimization loop — 2026-09-08

User explicitly requested continued observation/optimization with Claude Code while leaving the meeting video running. Existing 20-minute thread heartbeat updated, not duplicated. An active goal tracks this work. This is engineering feedback, not model self-training or automatic speaker enrollment.

## Current implementation and evidence

- Native user recorder PID46784/capture helper46786 left untouched; no restart/signing/build/route change or concurrent model run. Current recording directory ends743E719D-C735-46CF-8E5D-BEBBDC2BF89B. Always re-check ownership before future actions.
- Added context-local phase timings in fresh live workers. Latest numeric file per source is bounded, replaced atomically, includes source offset, wall time, failure flag and CPU thread setting. No text/audio/embeddings in telemetry. Observer/write failures do not interrupt inference. Hooks execute in memory independently of UI progress-file writes.
- Read-only scripts/observe-live.py prints latest source RMS/peak/exact silence, capture/transcript coverage and worker timing. Coverage difference is NOT exact lag: silence/no-speech can legitimately produce no transcript. Command: .venv/bin/python scripts/observe-live.py. Uses read-only SQLite and bounded latest finalized WAV/journal reads, no inference.
- Baseline sample: 12s microphone chunk total14.05s, transcribing11.54s, model loading1.43s, diarizing.27s. Later totals21.83s and32.90s; transcription dominates. Silent system worker measured.034–.063s (process-internal, excludes outer interpreter startup).
- Claude Sonnet reviewed compact code-only architecture using Max OAuth. Flagged per-VAD-region whisper-cli model/process reload; suggested splicing regions. Do NOT directly adopt splice suggestion: cpp returns no word alignment, seam/timestamp remapping and altered language context require independent validation. CLI --help confirms multi-input support; investigate per-input outputs/context reset as a safer potential reuse method. Source inference is a hypothesis, not measured spawn-overhead attribution.
- Four-thread CPU experiment added with strict recording-directory match,2/4-only choice,<=15min expiry; absent/invalid config means2. Only live worker applies it; no model/GPU/decoder change. Experiment config build/live-tuning.json (ignored) explicitly removed after first samples. New workers return to2; an already running4-thread worker may finish naturally. Never promote without a matched-audio benchmark.
- Four-thread live totals18.94s,25.94s,25.63s on DIFFERENT consecutive chunks. These do not establish an A/B speedup; still slower than incoming12s chunks. No promotion. Memory pressure remained1; one full readable recording process-tree physical footprint snapshot1276.8MiB. Earlier measurement failed because an owned child exited; retried and reported complete snapshot, not zero for missing process.
- Last observed system source still digital silence; mic has signal. Local default output reported built-in MacBook Air speakers, input built-in mic. Actual video playback device/source not established; do not infer a capture fault or change routing from this alone.

## Validation

35 targeted tests passed: live*16 (including observation/timing/tuning), silent_live7, low_memory5, progress3, pipeline4. Regression tests cover source-scoped expiry/fallback, no private content in snapshot, telemetry write/observer failures, normal2-thread CPU-only default and4-thread command preserving model/GPU settings. Initial4-thread command test failed only on /var vs /private/var normalized path expectation, fixed to model.resolve() and reran green. No real duplicate inference or memory stress tests during capture.

## Next bounded work

1. Retain numeric timing snapshots, inspect actual ASR call count/CLI load timing before blaming repeated loads. Current latest files overwrite; cache observations.jsonl holds sampled values but is not a complete per-chunk history.
2. Add/validate same-model multi-file reuse offline with fake CLI tests then a sequential matched-audio benchmark when user capture/inference is idle. Preserve absolute timestamps, VAD gaps and fresh decode context. No splicing deployment based solely on review.
3. Live throughput remains below real time. Design bounded preview backlog with explicit UI indication of deferred provisional text while all raw audio/final transcription is retained. Do not silently skip speech or retroactively inject fake transcript text. A UI/recorder change requires safe post-record restart.
4. Source signal/lag visibility in UI, then matched quality/reference tests (names/code switching, speaker continuity). UI build only when idle, using pinned signing scripts; no ad-hoc signing or new TCC reset.
5. Do not claim natural-meeting WER/DER or perfection without verified reference annotations. Never learn speaker identities from unconfirmed ASR guesses.

Local review and numeric snapshots: ~/Library/Caches/MeetingOS/live-optimization. Background numeric sampler is bounded to180s, no inference; session63906. Preserve quiet heartbeat: report meaningful changes, errors or required user action only.
