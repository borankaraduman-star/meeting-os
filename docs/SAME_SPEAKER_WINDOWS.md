# Same-detected-speaker window experiment

Implemented an internal opt-in `asr.same_speaker_windows=True` for provisional CPP processing only. Default is absent/false; desktop tuning does not expose it. Final/retry processing stays unchanged. Incompatible with batch-region trial. Source samples remain contiguous slices of original audio, including real gaps; no concatenated or duplicated padding. Result metrics flag merged-region counts and experimental status.

Group constraints: one known detected label for each region, no different/unknown turn anywhere in the full proposed span, at most 12s span and 750ms gap. Each individual region permits at most 250ms unlabeled edge padding, requires >=50% detected coverage, and rejects internal uncovered holes. These are conservative experiment policy values, not calibrated guarantees about true speaker identity. Diarizer mistakes can still group different humans. Existing segment embedding boundaries may change; saved identity consistency remains a required acceptance test.

Six tests cover actual pipeline call reduction and exact input samples/offsets, default/final exclusion, mid-gap or within-region other speakers, unknown/missing labels, insufficient coverage, oversized windows, and invalid region order/overlap. Combined pipeline, bounded-final and CPP batch suites: 20 tests passed.

Native trial uses the existing Turkish TTS clips 1 and 3 with a real 600ms gap, actual VAD/Sherpa/Resemblyzer/CPP, current vocabulary and FLOAT files. Off: two ASR calls, 10.80s. On: one call, 5.30s. Both zero edits against an 11-word script; same detected diarizer turn. Sampled tree peak ~1.47GiB. Single off/on order permits warm-up bias, and TTS/empty profile store do not establish human/identity accuracy. No production promotion.

Real meeting's first finalized mic chunk was tried in a private temporary store under the unchanged supervisor. It failed OS memory pressure after 5.96s, sampled tree peak 1,676,364,944 bytes, before comparison completed. No meeting DB/raw audio changes or immediate retry. Reports in `benchmarks/results/speaker-window-*-2026-09-08.json`. Next gate: matched human off/on/reverse-order validation under stable resources, actual saved-profile consistency and cross-speaker fixtures before any recording-scoped opt-in.

Actual Claude Code received the bounded grouping implementation for review but the call timed out after 90 seconds. No independent review approval is claimed; this is another reason to leave production opt-in disabled.
