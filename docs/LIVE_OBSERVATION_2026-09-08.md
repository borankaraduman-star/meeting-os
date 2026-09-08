# Live recording observation — 2026-09-08

User started a meeting-video test. Inspected only finalized chunks, read-only SQLite metadata/metrics, native journal and owned-process usage; did not stop/relaunch/sign the application, change routing or start competing inference. Claude Code Sonnet reviewed a compact code/numeric checkpoint with Max OAuth; no private transcript/audio was sent.

## Findings and changes

- Native journal advanced through ~432 seconds without errors. OS pressure remained level 1 (normal). Initial owned recording/inference tree measured ~1.32 GiB physical footprint.
- Sampled system chunks were exact digital zeros, while corresponding microphone chunks contained signal (latest measured mic RMS .0141, peak .1256). This does not establish where the video was played/routed or prove a system-capture defect. Both channel files existing is insufficient evidence of audible content.
- Live transcript lag grew from ~30–40 seconds to ~150 seconds. This is a remaining live-throughput problem; do not claim real-time acceptance or that the following optimization fixes all lag.
- Each silent live chunk previously loaded the full models before VAD. Added a bounded all-channel exact-zero WAV probe before importing the pipeline or constructing Store. No thresholds/downmixing; tiny nonzero, anti-phase, NaN/Inf, invalid, oversized or changing inputs use the normal path. Raw recordings remain untouched. Fresh synthetic 12-second stereo silence worker completed in .137 seconds with unchanged raw hash; no comparison against a competing heavy baseline during recording.
- Claude flagged duration parity; an added differential test failed on 44.1 kHz before correction. Probe duration now matches the normal 16 kHz resample output length. No timeline offset changes.
- Display adapter now labels active provisional processing captures as capturing only with live native evidence. Retries with retry_attempt remain processing even with stale capture journals. Persisted status and job ownership are unchanged.
- Python production files replaced atomically; future per-chunk workers and desktop snapshots use the changes without restarting the active recorder. Read-only current snapshot returns capturing.

## Verification and remaining work

28 targeted tests passed across silent_live (7), live/live_worker (10), capture_state (3), desktop (8). Silence tests explicitly reject Store/model construction, check normal-path delegation, all channels/block tails, malformed/empty/oversized files, tiny DOUBLE values, non-finite values and resampled duration parity. Git diff whitespace check passed. No additional inference/pressure stress test run.

Remaining: live speech inference throughput/backlog needs a separately measured solution without reducing final accuracy or increasing unsafe memory pressure. Source-level signal/lag feedback should be visible in UI; no native rebuild while the user records. No WER/DER claim without reference transcript/speaker annotations. Preserve user recording and existing signing identity.
