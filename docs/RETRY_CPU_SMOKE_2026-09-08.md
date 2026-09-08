# C7 real CPU retry smoke — 2026-09-08

On this M4/16GiB Mac, one actual CPU retry of the existing9.405625s synthetic Turkish/English fixture completed in8.236s wall time. No other model job was active; OS pressure was normal before and after the run. The external supervisor used120s admission/timeout and3.5GiB footprint limits; it sampled67 times and observed a peak1,545,030,608bytes (~1.44GiB) for its caller plus owned worker process group. This is sampled observation, not a hard peak upper bound.

The worker invoked the actual CLI `main(supervised=True)` under the isolated external guard, with `--db` pointing to a separate test SQLite file, `retry` of its single provisional meeting, and explicit CPU engine. Default local whisper.cpp turbo, Sherpa and Resemblyzer stages ran; no hosted API, model download, summary model or real user meeting was used. This verifies source snapshot/assembly, actual CPU inference and same-meeting commit together; it is not a live microphone/UI test.

Results:
- Exactly one meeting remained, with its original ID and complete status; three final transcript segments were written.
- Original WAV and capture journal hashes were unchanged; no assembled full WAV appeared in the raw directory.
- Processed temporary workspace was removed; source digest was saved in metadata; zero speaker profiles were enrolled.
- Normalized word errors0/22 and declared name/jargon entities6/6. Raw case-sensitive WER1/21 (capitalized “Ödeme” vs reference “ödeme”).
- Output preserved confidence_unavailable and short_context_diarization flags on all three segments; no invented confidence or identity certainty.

Reference text: “İpek, ödeme adımını konuşalım. Let's check the funnel because conversion dropped after the rollout. Çağrı yarın feature flag durumunu kontrol edecek.” The6 declared entities are İpek, funnel, conversion, rollout, Çağrı, feature flag. Reference comes from the existing fictional TTS fixture, not human annotation of a natural meeting. This does not establish speaker diarization accuracy, cross-meeting identity, echo robustness, long-recording resource behavior or M2 performance.

Local evidence remains under Library/Caches/MeetingOS/retry-cpu-smoke-20260908: report.json, worker.log, separate test.sqlite and copied capture. Audio/DB/cache evidence is not included in public source packages. The source fixture is benchmarks/code-switch-synthetic/mixed.wav and its existing mixed.reference.json. No identical model rerun was performed after success.

Supervisor success now returns sample count, elapsed time and sampled peak for reproducible resource reporting; callers that ignore the return value keep their existing behavior. No allocation limit, polling frequency or failure semantics changed. Failed runs still raise; this return-only summary does not promise failure telemetry.

Claude independently reviewed the instrumentation and measurement interpretation; no fixes requested. Elapsed guard time includes teardown, and peak remains a sampled observation. Full Python suite163 tests passed after the real smoke. The real run exercised isolated process-group measurement; no extra model run was made for optional instrumentation edge cases.
