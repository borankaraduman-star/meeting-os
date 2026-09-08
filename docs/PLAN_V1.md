# Meeting OS V1 — authorized scope expansion

The user explicitly asks to continue until the original plan, including summaries
and todo extraction, is implemented with Claude Code reviews. No further approval
pause for ordinary implementation; no external actions without specific consent.

1. Local MLX language model, sequential after STT, no paid API. Bounded transcript
   chunks, evidence-backed canonical record: summary, decisions, risks, questions,
   actions (owner, quoted due date, source segments, uncertainty). Retry malformed
   output once; never silently mark failed analysis complete.
2. SQLite versioned analyses keyed to transcript fingerprint. Stable action IDs,
   open/in-progress/done/dismissed status, Boran/My Actions, user edits and audit.
   Rerunning analysis never destroys manually tracked tasks. Stale source changes
   visible and prevent preparing outdated tasks.
3. Local drafts for spec/PRD, code plan, research plan and messages. Evidence-linked,
   explicitly draft, no sending. Deterministic routing recommendation and compact
   agent handoff markdown. User copies selected context into subscription clients;
   no hidden uploads/CLI tools executing transcript instructions.
4. Native UI: transcript/summary/My Actions/memory, analysis progress/retry, source
   evidence links, owner/due/status edits, prepare draft/export. Automatic local
   analysis after final/import with failure separate from recorded transcript.
5. Local stdio MCP for read-only meeting search, contributions, analyses, actions
   and compact packets. No web listener, no action execution. Grounded cross-meeting
   Q&A with citations and abstention when search has no evidence.
6. Meaningful tests: Turkish commitments/negation/proposals/unknown owner/no due date,
   prompt injection, bad JSON/evidence, stale analyses, task status persistence,
   actual local-model quality/runtime and desktop flows. Claude architecture and
   adversarial reviews on compact code and invented fixtures only.
7. Existing audio limitations tracked honestly; no fabricated natural-meeting or
   GUI permission validation. Package updated source/app, docs, model lock and tests.
