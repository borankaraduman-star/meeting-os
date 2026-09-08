# Live worker model residency fix — 2026-09-09

## Cause and change

The low-memory retry path had deferred Resemblyzer and isolated Silero, but the live record path still created an eager VoiceEncoder/Torch model in make_pipeline and retained it throughout CPP decoding. A fresh reproduction on the same private12s microphone chunk measured266,945,472bytes parent footprint at ASR entry, with Torch imported; the old run failed during decoding under shared OS pressure.

Supported low-memory Mac record+CPP+Sherpa+Resemblyzer now uses the same deferred embedding proxy as retry. A live chunk is normalized with unchanged read_audio and saved as a private FLOAT16k snapshot. Existing VAD, Sherpa, CPP and identity workers run sequentially; no parent Torch. Snapshot lifetime covers all workers and is cleaned after success/failure. Live source offsets, provisional flags, short-context speaker namespaces, identity thresholds and model IDs remain. No profile auto-enrollment, model change or guard relaxation. Only live chunks are bounded to60s before decoding; ordinary import/transcribe and existing retry behavior remain unchanged. Optional batch input extraction now supports the file reader.

## Verification

Failing regression first reproduced eager factory and parent VAD use. Tests now verify deferred construction, exact ASR clip samples after48k stereo resampling (including peaks), same segment/word/speaker/identity output, ASR-before-identity ordering, original-file preservation, cleanup on failure and oversized-chunk rejection.40 relevant tests initially passed; a later29-test run passed after7 ambient-pressure failures in hashing tests were rerun at normal pressure. Latest24 affected tests passed after strengthening sample equality and preserving bounded_final/provisional rejection.

Native after: first ASR-entry parent84,935,328bytes, no Torch;182,010,144bytes (68.2%) below baseline parent residency. Same12s input completed in22.49s,3segments/3turns, guarded sampled full process group peak1,290,750,592bytes. This is a residency reduction, not a claim that total peak dropped: baseline failed and never reached a comparable successful peak. Decoder remains slower than real time on this sample (RTF about1.87). No human reference, no accuracy percentage.

Five-minute live replay then failed with ResourceProbeError after14.59s; only the silent system chunk completed. The precise failed process probe was not preserved, so do not label it a confirmed memory-pressure failure or relax the guard. Sequential batch preflight then failed MemoryPressureError after3.15s. Neither produced a completed meeting, and30minute tests were not started. No caches were used in these independent test stores. Existing270real segments and101ASR checkpoints remain. Tests used existing audio only; no capture or unrelated service changes.

Actual Claude Code Fable5.1/max review completed, session47221, exit0, stream result success. Sanitized diff/tests only; no private content. Reviewer found no unconditional blocker and did not run tests. Dispositions below. Full evidence: benchmarks/results/live-phase-isolation-2026-09-09.json; private outputs stay under build/live-isolation-native and build/mode-comparison-after.

## Bounded remaining-cause investigation

Models available locally: CPP turboq5_0 (~547MiB) and unquantized MLX turbo (1,613,977,612weight bytes); MLX large has config but no local safetensors payload. No smaller audio model in inspected Hugging Face cache. Analysis language models are not STT alternatives. One concrete lower-memory candidate is multilingual whisper-small-q5_1,181MiB per upstream model card (https://huggingface.co/ggerganov/whisper.cpp). It requires a new download; none performed, no Turkish/English quality or speed claim.

A models-free bounded child-lifecycle test completed1.07s with~21MB sampled peak. Four rusage failures were errno3/ESRCH with processes already absent and correctly ignored by existing lifecycle logic. A12s replay with numeric probe diagnostics did not reproduce fatal ResourceProbeError; it failed on actual OS pressure after17.10s. One already-exited errno3 child was again handled. Therefore the earlier fatal resource-read failure remains unexplained; do not weaken fail-closed behavior or invent a proven timeout cause.

Shared-system reinspection found Docker VM running again asPID79340,2,009,189,688bytes footprint; lsof confirms Docker.raw/linuxkit kernel. Actor/restart cause unknown, no services changed in this work. OS pressure2 persists. Batch trial sampled324MB for its monitored group, far below3.5GiB ceiling; global pressure, not the per-job cap, stopped it. Exact failed batch model phase was not recorded, so attribution to Whisper weights specifically is unproven. This distinction prevents claiming that merely replacing Whisper will resolve every current failure.

## Fable review dispositions

-60s cap: it rejects strictly greater than60, not60 itself. Default capture chunks12s; oversized preview fails without truncating or deleting durable capture. Added pre-read rejection test. We did not clamp away audio.
-Path acceptance: verified by the actual successful12s VAD/Sherpa/CPP/identity native run, not merely mocks.
-Source path: Segment objects retain source channel and times, not private PCM pathname. Recording provenance stays in existing capture metadata; original-path caller is unchanged.
-Batch reader: added native-array sample equality and mono/dtype assertions in the optional batch path; same fake model outputs/offsets/speaker flags preserved. Regions are validated against frames by isolated VAD. Existing bounded_final rejects non-mono and provisional calls.
-Double normalization assertion: file VAD maps FLOAT16k, file diarization and identity read FLOAT16k; no additional sample-rate conversion. Regression compares exact ASR sample arrays from resampled48k stereo including peaks. Native full-output equality versus baseline remains unavailable because baseline resource-failed.
-Finalization scope: factory change targets record/retry; standalone import/transcribe/finalize are not included by this condition. No claim they automatically gained this live-only residency fix.

Latest affected suite25tests passed after batch coverage. No further model job runs. Remaining fatal measurement error not safely reproduced; no speculative relaxation. Lower-memory candidate needs a new181MiB download and held-out Turkish/English comparison; no download or changed default.
