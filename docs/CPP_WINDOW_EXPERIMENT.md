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

## Native matched result

Real CPU CPP on four fixtures: serial 21.216/23.008s versus window 5.396/5.509s (~4.1x faster, ~75% lower elapsed). Script WER 0.1818 serial versus 0 window on this tiny synthetic sample. Report: `benchmarks/results/cpp-window-matched-2026-09-08.json`. Not a real-meeting WER result and not a production promotion.

Critical qualification: timed_words=0 in every run, so zero timing violations/gap words is **no evidence of timing accuracy**. Investigation found backends.py explicitly returns words=[] for CPP, discarding full JSON tokens. The pinned CLI sets token_timestamps for -ojf; an actual synthetic native probe (`build/benchmarks/cpp-token-probe.json`) confirms subword text/offsets including zero-duration subwords and special tokens. Next prerequisite: conservatively group complete lexical tokens into words, preserve original text, validate bounds and fall back when incomplete; mark heuristic timing approximate. Validate speaker transitions before enabling contiguous live windows.

## Claude same-speaker window review checkpoint

Actual Claude Code reviewed current pipeline code, without private meeting content. Accepted concerns: check every diarizer turn over the full merged interval (not just endpoints); reject unknown/overlapping/other-speaker spans; detected labels do not prove identity; changed ASR row spans may include more silence in embedding clips and shift identity scores; missing word timing cannot repair an incorrectly merged speaker transition. Required checks include mid-gap other speaker, unknown/uncovered speech, nonzero offsets, unchanged input sample timeline, and embedding/identity comparison alongside WER. No production merge is enabled.

Review corrections: contiguous `audio[begin:end]` slicing does not duplicate VAD padding or inflate real gap time; Claude's padding-duplication claim does not apply to this design. Current embeddings already use ASR-row intervals within VAD-padded clips, not guaranteed speech-only audio. The relevant question is whether merging changes those intervals and identity outcomes. Claims that timing necessarily worsens on gaps are untested hypotheses, not findings.
