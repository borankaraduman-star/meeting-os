# A2 — CPU runtime qualified; candidate rejected by resource gate

Candidate1 retains Qwen3-4B-Instruct-2507, using unsloth's GGUF Q4_K_S through llama.cpp on CPU. This is a candidate, not the production default. The frozen12-case set has not been used for tuning or inference.

Pinned provenance: `analysis-cpu-qwen4b.json`. Runtime b10853 archive downloaded from the official release and verified against GitHub's SHA256 asset digest. Native executable reports build10853/commit9dcf84e5a and runs on this M4. Model metadata/revision and expected LFS SHA256 recorded; **2,383,309,920-byte model downloaded and stream-verified: SHA256 `90bc7227557ed8a417696b6ed8a94b2c351ad1d94de39bf2889ad8778366c68a`**. Publisher model metadata lists Apache2.0. Confirm runtime license before redistribution.

Native help verified: CPU layer/thread controls, bounded batch/context controls, seed/temperature, system/prompt files, no prompt echo, single-turn and offline mode. Separate llama-tokenize supports stdin, count-only output and offline mode; native token-ID JSON output successfully parsed during the short development run.

The pinned upstream schema converter was hash-verified and executed locally on `analysis_schema([1,2,3])`: conversion succeeded, grammar SHA2561735fd972252a492fce31c6feaf1381cf0640ed99addb0f9091d1f14cfbb261c. This does not yet prove native generated-output compliance. A reproducible weight-free probe is in scripts/probe-analysis-cpu.py.

Local runtime/converter/probe evidence: `~/Library/Caches/MeetingOS/cpu-analysis`. No private data used. Weight-free qualification stayed at normal OS pressure; subsequent A2.2 model inference failed the resource gate (below). Disk free snapshot17.5GB; recheck before model download and allow partial-file overhead plus1GB reserve.

Claude reviewed this checkpoint's design. Resolved prerequisites: schema mechanism and converter available; separate token-count tool; deterministic generation flags; file/stdin prompt delivery. Remaining: strict JSON and semantic validation in adapter, actual resource/quality run, exact tokenization/chat-template accounting and download disk check. Chosen initial design: one native process per call under existing supervisor, not a persistent loopback server. Avoid altering stdout into apparently valid JSON by extracting arbitrary substrings; reject malformed output.

Historical A2.2 procedure (executed through step3; step4 blocked by resource failure):
1. Recheck active processes, pressure and disk. Download only the pinned Q4_K_S file; stream-verify LFS SHA256 without reading the whole file into RAM. Preserve resumable download; do not fetch an entire multi-quantization repository.
2. Build an experimental, non-default adapter with model/path validation, CPU2threads, no GPU, small batch, offline flag, strict output parsing and exact-token-count path. Inputs stay in private temp files/stdin. Reject context overflow rather than silently shifting it.
3. Test adapter contract using fakes first; then exactly one short development fixture under normal-pressure/3.5GiB/120s gates. No simultaneous ASR/diarization. Any pressure abort rejects the run; do not raise ceilings.
4. Only after development gates pass, run the frozen held-out set once and independently adjudicate semantics. Record false tasks, owners/dates, decisions/risks and quotes. No promotion based on syntactic success.

Sources:
- https://github.com/ggml-org/llama.cpp/releases/tag/b10853
- https://huggingface.co/unsloth/Qwen3-4B-Instruct-2507-GGUF/tree/a06e946bb6b655725eafa393f4a9745d460374c9
- https://github.com/ggml-org/llama.cpp/blob/b10853/examples/json_schema_to_grammar.py

## A2.2 actual development run

The non-default `NativeLocalLLM` adapter supplies prompt/schema through private temporary files, enforces offline CPU2 threads, rejects chat delimiters/context overflow and strictly validates returned JSON. Model identity records filename, revision and verified hash. Native tokenizer completed; generation then caused non-normal OS memory pressure and the independent guard killed the owned native process. Total request elapsed **7.196 seconds** on this shared M4/16GiB Mac. OS pressure was normal before launch and returned to normal afterward. Peak footprint was not persisted, so no peak-memory claim is made. The3.5GiB threshold is a configured abort limit, not a measured peak.

Case: only fictional development fixture `tests/fixtures/analysis/cancel.json`, output allowance1800tokens, context4096, batch/ubatch128, GPU/offload disabled. No completed JSON output, semantic score or held-out run exists. This workload is rejected under the existing resource gate; do not rerun it unchanged, raise ceilings, terminate unrelated applications or promote the adapter. No production model selection changed. The frozen12-case set remains untouched.

Local evidence: `cpu-analysis/short-case-report.json`, `short-case.log`, `download.log` under the MeetingOS cache. Download/cache/runtime remain local and excluded from source release. Further model-family experiments require a documented, materially smaller resource hypothesis and count toward the plan's two-family limit. Recovery/diagnostics and echo work can proceed without model loading.

## Independent Claude review disposition

Claude reviewed the narrow adapter/supervisor/test package through the existing authenticated CLI. Its binary/CLI concerns were contradicted by the actual pinned b10853 runtime: `llama-completion` exists and help explicitly supports `--color [on|off|auto]`, `--fit [on|off]`, `--no-op-offload` and `--json-schema-file`. No options were removed based on recollection of older versions.

Accepted privacy finding: native failure stderr can contain input. Added optional `failure_details=False` to supervisor, selected by the adapter for tokenization and generation; errors retain only exit code. Regression first failed, then passed. Existing caller behavior is preserved. Tests separately verify stdout capture and failure stderr separation.

Tokenization/completion special-token parity remains an explicit unverified prerequisite for any future promotion. Do not claim exact end-to-end budgeting from the successful tokenizer invocation alone. Output allowance includes generated termination tokens; no evidence justified a speculative off-by-one patch, but the bound must be empirically validated before integration. Guard measurements are macOS-only. Candidate is already rejected by the stronger observed resource failure, so no additional inference was performed to investigate these pending compatibility gates.
