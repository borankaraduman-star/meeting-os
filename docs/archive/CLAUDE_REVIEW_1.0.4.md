# Claude Code checkpoint — 1.0.4

Claude Sonnet reviewed the bounded diff and full live.py through the existing Max CLI session, safe mode, no tools/MCP, no API credentials, no private data. Codex implemented and tested.

Review adjudication:

- Model warm-up/native inference can outlast the capture shutdown deadline: valid, explicitly outside this fix; independent process supervision is the first next checkpoint. No hard 15-second bound is claimed for the entire model job.
- Verify download offline override: models.fetch sets HF_HUB_OFFLINE=0 before its first huggingface_hub import in the fresh setup process. Inference remains offline by default. Already-imported Hub constants in arbitrary callers remain a separate pre-existing limitation.
- Verify environment names: installed huggingface_hub/constants.py recognizes HF_HUB_DISABLE_XET and HF_HUB_DOWNLOAD_TIMEOUT. A fresh interpreter regression test confirms default values, another confirms explicit overrides and offline inference remain intact.
- Verify remaining full-model references: source search finds only explicit catalog and model lock entries; runtime default paths do not require mlx-large.
- Reviewer confirmed bounded capture EOF wait and preserving genuine errors instead of treating them as empty cancellation. Forced kill preserves finalized files/journal; an unfinished native chunk is not guaranteed recoverable.

Validation: 75 Python tests passed together; an additional environment-override test passed with both existing download tests (76 total). Nine Swift tests passed. Native release build passed. New shutdown regression failed before the fix and passed after it. No model inference, memory stress or microphone capture in this checkpoint. The other Mac and a clean multi-GB install were not tested.
