# User-authorized memory cleanup — 2026-09-09

User explicitly requested finding and clearing the blocker, then continuing. Two development PostgreSQL instances had no client sessions; Redis had only the inspection connection. All three were gracefully stopped with unlimited stop timeout; no volumes, containers or files deleted. A guarded public3s CPP test still failed on OS pressure at0.61s, sampled535,135,696bytes. Thus stopping only those databases did not establish adequate headroom.

Docker VM still held2,390,069,088bytes physical footprint, the largest measurable process. Home Assistant was then gracefully stopped and Docker Desktop stopped normally (no force flag). Home Assistant is temporarily unavailable. VM PID3757 exited and OS pressure returned1. A full real recording retry started as PID72833/tool session93757; see build/recovery-after-docker-stop-watch.json for its state and later checkpoint evidence for the outcome. No completion claimed at launch. Video decoder previously accounting838MB had already disappeared before cleanup; its disappearance is not attributed to this work.

Restart the stopped services when the heavy MeetingOS validation is finished or they are needed:

```sh
/usr/local/bin/docker desktop start
/usr/local/bin/docker start anonim-feedback-arsiv-claude-pg purodak-split-api-postgres-1 purodak-split-api-redis-1 homeassistant
```

Existing unless-stopped restart policies were unchanged. The explicit start command is needed because these containers were manually stopped. Reopening Docker during inference may restore shared memory pressure. No global cache purge, model deletion, application force quit, decoder change or resource guard relaxation was performed.

First verified progress after cleanup: full mic VAD completed and transcription advanced from69cached regions to75/392, with69hits and6new successful checkpoint writes, no cache errors. OS pressure remained1 at this observation. This passes the previous first-new-region blocker; full recording completion remains unproven while job93757/PID72833 runs.
