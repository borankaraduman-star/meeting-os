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
