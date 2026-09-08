# Turkish precision checkpoint — 2026-09-08

Actual Claude Code (Sonnet, existing subscription session) reviewed bounded code and public evidence. Claude owns precision/model/config experiment selection and checkpoint review; Codex owns integration, resource safety and sequential native measurements. The existing 20-minute local quality heartbeat now includes this division. This is periodic invocation, not a continuously running Claude process.

## Completed baseline after bounded retry

The two deferred cases subsequently completed with unchanged resource guards and no active user capture. Across one successful result for each of the 12 cases: **14 / 244 word errors = 5.74% WER**. There were 14 total attempts, including the original two OS-pressure failures; this is not 12 uninterrupted successful runs. See `benchmarks/results-cpp-tr-current/completed-summary.json` for selection/provenance and `benchmarks/results-cpp-tr-deferred/report.json` for retries. No successful case was replaced. macOS pressure was normal before and after the retry.

Error inspection identifies proper-name errors (Meşhed, Schlegel, Upolu) as well as orthographic differences (`on yedi` → `17`, `çevrimiçi` → `çevrim içi`). Canonical WER is unchanged; spelling/number differences are not silently forgiven. This remains a small read-speech result, not evidence of meeting/name/code-switching adequacy. Historical MLX figures are descriptive only because runtime/settings differ.

## Initial current-baseline result (retained)

CPP large-v3-turbo q5_0, CPU2, current vocabulary enabled, Sherpa diarization. Public Google FLEURS Turkish human read-speech: 12 cases attempted, 10 completed, 2 failed under OS memory pressure. Successful subset: 11 word errors / 186 reference words (5.91% WER). This is **not a full-suite accuracy score**, a meeting score, or directly comparable to the historical 12-case MLX scores. No entity/name/jargon ground truth exists in these references. Model adequacy remains unproven.

First pressure failure recorded a sampled child-tree peak of 1,802,865,856 bytes, below its 3,758,096,384-byte budget; the OS pressure guard interrupted the job. The second case failed admission. Sampled footprint is not an upper bound on instantaneous memory. No memory guard was relaxed and no model switch was promoted.

Manifest and aggregate report are in `benchmarks/fleurs-tr/cpp-current.manifest.json` and `benchmarks/results-cpp-tr-current/`. Per-case logs/results remain local. Do not automatically repeat expensive work while pressure is elevated or a user recording is active.

## Next bounded experiments

1. Complete the two deferred baseline cases once memory and recording state permit; retain failed attempts as availability evidence.
2. Hold model fixed and compare vocabulary on/off using public human references annotated for names/terms, measuring both precision and recall plus unsupported additions.
3. Evaluate held-out human code-switching and meeting speech separately from read-speech and synthetic fixtures.
4. Consider a bounded alternative local model only against matched references and resource limits. No full-model stress run, parallel inference, paid API, private transcript upload, pseudo-label training or automatic voice enrollment.

Real meeting recovery remains incomplete; its original 270 provisional segments are preserved. UI long-duration soak and live latency validation also remain open.

## Claude checkpoint, verbatim

The following response preceded run completion: its “7/12, no failures” is superseded by the final 10/12 plus two pressure failures above. Its timing caveat means unrestricted cross-speaker merging remains blocked; conservative same-detected-speaker grouping is a separate candidate requiring validation.

Corrected checkpoint, final task plan:

- Facts corrected: old result.json engine=mlx (turbo/large), diarizer=sherpa; labels correctly combine ASR+diarizer, not ambiguous.
- Old weighted WER: turbo 29/244=.11885, large 20/244=.08197 — no significance test run; don't claim significant/non-significant difference.
- Current baseline = cpp q5_0, CPU2, WITH existing vocabulary (not promptsuz); 12-clip human run in progress, 7/12 done, no failures — let it finish, don't redefine.
- CPU4 and flash/no-flash/batch already trialed live/synthetic with no convincing gain — do not repeat.
- Contiguous same-speaker windowing: ~4x synthetic speedup, but blocked on missing word timing — no unrestricted merge until timing is available.
- Native output is GGML, not GGUF — keep terminology correct in configs/docs.
- Guard is physical-footprint/OS-pressure based, not an RSS cap — don't test/tune against RSS.
- No unsafe full MLX rerun, no parallel inference proposals.
- Roles: I own precision/model/config experiment selection + results review; Codex owns integration/safety + executes single-job measurement runs.
- Priority 1: finalize current cpp q5_0/CPU2/vocab baseline result once 12/12 complete.
- Priority 2: vocabulary precision/recall + hallucination rate, prompt on vs off, model held fixed.
- Priority 3: fresh held-out human speech eval; then Priority 4: bounded local alternative model only if accuracy still insufficient — gated by prior results, no private audio/transcript upload at any step.

## Post-completion Claude review

Claude recommends a fixed-model vocabulary-off ablation on identical references, unchanged WER normalization, followed by separately annotated held-out human meeting/code-switching audio. Entity recall alone cannot identify false entity introductions.

Review correction: Claude speculated that the vocabulary was likely built from these FLEURS references. Inspection shows the existing list contains Boran/İpek/Çağrı/Gökçe and PM terms, not Meşhed/Schlegel/Upolu/nispeten, and dates to the initial implementation commit `71ab43c`. Reference-derived vocabulary provenance is not established and must not be asserted. The set is nevertheless already inspected, so a future generalization claim still requires held-out data.
