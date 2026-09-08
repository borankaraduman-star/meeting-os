# Uncached private assembly experiment

The uncached-transfer retry reached VAD but stopped under OS pressure. This experiment also applies per-descriptor F_NOCACHE during assembly of the private snapshot. It is opt-in via scripts/probe-uncached-retry.py --uncached-assembly; production defaults, raw recordings, models, later pipeline opens and memory guards remain unchanged. Successful invocation still finalizes the selected real meeting through normal atomic retry.

The adapter scopes SoundFile replacement to synchronous assembly only and restores it on success/failure. It accepts owned0700 registered-pattern temporary snapshot roots, bounded events journals, listed six-digit source WAVs and newly created mic-full/system-full outputs. Source files open read-only with O_NOFOLLOW; output files use O_EXCL. Actual SoundFile positional parameters are retained; descriptor output explicitly uses WAV. Numeric markers prove successful source/destination flag application without content or paths. Do not run this process-global temporary class replacement concurrently with other soundfile consumers.

Inspection caught a real macOS integration mismatch: tempfile writes /var paths while resolve() yields /private/var. Parent normalization now accepts that spelling difference without bypassing descriptor/inode protections. The regression originally failed and now passes.

Validation:34 combined assembly/progress/retry/audio tests pass, including8 adapter tests. Actual Darwin F_NOCACHE on tiny synthetic16k/48k stereo sources gives identical PCM with gaps/overlaps/>1 peaks and unchanged raw hashes. This is fidelity/adapter verification, not large-file memory or live performance acceptance. Full real retry experiment remains pending at this checkpoint.

Real full experiment55850 subsequently completed assembly and entered mic VAD, then stopped under OS pressure after16.12s. Runtime markers confirm both transfer and assembly descriptor flag paths executed. Original270segments/69ASRoutputs retained; private dead workspace removed. See real-uncached-assembly-retry-2026-09-09.json. Not promoted; no demonstrated full-recovery benefit over transfer-only.
