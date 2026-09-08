# Actual Fable mapped VAD review — 2026-09-09

Claude Code, claude-fable-5-1, max effort, subscription OAuth, bounded sanitized source input, no tools or private audio/transcript/DB. Session39042 completed exit0 and stream result success. Full response retained locally at build/benchmarks/fable-mapped-vad-review.md.

Verified dispositions:

- Accepted clarification: copy-on-write does not freeze external writes. Worker comment now states this explicitly. Existing _signature already includes device, inode, size, nanosecond mtime and ctime; pre/post checks reject changed inputs. Private assembled file ownership and isolated worker failure remain necessary. No guarantee against arbitrary concurrent privileged mutation is claimed.
- Rejected read-only mapping recommendation: torch.from_numpy shares memory and warns that writes through a non-writable array have undefined behavior. Suppressing that warning is not a correctness improvement. Writable copy-on-write keeps source writes isolated; outer resource guards still cover later allocations.
- Retained fail-closed SciPy mapping validation. A dependency upgrade that changes mapping behavior should fail tests rather than silently allocate a full waveform. A custom RIFF parser would introduce another parsing implementation without demonstrated benefit.
- Documented independent bounds: four hours is an input-size ceiling, not a guarantee every four-hour signal meets the 10,000-region and 600-second worker budgets. Dense/slow recordings can fail these bounds safely. No cap increase or new whole-meeting support claim.
- Did not accept the review's claim that every 512-sample window is copied, or that short-fixture equality proves all lengths. Installed Silero utils_vad.py slices tensor views and pads only the final short window. Validation evidence remains exact13-spans on95.58s and full3153.7s real VAD execution with69 matching ASR cache regions; neither is human accuracy acceptance.

No decoding model, parameters, resource guards or identity thresholds changed in response to this review. Full real retry still stops during its first new Whisper region under OS memory pressure. Long live latency, full final transcript and held-out annotated meeting accuracy remain open.
