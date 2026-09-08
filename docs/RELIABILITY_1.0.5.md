# Meeting OS 1.0.5 — measured local fixes

## What changed

- Auto engine resolves to CPU-only quantized whisper.cpp turbo with two threads on Macs with at most16 GiB. Explicit engines remain available; auto plus an explicit model is rejected to prevent mismatches. Installer uses the same RAM policy and builds the pinned native binary; adds CMake if missing.
- Import/transcribe/finalize/analyze/prepare/ask run under a lightweight separate supervisor. It checks OS pressure and its owned process group footprint, enforces timeouts and kills/reaps its workers on cancellation. Native cpp calls also have pressure/footprint checks. Private output uses temporary files or the existing caller log; no remote inference.
- Live capture keeps models out of its recording process. Each chunk uses an isolated worker. Stop cancels current inference and skips queued provisional work while preserving captured audio for finalization.
- A pipe-based guardian stops the owned process group if its supervisor is killed. Applies to live capture too. Normal cleanup reaps the guardian. Failed import/finalize workers leave their processing meeting marked incomplete, identified by worker PID. Analysis failure does not invalidate a completed transcript.
- Closed-lid warning is visible in the native app. Actual local hardware state was closed lid, built-in default microphone. Apple documents hardware microphone cutoff: https://support.apple.com/en-euro/guide/security/secbbd20b00b/web
- Automatic analysis is deferred on16 GiB; manual analysis remains guarded. A smaller analysis model was tested and rejected on semantic quality. No claim that summaries are fixed.

## Measured acceptance checks

All content below is the same locally generated synthetic Turkish product meeting, not natural multi-speaker audio. Temporary databases only; no real profiles changed.

| Check | Result |
| --- | --- |
| App's integrated import, CPU ASR + Sherpa + Resemblyzer | Passed,15.45 s for40.41 s captured system audio; named entities and commitments preserved |
| Actual40 s live recording with playback | Exit0, live text emitted during recording, queued work drained; live fragment boundaries can cut phrases |
|9.2 s synthetic Turkish/English switching fixture | Passed in7.96 s; İpek/Çağrı and funnel/conversion/rollout/feature flag preserved; normalized text matches reference; short-context speaker uncertainty retained |
| Separate second capture finalized through CLI | Passed,19.52 s;3 final segments |
| Persistent voice profile across those captures | Enrolled clean synthetic segment as Test Yelda in test DB; second recording matched all3 segments, cosine0.971–0.986 |
| Microphone loop test at temporary low output volume | Still digital silence; lid closed and built-in mic selected, consistent with documented hardware cutoff; restored original volume31 and mute=true |
| Small Qwen3-1.7B4bit analysis | Process completed but failed quality: two tasks not correctly separated, incorrect time/category claims. Not selected or shipped as default |
| Smaller-model staged extraction experiment | Failed source quote validation; not shipped |
| Existing4B model with smaller prefill/8bit KV experiment | Still hit OS pressure; experimental parameters reverted |
| Automated verification | 87 Python tests passed;9 Swift tests passed; native release build passed |
| Fault injection | Timeout, cancellation, descendant cleanup, parent SIGKILL protection, capture ignoring SIGINT, and isolated live segment serialization tested without heavyweight models |

The profile test repeats one synthetic voice/utterance across separate actual captures; it does not prove identity accuracy for new speakers, noisy rooms, code switching or natural meetings. GUI rendering was not visually checked because UI-control tools are unavailable. The helper and native release compile, and the underlying lid state was independently read with ioreg.

## Claude review

Compact code-only Sonnet checkpoints through the existing Max account. Parent-death orphan risk was a valid finding and fixed with the independent pipe guardian and a regression test. Two initial findings did not apply to actual callsites: the CLI errors go to stderr, not duplicate JSON stdout; analysis never changes completed meeting status to processing. ChildFailure passthrough nevertheless now preserves the original last error. Follow-up warned about reaping guardians: code already waits per job/chunk, with timeout/kill/wait fallback. No private meeting contents sent.

## Remaining work

Healthy capture/transcription now passes this fixture. Full acceptance still needs resource-efficient *and* semantically accurate local analysis, open-lid/external microphone validation,3–5 natural meetings, multiple speakers, code switching and long sessions. Do not repeat failed4B workloads unchanged or make the inaccurate1.7B model the default. Next analysis candidate should retain quality with a lower-overhead CPU runtime or measured smaller model; benchmark against the existing adversarial analysis fixtures before changing defaults. No paid API fallback.
