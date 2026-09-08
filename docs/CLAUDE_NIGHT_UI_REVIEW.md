## Review: 4 concrete issues (evidence navigation + task states prioritized)

**1. Evidence clicks give no reliable navigation/feedback (`Intelligence.swift`, `openEvidence`)**
For same-meeting evidence, clicking a quote from the Analysis/Actions/Memory tab only calls `play(row)` — it never switches to the Transcript tab or highlights the matching row. A user reviewing a summary while on the Özet tab hears audio start but has no visual anchor for which line is playing. Worse, if `e.segment` doesn't match any current `row.id` (segment was edited/merged, or an LLM-paraphrased quote doesn't substring-match `filteredRows`), the click is a silent no-op — no error, no scroll, nothing. Cross-meeting evidence has the same fragility: `search = quote.prefix(40)` assumes the analysis quote is verbatim transcript text, which isn't guaranteed. Recommend: always jump to the Transcript tab and scroll-to/highlight the resolved segment, and surface an inline "kaynak bulunamadı" state instead of failing silently.

**2. Task states have no visual distinction beyond text inside a narrow Picker (`Intelligence.swift` `ActionsView`)**
Open, in-progress, done, and dismissed tasks all render with identical card styling (same background, same weight) — the only differentiator is text inside a 220pt Picker. In a longer task list this makes it hard to scan for what's actually outstanding, which undercuts the "readable task list, useful counts" goal. Recommend a status chip (color + label) and de-emphasizing done/dismissed cards (dim/strikethrough), plus a count of open vs. total in the header.

**3. Live recording forcibly overrides the selected meeting every 2 seconds (`App.swift`, `Model.refresh`)**
While `recording == true`, `refresh()` unconditionally sets `selected = active.id` on every timer tick. If the user clicks a different (past) meeting to review while a recording is running, they get yanked back to the live recording within 2 seconds — recording and reviewing another meeting can't coexist. This should only set `selected` once, when recording starts, not on every poll.

**4. Warning/staleness cues rely on color alone, inconsistently applied**
`row.notices`, `ActionItem.stale`, and `Insight.review` are all rendered as plain `.foregroundStyle(.orange)` text with no icon, while the meeting-level staleness banner in `AnalysisView` uses `Label(..., systemImage: "exclamationmark.triangle")`. This is both an accessibility gap (color-only signaling for low-vision/colorblind users) and a visual inconsistency across the same "needs review" concept. Recommend standardizing on the icon+text pattern already used for the meeting-level banner.

No other speculative changes recommended — these four map directly onto the evidence-navigation and task-state priorities called out for this pass.
