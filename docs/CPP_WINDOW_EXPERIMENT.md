# Contiguous-window experiment (not enabled in production)

Hypothesis: per-VAD-region model invocations repeat encoder work. A single bounded window retaining original silence might reduce that overhead without cutting speech. This is a benchmark candidate, not a change to live/final inference.

`benchmark-cpp-batch.py --comparison window` compares serial/window/window/serial on the same mono 16kHz clips (CLI resamples using read_audio), inserts 200ms gaps, and caps the whole window at 12s. Optional explicit fixture manifest gives script WER. Reports normalized text agreement, word timing bounds, missing/invalid timings and words with midpoint in inserted gaps; exports no transcript text. These are not DER or aligned timing-accuracy metrics. Timing remains subject to shared-machine variation; native ASR starts a fresh child each call (no result memoization), but ABBA is not a guarantee against thermal/cache bias.

Claude Code reviewed the function. Fixed malformed timestamps aborting metrics and rejected empty/nonfinite clips. Its missing-time-import warning does not apply (module import exists); 16kHz is enforced by CLI read_audio, not inferred from arrays. Its claim that ABBA must be non-adjacent contradicts the named sequence; retain ABBA and the explicit variability limitation.

Eight benchmark tests pass, including preserved silence, correct serial offsets, known WER difference, absent reference, malformed timing, hallucinated gap words, length budget and active-job refusal. Native window timing/quality has NOT run: recovery of real meeting 553993e7544a is active (parent 40778, worker 40784). Revalidate those PIDs before any inference; never treat this document as current process ownership.

When idle, from repo:

```sh
.venv/bin/python scripts/benchmark-cpp-batch.py benchmarks/cpp-batch-smoke/clip-{1,2,3,4}.wav --comparison window --reference-manifest benchmarks/cpp-batch-smoke/manifest.json --output build/benchmarks/cpp-window-matched.json
```

Run only through the guarded CLI. No concurrent model, GPU, changed thread count, or default promotion. Source scripts are synthetic, not human-annotated real meeting references.
