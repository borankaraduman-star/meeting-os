# Meeting OS Implementation Plan

**Goal:** local dual-source capture, Turkish transcription, persistent speakers.
**Spec:** DESIGN.md. Codex implements; Claude Code reviews compact checkpoints.
**Isolation:** new repo; development branch v0.1. No other project files changed.

- [x] Core: tests first for identity rejection, model isolation, corrections,
  Turkish normalization, silence handling. Implement types.py, store.py,
  metrics.py; verify with unittest on temporary databases.
- [x] Capture: Swift recorder and packaging script. Compile against installed
  macOS SDK. Test synthetic PCM chunk persistence, source separation and timing.
- [x] Inference: audio.py VAD, backends.py MLX/Whisper/cpp, speakers.py
  Resemblyzer/ECAPA/pyannote, pipeline.py. Test offsets and failure handling.
  Fetch ungated models explicitly and smoke-test available engines.
- [x] CLI: __main__.py record/live/import/finalize/show/label/enroll/profiles,
  models and benchmark commands. Validate complete saved-audio workflow.
- [x] Benchmark: manifest-driven evaluation with references, runtime/memory,
  speaker/identity metrics. Include code-switching/name/jargon read-aloud corpus
  and annotation instructions for 3–5 meetings; mark unavailable results honestly.
- [x] Claude adversarial review; fix material findings with regressions.
- [x] Fresh full tests, Swift build, CLI smoke, docs and measured status report.

Real-meeting accuracy and gated pyannote evaluation remain external validation, as recorded in VALIDATION.md.
