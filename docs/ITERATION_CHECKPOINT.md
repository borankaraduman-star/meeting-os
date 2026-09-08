# Local reliability iteration — 2026-09-08

User authorized continued local testing and improvement with Claude Code. Codex implements; Claude reviews compact code-only checkpoints using the existing Max session. No paid API, private audio/transcripts, outbound messages, or OS permission bypass.

## Safety baseline

The 16 GiB M4 desktop crashed during full Whisper testing (see CRASH_RECOVERY_1.0.3.md). Never repeat that workload. MLX memory limits are advisory. Use OS pressure and owned-process physical footprint, preserve captured audio, keep model tests sequential and bounded. Unit tests with fakes are preferred for fault injection. Do not run memory-pressure stress utilities or terminate unrelated apps.

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
