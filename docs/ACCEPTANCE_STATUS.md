# Active optimization acceptance — 2026-09-09

This section supersedes the older CPU-recovery snapshot below for the current live-optimization objective. Historical sections are retained as dated evidence, not proof that later work passed acceptance.

| Requirement | Current verified evidence | Remaining acceptance |
|---|---|---|
| Real meeting completion | 3153.7s mic VAD completed; regenerated snapshot reused1diarization and69ASR checkpoints. Original270 provisional segments preserved after guarded failure. | Complete remaining ASR and final identity/transaction; latest full trial stopped on first new ASR region under OS pressure. |
| Live latency | Experimental bounded same-speaker grouping has short synthetic evidence; first real chunk had no eligible grouping. | Sustained real live backlog/latency improvement is unproven; grouping remains off by default. |
| Mic/system visibility | Real archived mic nonzero, all263 system chunks digitally zero. Separate18s local playback test captured both channels. | Long live source visibility, device transitions and full recording stability. Short playback is not proof of audio in the archived silent channel. |
| Memory and recording safety | Mapped final VAD, bounded silence gate, isolated final identity, bounded identity batches; exact public fixture comparisons and relevant tests. Raw recording and successful checkpoints retained. | Current shared OS pressure prevents standalone decoder admission before model launch. Do not relax guards or terminate unrelated active apps/services. |
| Claude collaboration | Actual Fable5.1/max bounded reviews completed, including mapped-VAD review39042 exit0; findings checked against source and dispositions recorded. | No review substitutes for real full-record or human accuracy acceptance. |

Latest blocker revalidation: OS pressure2; process listing showed no MeetingCapture, meeting_os recording/finalization/retry/live worker, whisper-cli or Claude print job. Working tree clean before this documentation update. Repeated pressure across the resumed attempt, standalone admission attempt and current continuation prevents further native acceptance without external headroom. No model is left running or waiting. See real-mapped-vad-retry-2026-09-09.json and idle-pressure-admission-2026-09-09.json under benchmarks/results.

Cross-meeting identity and Turkish names/jargon/code-switch accuracy still need independent human-labeled meeting references. No perfect-product or full-goal completion claim.

---

# Current acceptance status —2026-09-08

This is the current overview; older checkpoint paragraphs document historical states. Implemented code and controlled tests are not natural-meeting acceptance.

| Area | Evidence now | Open acceptance |
|---|---|---|
| CPU transcription/recovery | Actual9.4s fictional TR/EN CPU retry, same meeting, raw preserved,8.24s wall/~1.44GiB sampled peak; normalized WER0/22 and6/6 entities | Natural speech, overlapping people, long inputs, other M2 Mac |
| Recovery and diagnostics | Transaction/fault-injection tests, private diagnostic export, native UI wiring and prior build | Native visual interaction and restart/device scenarios on an available session |
| Echo | Bounded per-window and timestamp-aware measurements, drift trend and uncertainty, synthetic adversarial tests, read-only file harness | Old real speaker/mic sample was inconclusive0/2 windows; no cancellation or transcript deduplication enabled |
| Capture soak | Bounded5/15/30/60 minute harness and metadata coverage/gap/overlap counters; fake subprocess success/failure | Asleep-display attempt failed; temporary wake allowed validated five-minute capture (52 intact chunks, ~20MiB sampled peak).15-minute silent-system continuity also validated (152 intact chunks);30-minute stage validated (302 intact chunks, playback captured);60-minute attempt failed around30minutes;300 finalized headers valid,2 partial files retained; no60-minute pass |
| Speaker identity | Existing local profiles and controlled synthetic identity checks | Human-labeled multi-person, cross-meeting identity, false acceptance and abstention on3–5 consented meetings |
| Summary/to-do | Existing analysis/evaluation framework and frozen fictional held-out cases | Resource-qualified model with semantic acceptance; current4B CPU candidate failed pressure gate. Deferred/manual on16GiB |
| Distribution | Previously verified anonymous1.0.5 source/bootstrap ZIP | Current checkpoint is local source, not newly published/notarized; clean nondeveloper install not established |

## Work split and next steps

Codex implements and executes tests; Claude reviews complete compact code checkpoints and adversarial logic using the existing subscription. No paid API or private recording content is sent for review. Only numeric/code/synthetic material is shared.

ScreenCaptureKit needed the sleeping displays temporarily awakened. The5-minute gate then passed. The15-minute continuity gate also passed with a silent system stream. The30-minute stage also passed with deliberate playback evidence. The60-minute attempt failed around30minutes. No active capture remains. Current OS pressure2 blocked subsequent Swift compiler admission; the original runner did not record a precise failure reason, so do not attribute the failure to a proven cause. Preserve sources and improve diagnosis before an unchanged retry. Distinguish capture-only costs from inference; retain current pressure/footprint limits. Speaker/headphone echo controls and native UI checks also need hardware access.

The final natural-meeting gate requires3–5 consented recordings with human reference words, entities, speaker turns and repeated speaker labels. Public or synthetic clips cannot prove live microphone double-talk or persistent natural speaker identity. Until these gates pass, this is an implemented and tested local system with open product acceptance, not a completed perfect-product claim.

## Parallel fixes pending full integration

A separate agent implemented error-triggered bounded capture shutdown in Python; Claude independently reviewed this and the installer fix. Whisper bootstrap now fetches a missing pinned commit even in an existing valid repo, keeps cached installs offline, and refuses invalid git metadata without deleting files. Seven lightweight targeted fake tests passed; no real download/build/device change was run. The full suite and native build remain pending normal memory pressure; these are local source changes, not an updated installed/public app.

Read-only native audit found that throwing `stream.stopCapture()` bypasses writer finalization, and one throwing writer can skip the other. This remains unfixed: compiler admission failed before compilation, test draft retained outside the repo. UI visual acceptance is still pending. There is no evidence tying this native control-flow defect to the failed soak; a hard supervisor kill can leave partial files independently.

## Current local UI refresh

After OS pressure returned normal,201 Python tests and14 desktop Swift tests passed and a guarded single-job release build completed. Current UI installed, signature verified and reopened on this Mac, using functional source commit c5761e4 and current repo/venv. Prior bundle retained locally; runtime build-info.json records provenance. No new public ZIP or update on the other laptop. Native capture cleanup defect remains open; launch verification is not visual acceptance. User is preparing a short live microphone test from another laptop's speaker; background work must avoid conflicting recording/device/app actions.
