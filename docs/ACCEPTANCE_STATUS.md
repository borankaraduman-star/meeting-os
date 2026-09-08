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
