# Retry-only completed diarization checkpoints — implemented, long-record acceptance pending

Real owned-audio retry completed full diarization then failed at ASR10/392 due to OS pressure. Persisting completed diarization avoids repeating its native memory peak on an otherwise identical retry. This does not reduce first-run native memory, guarantee successful recovery or change recognition quality.

Wrap only retry pipeline diarizer.turns_file. Cache key includes exact decoded float32 samples and dimensions (streaming bounded hashing), source, sample/frame format, complete model contents, actual Sherpa runtime native artifact identity/version, threshold, relevant code and platform/configuration. Check artifact identity before/after lookup or computation; fail rather than store mixed-generation output. Use a meeting-owned SQLite table with FK cascade, bounded payload/count/LRU and checksum; completed turn list and key committed together. Cache read corruption is a miss. Never cache incomplete output, embeddings, identity decisions or live chunks. Preserve exact sorted-start turn list and valid overlaps. Existing atomic final transcript replacement remains unchanged.

Actual Claude Code reviewed the design, emphasizing complete keying, atomic writes and overlap preservation. Its FLOAT16 concern misread the supplied description: snapshots are float32 WAV at16kHz, not float16. Hash the same snapshot the worker reads. Review at build/benchmarks/claude-diarization-checkpoint-plan.md.

Acceptance: first red tests for failed computation not stored, interrupted downstream ASR with successful diarization reused by fresh wrapper, exact output/overlap preservation, audio/model/config/runtime changes forcing miss, invalid/oversized/corrupt payloads rejected and deletion cascade. Then short native equality/reuse, then actual long retry with interruption/resume evidence. No resource guard relaxation or parallel heavy work. Ten real ASR checkpoints currently exist; full recovery, held-out human accuracy and live acceptance remain open.

## Implemented and verified

CheckpointDiarizer wraps isolated Sherpa turns_file in run_retry only. All model tree files, Sherpa package Python/native dylib/so files and relevant pipeline code are content-hashed. Canonical float32 samples, source and frame count form the audio key; platform, environment and threshold form artifact identity. Snapshot/artifact signatures and resolved artifact list are checked before returning a hit or saving native results. Protected private retry inputs remain the trust boundary; this is not protection against a malicious same-user writer defeating filesystem metadata checks.

SQLite commits key/payload/checksum together, bounds single entry to4MiB and global payload to32MiB/128entries, evicts by LRU, and cascades meeting deletion. Bounds cover declared payload, not total database/WAL size. Empty completed turns can be cached; failed computation cannot. Invalid cache data is deleted and recomputed. SQL errors fall back to native with diagnostic error counts. Cached full turns retain overlap; embeddings/identity are still recomputed. No live path cache.

33 relevant tests passed, including actual run_retry integration: downstream failure preserves the original transcript, subsequent retry uses completed turns once and commits the final replacement. Native public95.58s four-voice fixture: exact13turn baseline match; first calculation including hashing4.711s, fresh-wrapper reuse including hashing0.208s. Evidence benchmarks/results/diarization-checkpoint-native-2026-09-08.json. Same Python process with fresh wrappers; full real interrupted-run acceptance still pending.

Actual Claude code review found no blockers (several tentative claims in its response were self-retracted). Retained pre/post checks rather than adopting its suggestion to remove them. No claim of live latency, first-run memory reduction or improved recognition accuracy.

## Correction: WAV metadata must not define audio identity

Real resume session41921 missed the cached full diarization because newly assembled float WAVs contain a PEAK timestamp. Original whole-container hashing was safe against false hits but defeated reuse across different creation times; earlier same-file native test and same-second integration fixture failed to expose it. That session was intentionally canceled at144.24s to install this fix, not an OS crash.270 original segments and56ASR rows preserved; one private workspace cleaned.

Schema2 now hashes mono16k float32 decoded samples in65536-frame blocks, canonical little-endian bytes plus dimensions. WAV metadata is excluded; any sample-bit change remains a miss. Input mutation guards and finite checks remain. Helper code participates in artifact identity, so previous schema1 diarization rows safely miss and can be LRU-evicted; ASR keys are unaffected. First schema2 full diarization must still be computed once.

30 relevant tests passed. Native95.58s test deliberately changes PEAK timestamp before a fresh wrapper: exact13turns reused, hit1/miss0, first7.229s vs reuse.292s including hashing. This is short-fixture evidence; actual long regenerated-snapshot reuse must still be verified. Artifact: benchmarks/results/diarization-canonical-key-native-2026-09-09.json.

Actual Claude Sonnet medium-effort review found no blockers. Four-hour bound is intentionally inherited. Its stat/open concern is bounded by private immutable retry ownership and pre/post inode/size/mtime/ctime checks; replacement or modification normally changes that signature. No claim of protection against a malicious same-user ABA writer.
