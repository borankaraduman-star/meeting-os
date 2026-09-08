# Meeting OS V0.1 — approved scope

Boran's request authorizes implementation of the local ear only. No summaries,
agent routing, messaging, paid inference, or uploading meeting audio.

## Initial architecture (historical planning checkpoint)
- macOS 15+ Swift ScreenCaptureKit recorder. Microphone and system audio are
  separate timestamped WAV chunks. A single serial writer finalizes each chunk
  before publishing JSONL; interrupted recordings retain finalized chunks.
- Python CLI: record/live, import/transcribe, finalize, list/show, correct labels,
  explicitly enroll/delete speaker profiles, benchmark.
- MLX Whisper turbo live / large-v3 final are candidates, not asserted winners.
  Compare OpenAI Whisper CPU and whisper.cpp Metal on the same WAV and references.
- Silero VAD with bounded segments. Original segment text stays unchanged;
  vocabulary is a prompt, never a forced replacement. Confidence consists of
  raw ASR metrics and flags, not a calibrated probability.
- Ungated local embedding clustering is a baseline; optional pyannote Community-1
  provides stronger full-recording diarization after its model access agreement.
  Compare Resemblyzer and SpeechBrain ECAPA embeddings. Model-specific profile
  namespaces prevent cross-model cosine comparisons.
- SQLite stores meetings, segments, voice samples, corrections. Enrollment is
  explicit, requires clean >=3s speech; recognition cannot train profiles.
  Unknown / ambiguous speakers stay unknown. Thresholds need real-data calibration.
- CLI live is provisional. Whole-track finalization is a separate run; capture
  remains independent of inference speed and logs backlog/failures.

## Evaluation and constraints
M4 / 16 GB; load models sequentially. Model downloads are explicit, free, and
networked; inference defaults offline with telemetry disabled. Use headphones to
avoid system audio bleeding into mic; no claim of acoustic echo cancellation.
Compare normalized/raw WER, CER, vocabulary recall, DER including overlap,
identity false accepts/rejects, real-time factor, peak RSS, live lag, silence
hallucinations. Three to five consented real meetings, with manual reference
annotations and held-out speakers/sessions, are required before quality claims.
No real meeting audio was supplied. Synthetic smoke fixtures are not quality proof.

## Delivered architecture update

Native SwiftUI desktop controls the CLI through local Process/stdio; no web server
or open port. It provides library, recording, import, editing, explicit profile
management, playback, vocabulary and exports. Swift helper owns its fsynced native
journal; capture starts before inference warmup. Finalization intentionally creates
a separate meeting and editing is gated to complete meetings in the desktop bridge.

Measured public Turkish read speech favored large-v3 for final/import; turbo remains
live. Sherpa ONNX pyannote3 segmentation + TitaNet-small global clustering .9 is the
default; the fixed-window clustering baseline and gated Community-1 are optional.
Resemblyzer remains the profile encoder after held-out utterance tests. Text edits
retain the original and audit trail. No consumer-subscription API integration exists.
See VALIDATION.md for current measurements and first-run macOS permission limitation.
