# Preview failure visibility and completion handoff

Healthy native audio capture must still yield a provisional completion receipt when only live STT fails; the existing native UI then runs a same-meeting full retry. Previously preview exceptions joined capture errors, raised at record end and prevented this handoff. Fixed for future recorder processes. Native/helper/journal failures still fail capture normally. Current user recorder46784 is already running old code and was not restarted; it can still end incomplete after its earlier124 preview errors. Once it actually exits and no competing inference exists, inspect native stop/journal evidence and recover the same meeting553993e7544a through normal retry; do not assume automatic completion of this old process.

Added per-recording preview-failures.jsonl (fsync; no error message/transcript), a receipt preview_failed_chunks counter, and bounded current/legacy error summarization scoped to exact capture directory. Counts are lower bounds; no errors is not proof of a complete transcript. Existing active bridge reads old last-job.log and reports124 known failures in .19s total snapshot. It returns no private text/paths in the summary. Future durable logging cannot be hot-applied to already running recorder.

Extended Claude-authored formatter with a fourth line "Canlı metin eksik" and explanatory help; installed native app remains unchanged until safe idle signed rebuild.21 isolated formatter tests passed. No claim of full app layout verification.

Claude reviewed the recorder/ledger change. Accepted silent-ledger-write-failure concern: if durable error logging fails, record marks incomplete/nonzero instead of clean success. Added receipt failure count. Its claim of no fallback trace was overstated: stdout legacy logging already existed. Its partial-row duplication concern is addressed by existing RetryStore.finish transactional replacement (DELETE old meeting segments then staged INSERT), confirmed in code and31 retry tests; a failed chunk means not fully processed, not that every row is absent. Persistent model/config failure circuit-breaker remains a future consideration, not required to preserve raw capture; known preview failure is now explicitly reported.

Added early OS pressure admission before model resolution/loading in make_pipeline; previously cpp guard was reached after Python embeddings/diarization setup. This code applies to fresh worker calls now. No stress loads or concurrent inference used.

Validation:73 targeted Python tests passed (preview7,live9,retry31,desktop8,capture_state5,low_memory6,silent_live7).21 isolated Swift formatter tests passed. Tests verify native capture errors still fail, preview-only failure yields a valid receipt/status, failed ledger write fails clean completion, raw fixture untouched, legacy scoping/dedup/bounded tail and no false completeness claim. Current real old recorder still unmodified; pressure1 at final check. Real finalization and full installed UI tests remain unperformed.

Prepared benchmarks/cpp-batch-smoke with4 clips/10.805625s from existing tracked synthetic code-switch sample plus exact digital silence; manifest stores source hash, original voice boundaries and scripts. No private meeting audio. Native matched batch test remains OFF/unrun. When idle and pressure normal, from repo run:

```sh
.venv/bin/python scripts/benchmark-cpp-batch.py benchmarks/cpp-batch-smoke/clip-*.wav --output "$HOME/Library/Caches/MeetingOS/batch-benchmark.json"
```

The harness refuses active Meeting OS audio jobs, uses180s outer guard, reports ABBA times/equality/distinctness/binary hash, and makes no model-quality ground-truth claim. Do not promote batch based only on fake tests.
