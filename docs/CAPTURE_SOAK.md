# Staged capture-only acceptance

Run from the repo with the display/session available and macOS microphone/system-audio permissions granted:

```sh
.venv/bin/python scripts/capture-soak.py --minutes 5 --output "$HOME/Library/Caches/MeetingOS/soak-new-run"
```

The output directory must not exist. Durations5,15,30,60 minutes are supported. Advance only after reviewing the previous stage; this command does not launch a duration ladder automatically. No model, transcription, volume/device changes, assembly or raw-file cleanup is performed. Existing owned-process pressure/footprint supervision and lifeline are used, with a duration+30s timeout. Unexpected pressure or failure stops only the owned capture group. Finalized audio and logs stay local.

`report.json` includes success resource sampling and metadata timeline metrics when capture exits successfully. Capture exit0 is explicitly `captured_pending_acceptance`, not a test pass. Missing source chunks, duration shortfall, waveform validity, silence/dropouts and actual listening still need review. Timeline metrics distinguish interval union, internal gaps, duplicate overlap time and out-of-order timestamps. Out-of-order counts are not queue depth or wall-clock delivery delay; leading/trailing coverage is exposed by first/last timestamps. Metadata can be wrong: these counters do not validate WAV headers or samples.

Errors retain logs and produce a short allowlisted error code, without copying free-form error text into the summary. Interrupted creation of the report itself may leave raw data without a report; no success is promised in that case.

## Current evidence

On2026-09-08, a five-minute hardware attempt exited immediately with native `No display available`. Capture did not start; no duration gate passed. Evidence is in the local `capture-soak-5m-20260908-b2` cache. The initial runner propagated an exception after saving failed status; the final runner now returns a structured failure. Its subprocess-based fake success/failure tests verify metrics, missing-source visibility, private error exclusion from the report, preservation of logs, and refusal to overwrite a previous run. The same unavailable hardware was not retried.

Long recording, source switching, sleep/wake and visual acceptance remain pending. Prior accelerated reconstruction and native self-tests are separate evidence and cannot substitute for this hardware gate. The other M2 Mac remains untested.

Claude separately reviewed the harness and interval sweep; no interval-metric defects found. Cancellation deliberately tears down the owned group, writes a failed report, then the CLI exits1. Returning a report does not keep capture running; a dedicated user-cancel code remains a possible UX refinement. The raw worker log is local and may contain paths/OS error text; it is not a share-safe diagnostic export.

## Awake-session five-minute result

Read-only OS inspection showed the lid open and all displays asleep. A temporary `caffeinate` user-activity/display assertion restored capture; no persistent power setting or permission changed. The second actual run completed300.698s under supervision. Sampled peak caller+capture footprint20,989,056bytes (~20.02MiB),2194 samples; this excludes inference and unrelated desktop memory.

Both sources produced26 finalized chunks (52 total). Full bounded-block decoding and header checks passed for every file; no missing/corrupt/partial WAVs. Mic coverage300.24967s, system300.32s; no out-of-order chunks or overlaps, mic internal gap~1.18e-11s is floating-point roundoff. Initial source offsets0.252s/0.144s are exposed. Mic RMS0.00561, system RMS0.02531; the system carried one existing fictional9.4s TR/EN clip and otherwise silence. This demonstrates five-minute capture continuity with that workload, not long-form STT, device switching or natural-meeting quality. Numeric evidence: docs/CAPTURE_5M_2026-09-08.json.

The15-minute stage was then started under the same guard and a930s temporary display assertion. Its result is pending in the local `capture-soak-15m-awake-20260908-b2` cache. Do not launch a duplicate; inspect owner.json identity and report.json completion first. The active heartbeat resumes validation and only then considers30minutes. Do not publish a duration pass while the stage is running.

## Fifteen-minute capture continuity result

The15-minute owned process completed with native stopped event and no error events. PID/start/boot inspection confirms its original owner is gone. Runtime901.117s; sampled caller+capture peak21,005,440bytes (~20.03MiB),6362 samples. Both channels have76 finalized chunks (152 total); every WAV header and all frames were validated in bounded65536-frame blocks with finite values and unchanged source metadata. No missing/invalid/partial files. Mic coverage900.256s, system900.32s; internal gaps, overlap and out-of-order counts all zero. Numeric evidence: docs/CAPTURE_15M_2026-09-08.json.

Mic RMS0.006898, system RMS0.0. No deliberate system playback was scheduled during this stage. The all-zero system channel demonstrates continuous silent PCM writing, not audible system capture or an independently verified absence of system sound. Do not claim speech accuracy, desktop-wide memory, RAM trend or device resilience from this run.

