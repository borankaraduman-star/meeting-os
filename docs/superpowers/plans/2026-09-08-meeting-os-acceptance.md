# Meeting OS Acceptance Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans task-by-task. User already authorized implementation without routine confirmation. Codex implements; Claude Code reviews architecture and adversarial QA through the existing Max session. Do not delegate duplicate implementation.

**Goal:** Make the measured recording/transcription baseline a reliable meeting application, with accurate resource-bounded local analysis and honest natural-meeting acceptance.

**Architecture:** Keep raw mic/system audio durable and separate. Use isolated, supervised inference; admit new defaults only after resource and semantic gates. Recovery/diagnostics and echo handling must preserve source evidence and explicit uncertainty.

**Tech Stack:** Apple Silicon macOS, ScreenCaptureKit/SwiftUI, Python3.12, SQLite, whisper.cpp CPU, Sherpa/Resemblyzer, local text models. No paid API.

**Spec:** docs/RELIABILITY_1.0.5.md and docs/ITERATION_CHECKPOINT.md plus Boran's five remaining iteration priorities.

## Global constraints

- This shared Mac has16 GiB; stop on non-normal OS pressure or3.5 GiB owned inference group footprint. Polling is mitigation, not a hard allocator guarantee.
- No full Whisper stress test, identical retry of failed4B MLX or promotion of failed1.7B analysis.
- No private transcripts/audio sent to Claude, remote services, or public releases. No outbound messages/actions.
- Short tests precede long tests; no simultaneous model runs. Do not shut down unrelated apps to manufacture a pass.
- A passed synthetic test is not a natural-meeting or multi-speaker quality claim.
- Use existing heartbeat/checkpoint, not duplicate background workers. One bounded reviewable task per cycle.

## Ownership and review checkpoints

Codex owns implementation, local experiments, evidence artifacts, integration, tests and release. Claude owns independent plan criticism, adversarial cases/acceptance review and compact diff review. Give Claude only relevant code, declared synthetic fixtures and summarized measurements; no full history or repeated whole repo. Reject findings contradicted by actual callsites and document the reason.

### A1: Freeze meaningful analysis checks (start now)

