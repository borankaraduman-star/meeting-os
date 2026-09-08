# Idle matched CPP comparison

Same tracked synthetic clips 1 and 2 (5.598s total), same pinned binary and q5_0 turbo model, CPU two threads, same vocabulary/decoder. Single guarded inference tree, no live recording. Results under `benchmarks/results/cpp-*-matched-2026-09-08.json`. ABBA comparison reduces order bias but two repeats on a shared laptop cannot establish stable distributions.

- Serial 9.662s, 10.001s; batch 9.343s, 9.508s (~4.1% faster mean). Exact structured output equality FALSE; does not necessarily mean text differs, because timestamps/confidence are included. No WER/DER claim. Not promoted.
- Flash 9.374s, 13.166s; non-flash 11.483s, 12.858s. Wide variation, non-flash mean slower. Exact structured output equality FALSE. Not promoted.
- Prior live batch/no-flash experiments did not meet real-time requirements. Prior live GPU trial hit memory protection; live GPU remains unconditionally disabled. The expiring trial profile is absent. Exception rollback is best-effort and revision checked, not a SIGKILL/atomic rollback guarantee.

## Guard failure found and fixed

First benchmark aborted before useful inference with ResourceProbeError. Instrumented reproduction recorded proc_pid_rusage errno=1 on a running `ps` process in the worker process group. This was a protected diagnostic subprocess, not model allocation. Repeated the same benchmark successfully after moving only fixed ps/sysctl diagnostics into separate sessions (existing 2–3s check_output timeouts unchanged). Native models and Python inference workers remain in their owned groups and keep footprint/OS-pressure limits.

Claude Code reviewed the change and highlighted group cleanup: check_output reaps/terminates its direct diagnostic child on normal completion/timeout; abrupt supervisor SIGKILL could leave a diagnostic temporarily running outside the model group. These are finite read-only system queries, not inference. No universal orphan guarantee is claimed for diagnostics. Existing inference descendant-kill tests and new real nested monitoring regression pass.

Validation: supervisor 11, low-memory 8, live 20, benchmark 4, CPP batch 4, pipeline 5 tests pass. UI remains responsive (sampled <1% CPU); OS pressure sampled normal. No paid API, user audio upload or routing/permission change.

Next performance hypothesis: repeated short VAD regions incur separate full encoder passes. A contiguous live-chunk pass could amortize those while diarization still uses real turn boundaries. It requires matched text/timestamp/speaker/quiet-gap tests before enabling. Neither current candidate solves live latency. Real meeting final pass is also outstanding; do not mark goal complete.
