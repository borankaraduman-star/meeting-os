# Local reliability iteration — 2026-09-08

## Active work plan

Follow docs/superpowers/plans/2026-09-08-meeting-os-acceptance.md as the current ordered plan. Codex implements/tests; Claude independently reviews and authors adversarial fixtures. A1 completed:90 tests pass and12 independent fictional cases frozen in benchmarks/analysis-heldout-v1. A2 CPU candidate failed resource gate; execute model-free C recovery/diagnostics, then B echo, D long/device/installer and E natural meetings. Historical sections below are evidence, not instructions to redo completed work.

User authorized continued local testing and improvement with Claude Code. Codex implements; Claude reviews compact code-only checkpoints using the existing Max session. No paid API, private audio/transcripts, outbound messages, or OS permission bypass.

## Safety baseline

The 16 GiB M4 desktop crashed during full Whisper testing (see CRASH_RECOVERY_1.0.3.md). Never repeat that workload. MLX memory limits are advisory. Use OS pressure and owned-process physical footprint, preserve captured audio, keep model tests sequential and bounded. Unit tests with fakes are preferred for fault injection. Do not run memory-pressure stress utilities or terminate unrelated apps.

## C2b retry storage checkpoint

Internal RetryStore implemented: exclusive process-owned attempt, separate bounded stage rows, same-meeting atomic commit, idempotent finish, old-token rejection, conservative protection for corrected/analyzed/task-linked/final segments, baseline snapshot recheck. Original rows survive staging, abort, SQL insertion failure and abrupt fake child exit during commit; a subsequent attempt retains one meeting. No CLI/UI/model wiring yet. Claude reviewed; no confirmed atomicity blockers. Segment-rename audit concern disproved against full method and protected by a regression. Empty outputs intentionally refused. Final full suite129 Python tests passed, including two-connection race and abrupt owned process exits; no model or user DB used. Next C2c: guarded orchestration with audio availability/source revalidation, attempt-local assembly, full completion count and cancellation; do not call old finalize or promote storage-only tests to end-to-end recovery acceptance. See docs/RECOVERY.md.

## C2a finalized capture availability

Added opt-in `recovery --audio` to inspect finalized capture headers for interrupted/incomplete/provisional/failed captures. Skips active/unknown processing owners; imports explicitly unsupported. Counts separate mic/system chunks, deduplicates entries, flags missing/corrupt/truncated/conflicting data, rejects external paths/symlink leaves/FIFOs, bounds journal lines/bytes/chunks and rejects oversized chunk files before native parsing. Read-only, no waveform/model load or user data accessed in tests. Claude reviewed; reproduced and fixed truncated WAV payload misclassification with RIFF extent checks, plus per-chunk TypeError handling. Final full suite:116 Python tests passed. See docs/RECOVERY.md for limitations and C2b retry transaction contract. Next implement that contract on the existing meeting with conservative refusal when corrections/tasks/analysis would be invalidated; do not use existing finalize as an idempotent retry.

## C1 process identity and conservative recovery

Implemented native PID + microsecond start time + boot UUID for live/import/finalize ownership. New recovery CLI lists processing rows without mutations; explicit mark rechecks under SQLite transaction and changes only confirmed interrupted rows to incomplete. PID-only/corrupt/denied inspection remains unknown. Supervisor cleanup uses the same classifier rather than PID-only SQL. No process signals, model loading, user DB edits, audio changes or retry flow. Claude reviewed the small checkpoint; no confirmed blockers. Its zombie/reaping concern was checked against supervisor wait-before-callback order and a dedicated regression test; native EPERM path also tested. Full suite104 passed before these two additional focused passing regressions. SDK layout compiled to136/120/128. See docs/RECOVERY.md. Next C2: finalized-audio availability and idempotent retry contract, then allowlisted diagnostics and GUI integration; do not claim recovery UX complete.

## A2.1 runtime qualification

Pinned llama.cpp b10853 and Qwen3-4B-Instruct-2507 GGUF Q4_K_S downloaded and SHA-verified. Experimental adapter/fake tests added, never wired to defaults. Native tokenizer worked; single fictional cancel fixture generation was aborted on OS memory pressure after7.196s. Normal pressure restored; no output/semantic score or held-out evaluation. Candidate fails current resource gate; do not repeat unchanged. Peak footprint was not persisted. See docs/candidates/ANALYSIS_CPU_QUALIFICATION.md. 96 Python tests passed after the change. Claude compact review completed; native error-detail leakage fixed with a regression test. CLI concerns rejected against pinned help; tokenizer/completion parity remains unverified. Next prioritize model-free recovery/diagnostics and echo; another model family only with a justified lower-resource hypothesis, keeping the two-family cap.