A30-minute guarded capture was started next with temporary display assertion1830s, plus one9.4s local fictional TR/EN playback after the native started event. Its capture completion is pending in `capture-soak-30m-awake-20260908-d2`. Inspect owner.json/report.json before any new run; validate system nonzero samples as well as full-file/timeline integrity on completion. Do not begin60minutes until30minutes passes. No model or persistent power setting changed.

Claude independently reviewed the15-minute numeric evidence and scoped claims. Added explicit sample rates (48kHz both sources; mic mono/system stereo) and verified the original supervisor and native process IDs absent, including no zombie under those IDs. The resource enforcement path was not stress-tested by this low-memory run; existing fault-injection tests are separate evidence. No code changed this checkpoint, so the unchanged189-test suite was not repeated.

For the active30-minute run, afplay exited0 and the first three finalized system chunks contain844,196 nonzero samples, peak0.840743. This is interim evidence that playback entered the system stream, not a30-minute pass or proof of acoustic microphone quality.

## Thirty-minute capture continuity result

Completed1800.910s under the guard; sampled caller+capture peak20,972,648bytes (~20.00MiB),12646 samples. Both channels produced151 finalized WAVs (302 total),48kHz mic mono/system stereo. All headers and every frame decoded in bounded65536-frame blocks: finite, exact declared frames/durations, unchanged source metadata, no missing/invalid/partial files. Native stopped with no error events; original supervisor/native process IDs absent and original owner identity no longer active. Coverage1800.01067s mic/1800.06s system, zero internal gaps/overlap/out-of-order. Numeric evidence: docs/CAPTURE_30M_2026-09-08.json.

System contains844,196 nonzero samples, matching the interim check after one local9.4s fictional playback; RMS0.010339. Mic RMS0.002069 is not speech-intelligibility evidence. Claude reviewed numeric-only results and considered60minutes a reasonable next stage. No production code changed; unchanged189-test suite not repeated. Reviewer wording about a memory trend is not adopted: only sampled peak/count and elapsed time were retained, not a RAM trajectory. This remains sparse-playback capture integrity, not sustained conversation, ASR, device switching or whole-desktop memory acceptance.

The60-minute stage is active in `capture-soak-60m-awake-20260908-d3`, with owner.json pinning supervisor identity. Startup checked ~12.95GiB free disk (>4GiB admission for expected raw audio plus reserve), no other capture/inference found, native started event verified. Temporary display assertion3630s; one local fictional playback, no model or permanent power setting change. Do not duplicate while active. Validate final output and nonzero system evidence before marking the60-minute stage complete; do not extend to a new duration ladder afterward.

## Failed sixty-minute attempt

The attempt produced a failed report at2026-09-08T17:19:16Z with only `supervision_or_validation_failed`; no sampled failure metrics or precise termination cause were retained. Last finalized chunks end around1800s. Header-only inspection found300 available chunks (150/source), no missing/invalid journaled chunks, and2 unvalidated partial WAVs retained. No full decode of this failed attempt was repeated. docs/CAPTURE_60M_INTERRUPTED_2026-09-08.json records the limited evidence. No60-minute pass.

Later OS reads returned pressure2; a guarded Swift test build was refused before starting the compiler. This does not by itself prove the earlier capture failure's cause. Do not replay the60-minute test unchanged under pressure or infer that the native stop-cleanup defect caused this failure. Failure-reason telemetry and normal-pressure admission should precede a further long run. Existing5/15/30-minute evidence remains scoped to those runs only.

## Failure reasons for future runs

The runner now emits fixed codes: memory_pressure (OS non-normal pressure), resource_probe_failed (unreadable resource state), memory_limit (owned-process budget), timeout, canceled, capture_failed, supervision_failed, or validation_failed. Typed exceptions retain RuntimeError compatibility; no raw exception text enters the JSON report. Existing owned-process cleanup logic is unchanged. Failures still do not carry historical peak metrics, and unrelated/cleanup exceptions can remain generic; the old60-minute failure cannot be retroactively diagnosed.

Six fake-only tests verified admission, typed in-loop failures with kill/wait, private-text exclusion, report mapping and malformed-journal distinction. A separate admission-only check read real OS pressure2, returned memory_pressure and verified zero capture Popen calls with an isolated tripwire. No native process/model/compiler ran. Claude reviewed the complete relevant code with no concrete regression found. Full integration suite remains pending normal pressure.
