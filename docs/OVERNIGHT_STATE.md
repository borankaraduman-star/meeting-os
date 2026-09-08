> Superseded for the new overnight request: see NIGHT_ITERATION.md. Heartbeat reactivated until 2026-09-08 09:00 Europe/Istanbul.

# Meeting OS checkpoint — V1

Repo: `/Users/boran/Library/Application Support/MeetingOS/repo-v0.1`.
User-facing link: `outputs/meeting-os-local`. Durable runtime outside iCloud.

V1 scope now implemented: local constrained Qwen3 analysis, cited summaries,
decisions/risks/questions/tasks, durable Boran task queue and manual edits,
local editable drafts, deterministic routing and local handoff, native UI,
read-only stdio MCP, grounded local memory search/QA, real-model and human
reference evaluation harnesses. No paid inference APIs or outbound actions.

62 automated tests pass. Three constrained-model fictional cases pass; long
summary/retraction real-model smoke passes; fresh STT and MCP smoke pass.
GUI analysis/task/draft/edit/export/memory flows checked with fictional demo.
Final integration report and delivery package are the authoritative results.

Open external validation: native GUI macOS consent still needs user's own
interaction; never bypass. No 3–5 natural meeting recordings/references were
provided, so no natural meeting accuracy or full long-session guarantee.

See TESLIM.md, docs/VALIDATION_V1.md and docs/V1_REVIEW_RESOLUTION.md.
Existing overnight heartbeat remains paused after local delivery; do not create
new recurring jobs unless requested. Do not rerun finished checks without reason.
