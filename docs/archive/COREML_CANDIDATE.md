# Core ML encoder candidate — not enabled or benchmarked

Pinned upstream README describes ANE encoder offload via WHISPER_COREML=1 and a compiled encoder, with a separate first-device compilation cost:
https://github.com/ggml-org/whisper.cpp/tree/52a939a2a762224e255d366c1182b2af4dd1a032#core-ml-support

Current installed whisper-cli otool output links Accelerate/Metal/MetalKit but no CoreML framework. This is evidence against CoreML-enabled linkage, not a full runtime backend assertion. Local source build cache is absent; build script pins revision52a939a2a762224e255d366c1182b2af4dd1a032. No rebuild, encoder download/conversion or runtime configuration change performed.

Actual Claude review: plausible bounded candidate, but explicit gates required; one public clip is only smoke. ANE/CoreML service memory can live outside supervised child tree. Do not claim existing child footprint budget caps total experiment memory or repeat the earlier Metal trial as if it were CoreML. Until measurement accounts for external services, do not enable on this16GiB machine merely on upstream speed claims. Keep OS-pressure guard unchanged.

Proposed post-recovery gate: separate source/build/encoder path and conversion environment; never overwrite active CPP/model or shared dependencies. Observe system pressure normal for60s before admission; stop on first elevated pressure or resource-probe error. No concurrent capture/retry/inference. Record conversion/compile disk,time and cold start separately; verify runtime reports CoreML loading rather than silent CPU fallback. Single public clip smoke requires finite output/timestamps and no extra reference word errors relative to matched CPU baseline. This is only entry to a paired multi-case CPU/CoreML evaluation, never default promotion. Any proposed promotion requires at least20% median end-to-end improvement across matched cases, no aggregate word-error increase, and memory/availability evidence including outside-tree services. These are proposed acceptance thresholds, not achieved results. Preserve source/name/code-switching held-out evaluation as a separate quality requirement.

Current priority remains completed long-record recovery and real diarization checkpoint reuse; avoid adding another heavy runtime while these are unverified. Review log: build/benchmarks/claude-coreml-candidate-review.md.