Files: meeting_os/evaluation.py; scripts/benchmark-analysis.py; tests/test_evaluation.py; tests/fixtures/analysis/*.json.
Interface: `check_fixture_analysis(result, case) -> dict[str,bool]`, automated *proxies*, not human semantic adjudication.
- [x] Add failing tests showing correct counts/owner sets can hide swapped ownership, dates and wrong tasks.
- [x] Attach expected title terms, owner and exact due text to existing fictional cases. Keep expectations out of model prompts.
- [x] Add one-to-one task checks and make benchmark output explicitly require separate semantic review.
- [x] Run focused evaluator tests; Claude reviewed gate design. Existing cases are development fixtures, not held-out data.
- [x] Before tuning any candidate, create a separately versioned held-out set and freeze its hash. Do not tune to it; report failed cases without moving the goalposts.

Acceptance: false task/owner/date pairings fail automatic checks; source/evidence validators remain mandatory. All held-out decisions, risks and summary time/negation facts require independent review. No unsupported owner/date/accepted task allowed in the small acceptance set; report precision/recall and sample counts on larger sets, not blanket100% claims.

### A2: Resource-efficient analysis runtime

Files: meeting_os/llm.py, meeting_os/models.py, docs/MODEL_LOCK.json, scripts/benchmark-analysis.py; new backend adapter/tests only if measured necessary.
Consumes A1 gates; produces same `LocalLLM.complete(system,user,max_tokens,schema)` contract and provenance/model revision.
- [x] Profile runtime overhead without loaded weights; select at most two justified candidates, first a CPU runtime retaining the proven4B model family.
- [ ] Pin model/runtime revision, license, download checksum/source; revisions and checksums verified, model license recorded; runtime license confirmation remains before redistribution.
- [x] Test one short case under supervisor; aborted candidate on pressure after7.196s. No automatic retry of the same failed workload. Runtime license confirmation remains required before redistribution.
- [ ] Run development cases, then frozen held-out cases; Claude independently examines synthetic outputs.
- [ ] Only integrate a candidate passing resource, evidence and semantic gates. Leave manual/deferred analysis when none passes.
- [ ] Test app-visible cancellation, errors and preserved transcript before release.

Initial target: no pressure warning, peak group footprint below3.5 GiB, short fixture analysis under120 s. Targets are release gates to be measured, not current performance claims.

### B: Echo and overlapping speech

Execution split: Codex implements bounded measurements and regression tests; Claude reviews complete small code checkpoints and proposes adversarial controls. B1: read-only per-window correlation. B2: timestamp-aware windows, drift and speech-shaped controls. B3: hardware speaker/headphone evidence and conservative UI markers. No cancellation until near-end preservation is demonstrated. See docs/ECHO_MEASUREMENT.md.

Files: meeting_os/audio.py, meeting_os/pipeline.py, meeting_os/types.py; new bounded echo analysis module and synthetic alignment tests.
- [ ] Create delayed/attenuated system-to-mic fixtures plus genuine near-end and simultaneous speech controls.
- [ ] Measure clock offset/drift and duplicate content before choosing a cancellation approach.
- [ ] Preserve both raw channels; mark probable duplicates and uncertainty before any automatic suppression.
- [ ] Do not suppress near-end-only speech or double-talk. Require review on ambiguous alignment.
- [ ] Re-run hardware loop at ordinary volume, plus headphone/control case when available.

Gate: fixture truth shows no lost near-end speech; duplicate reduction and residual errors reported separately. Natural double-talk remains unverified until real data exists.

### C: Recovery and private local diagnostics

Files: meeting_os/store.py, meeting_os/live.py, meeting_os/supervisor.py, meeting_os/desktop.py and SwiftUI recovery flow; new diagnostics module/tests.
- [x] Reproduce crash leftovers with fake processes and temporary DBs.
- [x] Distinguish stale processing jobs using PID, microsecond kernel start timestamp and boot UUID; native identity exercised on this Mac, unknown states preserved. Read-only recovery CLI plus transactional mark, no signals.
- [x] Expose finalized audio availability and same-meeting guarded retry without task/profile writes; manual native recovery/cancel wired. Corrected/analyzed/final records conservatively refused. Visual QA and legacy auto-finalize consolidation remain pending.
- [x] Export only allowlisted versions, stage/resource counters and sanitized error codes. Diagnostics CLI implements current snapshot with private no-overwrite export; no DB/raw logs/audio/transcripts/names/credentials/paths/URLs. Independent Claude review and privacy tests passed. GUI integration pending.
- [ ] Claude reviews the allowlist and fault-injection results; test restart during finalization/analysis and interrupted download.

### D: Long recording, devices and installer

Files: scripts/stress-capture.py, scripts/verify-capture.py, scripts/install-mac.sh, scripts/setup.sh and associated tests/docs.
- [ ] Progress5→15→30→60 minutes only if prior duration passes and offers new evidence. Models stay bounded; capture-only and inference resource costs reported separately.
- [ ] Measure chunk timeline gaps/overlap, late chunks, queue growth, RAM trend and finalize duration.
- [ ] Exercise device disconnect/switch, stop, low disk, sleep/restart using fakes first; hardware interactions only when actually available.
- [ ] Test clean install and cached rerun in isolated locations; public ZIP remains source/bootstrap, not a notarized standalone app.
- [ ] Separate evidence from this M4 and other M2 Mac; never mark the other machine tested remotely.

### E: Natural-meeting acceptance

Files: benchmarks private manifests, scripts benchmark harness, docs final acceptance report.
- [ ] Use3–5 consented natural meetings, not synthetic concatenations. Public recordings may supplement but not simulate a real mic/system meeting.
- [ ] Label Turkish words, names/jargon, speaker turns and cross-meeting identity with human ground truth.
- [ ] Report WER/entity recall, speaker error, false identity acceptance/abstention, overlap errors, task precision/recall/ownership/date accuracy, runtime and peak footprint.
- [ ] Review UI clarity, recovery and source playback alongside model accuracy.

Do not invent numeric quality success before corpus size/annotation agreement exists. If real fixtures or device access are unavailable, continue independent A–D work and state that E is pending. Stop repeating tests or adding unrelated features when remaining work requires external input.

## Delivery rhythm

Each checkpoint: reproduce → implement → relevant tests → compact Claude review → resolve findings → record measurements → commit. Package/publish only useful reviewed releases. Keep progress updates focused on findings. No routine permission requests; user already authorized this scope.

## Claude review decisions and clarified gates

- Held-out set:12 explicitly fictional cases,2 each for cancellation/transfer, conditional vs commitment, owner/date pairing, decisions/risks, unanswered questions/unknown owner, and untrusted quoted instructions. Claude drafts; Codex validates labels against source before hashing. These cases never go into tuning prompts; each candidate gets one frozen evaluation. This is a small release gate, not a population accuracy estimate.
- No fabricated quote, unsupported named owner/date or false accepted task in the12-case set. Independently adjudicated task precision must be1.0 and recall at least0.9; owner/date correctness on matched tasks1.0. No unsupported summary or decision claims; failures are shown individually. Thresholds fixed before candidate outputs. Report denominators and adjudicator disagreement.
- Resource ceiling already fixed above:3.5GiB, OS normal pressure, sequential models, short case120s. Do not raise ceilings after a candidate fails.
- Echo: accept Claude's raw-channel checksum and separate-error metrics suggestions. Reject suppressing all uncertain double-talk: preserve near-end content with an uncertainty label instead of silently deleting it.
- Recovery kill points: before model load, mid-inference, between temp-result write and atomic rename, after audio chunk fsync but before DB update. Never edit actual user DB for fault injection.
- Diagnostic allowlist: app/runtime version, OS major/minor, architecture, stage enum, elapsed seconds, peak bytes, pressure enum, counts, sanitized error-code enum. No free-form exception text, paths, PIDs, usernames, content, tokens or URLs.
- Hardware matrix: current M4/16GiB/macOS26.5; other M2/16GiB only when accessible. Support floor remains macOS15. Clean installer acceptance means no project venv/models and separately verified missing Homebrew/developer-tool paths; mocks on this configured Mac do not prove a clean non-developer account installation.
- Full Python suite before integration; Swift suite/build also when native UI changes. Do not repeatedly rerun unchanged suites during candidate profiling.

## A1 evidence

90 Python tests passed. New regression checks failed before implementation and pass afterward. A nonexistent benchmark case exits before loading a model. Benchmark execution now uses the process supervisor. Frozen cases: benchmarks/analysis-heldout-v1/cases.json and manifest.json. Claude authored12 cases, Codex reviewed and documented three pre-freeze clarifications; no model candidate has been evaluated on this set yet. A1 complete; A2 is next.

A2 primary runtime reference: https://github.com/ggml-org/llama.cpp/blob/master/grammars/README.md . JSON-schema support is a subset; verify the application's schema constraints against a pinned runtime rather than assuming equivalent enforcement. Model artifact/revision selection is still pending.

## Resource-gate scheduling update

A2.2 CPU4B candidate failed pressure admission during generation. Keep analysis manual/deferred and stop this candidate here; do not interpret the remaining quality boxes as permission to retry. Codex next implements C's process-identity/recovery and allowlisted diagnostics with temporary databases/fake processes, then B's raw-preserving echo measurements. Claude reviews those compact changes and adversarial fixtures independently. D follows passing recovery/echo gates; E remains dependent on real consented data and human labels. This reorders independent work to keep progressing without further model pressure on the shared Mac.

### C1 concrete next checkpoint and Claude handoff

Observed callsites: `run_transcribe` stores only worker_pid; `live.record_live` stores capture_dir/provisional without an owner identity; interrupted CLI cleanup matches PID alone. `Store` has no startup recovery classifier. Address these together, without touching the real user database in tests.

Codex implementation sequence:
1. Add a process-identity helper using PID plus kernel process start timestamp (including subsecond precision), and boot identity where available. Unknown/unreadable identity must return unknown, never dead. Add fake-provider tests for alive, dead, reused PID and denied inspection.
2. Persist identity at job creation for live/import/finalize; use matching identity for cleanup. Preserve compatibility with historical PID-only rows: classify conservatively as requiring review, not automatically stale.
3. Add a read-only recovery listing that distinguishes active, interrupted and unknown rows and reports finalized capture availability locally. Apply state transitions transactionally only after rechecking identity; never signal processes from recovery. Idempotent retry must retain original meeting and corrections, with an explicit policy for replacing provisional segments before enabling UI retry.
4. Add diagnostics with a fixed schema of versions, numeric stage/resource counters and enumerated error codes. Build from structured records, never scrub arbitrary logs and call them safe. No paths, titles, names, text, audio, tokens or URLs. Write local JSON with private permissions; no network.
5. Claude receives the narrow diff and synthetic fault cases, reviews PID reuse/races, duplicate writes and privacy, and reports specific blockers. Codex resolves findings and runs relevant tests before checkpoint/release.

C1 acceptance: reused PID cannot make an unrelated process a recovery target; inspection failure preserves unknown state; repeated recovery does not duplicate profiles/tasks; adversarial secrets in arbitrary metadata never appear in diagnostic output. GUI recovery integration is a subsequent checkpoint after the storage contract passes.

## B2 / D harness checkpoint

B2 implemented: bounded timestamp-aware alignment, conservative lag-trend fit, impulse abstention, speech-shaped controls and read-only file harness. Claude reviewed core and harness separately; malformed-input and fractional-timing regressions fixed. Natural/hardware echo detection remains inconclusive; no suppression or UI duplicate marker is enabled. See docs/ECHO_MEASUREMENT.md.

D harness implemented: guarded staged capture runner and metadata-only interval coverage/gap/overlap/order metrics; fake subprocess success/failure and privacy/preservation tests. Actual hardware state/evidence and open acceptance are tracked in docs/CAPTURE_SOAK.md and docs/ACCEPTANCE_STATUS.md; do not treat a successful subprocess exit as a complete product acceptance pass.
