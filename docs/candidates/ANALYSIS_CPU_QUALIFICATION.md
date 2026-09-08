# A2.1 — CPU analysis runtime qualified, model not yet evaluated

Candidate1 retains Qwen3-4B-Instruct-2507, using unsloth's GGUF Q4_K_S through llama.cpp on CPU. This is a candidate, not the production default. The frozen12-case set has not been used for tuning or inference.

Pinned provenance: `analysis-cpu-qwen4b.json`. Runtime b10853 archive downloaded from the official release and verified against GitHub's SHA256 asset digest. Native executable reports build10853/commit9dcf84e5a and runs on this M4. Model metadata/revision and expected LFS SHA256 recorded; **2,383,309,920-byte model has NOT been downloaded or hash-verified yet**. Publisher model metadata lists Apache2.0. Confirm runtime license before redistribution.

Native help verified: CPU layer/thread controls, bounded batch/context controls, seed/temperature, system/prompt files, no prompt echo, single-turn and offline mode. Separate llama-tokenize supports stdin, count-only output and offline mode; actual count behavior still needs a model.

The pinned upstream schema converter was hash-verified and executed locally on `analysis_schema([1,2,3])`: conversion succeeded, grammar SHA2561735fd972252a492fce31c6feaf1381cf0640ed99addb0f9091d1f14cfbb261c. This does not yet prove native generated-output compliance. A reproducible weight-free probe is in scripts/probe-analysis-cpu.py.

Local runtime/converter/probe evidence: `~/Library/Caches/MeetingOS/cpu-analysis`. No private data used; no model inference or sockets opened. OS pressure stayed normal. Disk free snapshot17.5GB; recheck before model download and allow partial-file overhead plus1GB reserve.

Claude reviewed this checkpoint's design. Resolved prerequisites: schema mechanism and converter available; separate token-count tool; deterministic generation flags; file/stdin prompt delivery. Remaining: strict JSON and semantic validation in adapter, actual resource/quality run, exact tokenization/chat-template accounting and download disk check. Chosen initial design: one native process per call under existing supervisor, not a persistent loopback server. Avoid altering stdout into apparently valid JSON by extracting arbitrary substrings; reject malformed output.

Next bounded checkpoint:
1. Recheck active processes, pressure and disk. Download only the pinned Q4_K_S file; stream-verify LFS SHA256 without reading the whole file into RAM. Preserve resumable download; do not fetch an entire multi-quantization repository.
2. Build an experimental, non-default adapter with model/path validation, CPU2threads, no GPU, small batch, offline flag, strict output parsing and exact-token-count path. Inputs stay in private temp files/stdin. Reject context overflow rather than silently shifting it.
3. Test adapter contract using fakes first; then exactly one short development fixture under normal-pressure/3.5GiB/120s gates. No simultaneous ASR/diarization. Any pressure abort rejects the run; do not raise ceilings.
4. Only after development gates pass, run the frozen held-out set once and independently adjudicate semantics. Record false tasks, owners/dates, decisions/risks and quotes. No promotion based on syntactic success.

Sources:
- https://github.com/ggml-org/llama.cpp/releases/tag/b10853
- https://huggingface.co/unsloth/Qwen3-4B-Instruct-2507-GGUF/tree/a06e946bb6b655725eafa393f4a9745d460374c9
- https://github.com/ggml-org/llama.cpp/blob/b10853/examples/json_schema_to_grammar.py