## Open-lid microphone retest

User opened lid and switched output from Bluetooth to built-in MacBook Air speakers. Read-only device inspection confirmed built-in input/output and open lid. Fresh13s actual capture: microphone RMS0.01748, system RMS0.11246, both separate channels. Guarded CPU pipeline transcribed microphone audio in7.11s, correctly recovering the played Turkish opening (product meeting, payment error, conversion drop). No audio settings changed in this final retest. Built-in microphone path now validated on this short controlled sample; natural live conversation, echo handling and long recordings still need testing. Local evidence: concept-test/builtin-retest-* under MeetingOS cache. No audio/transcripts published.

## Latest shipped checkpoint: 1.0.5

Read [RELIABILITY_1.0.5](RELIABILITY_1.0.5.md) first. CPU default integrated import15.45s passed;40s live capture passed; second capture finalize19.52s passed and persistent synthetic identity matched0.971–0.986. Independent process-group supervisor and parent-death guardians implemented for inference and recording;87 Python and9 Swift tests passed. Closed lid is the actual reason the default built-in microphone is unavailable; native UI now warns. Automatic analysis deferred on16GiB. Small1.7B model failed semantic and staged quote-validation tests; NOT selected.4B prefill/KV memory experiment also failed and was reverted. Prioritize a lower-overhead quality-preserving analysis runtime/model, diagnostics, recovery UX, and then natural meeting benchmarks. Do not repeat completed baseline work or failed identical model tests.

## Earlier checkpoint

- Recommended installation downloads turbo, diarization and local analysis models; optional full Whisper is no longer downloaded automatically.
- Xet CAS is disabled by default before Hugging Face import, and HTTP download timeout defaults to 120 seconds. Explicit environment overrides are respected. This addresses the observed CAS transport path, not every possible network failure.
- A capture helper ignoring SIGINT can no longer leave the live queue waiting forever for EOF. Stop has a 15-second grace period; timeout terminates the owned helper, marks the meeting incomplete and retains finalized audio/journal.
- Regression reproduced with a small subprocess, then fixed. 75 Python tests pass; the additional explicit-environment/offline test also passes (76 total). 9 Swift tests and the native release build pass. No model inference or real microphone capture was needed for this checkpoint.

## New empirical acceptance result

Read [CONCEPT_TEST_2026-09-08](CONCEPT_TEST_2026-09-08.md) before further inference. Actual default turbo import hit OS pressure at 6.13 s; actual Qwen analysis hit it at 8.66 s. Both guarded aborts returned the OS to normal. Do not retry unchanged. Direct quantized CPU turbo with GPU disabled succeeded on captured system audio in 11.73 s at 1.14 GiB, 0/58 normalized word errors on a single synthetic voice. This is not an integrated fallback yet. Microphone file was completely silent. Prioritize integrating low-memory staged inference, microphone silence feedback and deferred analysis after the independent supervisor. Full concept acceptance failed; no natural-meeting or speaker-identity claim is justified.

## Next bounded checkpoints (in priority order)

1. Independent inference supervisor: inspect native main-thread guard and direct CLI; bound unresponsive model jobs without blocking UI, test with fake child processes, and ensure cleanup marks interrupted meetings recoverable. Do not claim Python polling interrupts a native inference call.
2. Interrupted-job recovery: distinguish active work from stale processing rows after desktop/process restart without marking another live job interrupted. Add a visible recovery route where appropriate.
3. Diagnostics export: local-only, allowlisted resource/version/stage/error information; exclude transcripts, names, audio, credentials, signed download URLs and raw OS reports. Test privacy exclusions.
4. Installer resilience: verify cached reruns and partial downloads with mocks; classify failures clearly. Do not repeat multi-GB downloads just to exercise installation.
5. Recording usability and accessibility: clear cancel/recover states, keyboard navigation and readable progress. Build and visually test if UI-control tools exist; explicitly record when visual testing is unavailable.
6. Short public Turkish audio smoke test only after supervisor is verified and OS pressure is normal; cap duration and physical footprint, no full Whisper on this Mac. Never present synthetic/concatenated fixtures as natural meetings.

## Exit criteria

Pause when this bounded backlog is complete or further acceptance requires unavailable hardware permissions or 3–5 consented natural meeting fixtures. Report remaining limits honestly. Do not invent endless features, keep retesting unchanged code, claim “perfect”, or claim a second Mac was tested. Publish only reviewed, tested source/bootstrap releases with checksums. Do not overwrite a running recording or unrelated user changes.
