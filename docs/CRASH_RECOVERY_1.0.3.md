# 8 September 2026 — desktop crash recovery, 1.0.3

## Evidence and responsibility
At approximately 10:59 Istanbul, WindowServer watchdog reported its main thread
unresponsive for 40 seconds. Same-time Jetsam event identifies the test Python
PID98653 as largest process: 541492 × 16384-byte pages, approximately 8.26GiB.
Other already-open applications consumed substantial memory too. Machine has
16GiB RAM. Strong evidence points to memory pressure triggered/aggravated by our
unbounded full-size Whisper test. This was an unsafe test choice on a shared Mac.
Uptime did not reset: desktop/session failed, not a confirmed kernel reboot.
Raw OS reports remain on this Mac and are not included in the public package.

## Recovery observed
After session restart, test/model processes were no longer running; no additional
heavy inference or artificial memory-pressure test was launched. No user files
were deleted and unrelated apps were not terminated. At 11:05 kernel memory
pressure level was1 (normal), one-minute load fell from155.5 to5.58. Swap remained
~1.1GiB; this alone does not require deleting caches or rebooting.

## Fixes
- Import/finalize default to local turbo. Full decoder models (>4 layers) rejected
  before weights load on machines below32GiB. This changes the quality/speed tradeoff;
  no claim of identical accuracy to full large model.
- MLX cache limited to64MiB and cleared after ASR regions. Memory-limit API is
  advisory; NOT presented as a hard allocator limit.
- Native app independently measures child physical footprint (includes compressed
  footprint unlike ordinary RSS) with budget25%physical RAM, max10GiB. It monitors
  OS warning/critical pressure. Non-recording owned jobs receive termination;
  live recording receives normal stop, preserves audio and suppresses auto-finalize.
  An in-flight native model call can delay graceful recording shutdown.
- Python checks OS pressure before MLX load and each ASR region. Failure is explicit
  and retryable, not silently continuing under pressure.
- Added stage/count/elapsed progress; stop avoids unnecessary queued live inference
  before final processing. Durable captured chunks remain available for finalize.
- Corrected result memory note: RSS does not bound total Metal/compressed footprint.

## Validation
70 Python +9 Swift tests passed before final diagnostic-wording adjustment.
Large-model CLI invocation was rejected on this16GiB Mac without loading weights.
Native build passed. No full-size rerun after crash; resource guard tests do not
allocate heavy models. Earlier turbo240sec public constructed fixture took67.63s;
full-size GUI import took385.78s and coincided with desktop failure, so it is NOT a
successful usability/stability benchmark. Fixture was assembled from public Turkish
FLEURS samples, not a natural meeting; no private audio sent to Claude.

Claude review: guard-call-site concern already covered by backends.py and real CLI
rejection. Fail-closed diagnostic now chains original exception type. Prior concerns
about duplicate finalize segments and stale progress are prevented by separate final
meeting records and unique per-job files removed on process completion.

Limits: no guarantee against all system/app memory exhaustion; no new M2 hardware
measurement; real live-capture revalidation was interrupted by the desktop incident.
Do not resume long model tests without resource-budget enforcement and monitoring.

Final focused validation:4 resource tests passed (including safe defaults and
OS-pressure rejection). Protected app relaunched with no heavy job started;
pressure level remained1. New tests bring total discovered Python tests to72;
full70 earlier plus final4 resource tests, not a claimed fresh full72 run.
