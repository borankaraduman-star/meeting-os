# Source signal visibility — 2026-09-08

## Production backend

Added bounded read-only finalized WAV inspection: all-channel RMS/peak, exact digital silence, measurement age, unknown on missing/malformed/non-finite/oversized/changing/outside-root file. No speech classification or amplitude threshold. Source paths and meeting content are not returned. Capture snapshot keeps existing numeric source coverage; adds signals only for a currently owned provisional capture without retry_attempt. Does not scan completed history or retries. New desktop bridge invocations use this code without restarting the app.

Actual stdio snapshot of user meeting553993e7544a completed in .122s and returned display_status capturing, mic signal, system digital_silence, fresh ~11s measurements. Separate probe .097s including import. Source unit tests and snapshot gating tests confirm anti-phase stereo is not silence, extreme/non-finite input remains unknown and only live owner triggers probes.

## Claude-authored presentation (source integrated, installed UI unchanged)

Claude Code Sonnet wrote CaptureSignalPresentation.swift and18 XCTest cases in an isolated cache directory using Write-only tools/Max OAuth. No private meeting data provided. Codex integrated into desktop App activity and bounded footer activity text to4lines, with help explaining this Mac's system audio versus other-device sound reaching mic. Label separates signal/silence/unknown/stale; waiting text no longer assumes an OS permission problem. Current installed app has NOT been rebuilt/re-signed/restarted, so it does not yet show this new formatter.

Codex added real JSONSerialization0/1 regression test. It exposed NSNumber numeric0/1 passing Swift `is Bool`; fixed using CFBoolean type identity. Claude's infinity fixture expected24hours while finite-validation implementation returned0; corrected fixture to reject infinity consistently with invalid-duration policy.19 standalone Swift formatter tests now pass in a small isolated package; NOT a full native app build/layout verification. Source/test copies in repo match successful isolated test inputs. Full app build and geometry/visual checks remain for safe idle installation through pinned signing scripts.

16 Python tests passed (source_signal3,capture_state5,desktop8),19 isolated Swift tests passed; git whitespace check passed.

## Live memory incident and integrity limits

While attempting the first isolated formatter test, OS pressure changed to2 and the guard terminated that test. No Swift .build directory yet existed; timing alone does not establish the cause. No unrelated processes terminated. Owned native recorder46786 and parent46784 stayed alive and raw journal kept advancing. Process footprint snapshot showed VM~2314MiB, Java~1115MiB, Chrome renderer~905MiB, cpp~782MiB, live Python~468MiB among larger consumers; do not attribute a single cause from this snapshot.

Existing live-loop behavior catches pressure admission failures and advances the queue. Found124 unique failed current-recording chunks in bounded last-job.log tail, all pressure-related; all124 referenced raw files still exist. This proves file presence, not full decoded integrity/finished transcript. A shorter live backlog after this incident is NOT a speed improvement: provisional text is incomplete. Full final processing/recovery must be verified after recording ends. This incident exposes a remaining need for explicit deferred-preview coverage and backpressure UX.

After pressure returned normal, four read-only samples over30s all showed level1. The small standalone formatter package then ran under guard;19 tests passed after corrections. Current pressure normal at final check. No native app rebuild or duplicate inference performed.

## Source route evidence

Read macOS SDK CoreAudio process-property definitions locally, queried process objects using AudioObjectGetPropertyData. Four snapshots over30s:28 process objects,0 active output streams,1 active input stream,0 query errors. This supports system-silent/mic-signal being consistent with no playback on this Mac at those moments; it does not identify which external device plays the meeting, prove no local playback at other times, or test capture against known local audio. No audio route/permission changes made. Numeric survey in ~/Library/Caches/MeetingOS/source-signal-ui/audio-io-survey.jsonl.

Next: preserve active user recording; finish explicit deferred-preview/error coverage and verified finalization. Install/visually verify new source labels only at safe idle, with stable signing. Batch comparison still default-off and unrun on real clips. Do not claim real-time accuracy or product completion.

## Full stopped-capture decode audit

Capture 743E719D-C735-46CF-8E5D-BEBBDC2BF89B, same-meeting recovery 553993e7544a. Every sample of all 526 WAVs was decoded in 65,536-frame blocks; no model was loaded. Numeric report: `benchmarks/results/real-capture-signal-audit-2026-09-08.json`.

Mic: 263 nonzero chunks, summed duration 3153.675s, RMS .013868, peak .388879; no clipped (abs >= .999) or nonfinite samples. System: all 263 chunks exactly zero, summed duration 3153.7s. No file size/mtime changed during inspection. This verifies source sample content and decodability, not timeline alignment or recognition accuracy. Combined with earlier no-local-output observations, external playback entering microphone is consistent; the audit cannot identify the physical playback device. The app must not imply successful system-sound content capture for this recording.
