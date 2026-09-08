# Desktop UI repair and redesign

User requested implementation of the interface by Claude Code, with Codex testing
and integration. Claude works in an isolated copy containing only desktop source
and tests; no recordings, profiles or meeting database are provided. Codex owns
the real application installation and test window. No API keys or paid API calls.

## Reproduced defect

At a 1000 × 852 outer window with 15 meetings, the sidebar and detail content
expanded beyond the window. AX geometry placed the record button 115 pixels above
the window's top and meeting title 216 pixels above it. The NavigationSplitView
reported a 1489-pixel content height. Primary actions, navigation and settings were
not reachable. This is a containment bug, not just a cosmetic titlebar issue.

## Selected design

Retain the native SwiftUI application and all existing Model operations. Use a
bounded sidebar and flexible content area, with independent scrolling of the
library and meeting contents. Record/stop remains a global action, visible when
another meeting or tab is selected. Headers, tabs and footer controls remain in
the window. Prefer native adaptive light/dark surfaces, restrained teal accents,
readable transcript rows, distinct selected meeting and accessible control names.
Errors expose full details in bounded space. Preserve recovery, cancellation,
speaker enrollment, evidence navigation and draft-review safeguards.

## Acceptance checks

- Build and Swift behavior tests; compare Model/runtime code with the baseline.
- Actual macOS window geometry at small, default and large sizes.
- All four tabs, meeting selection, transcript search, settings and edit sheets.
- Record and stop remain visible while navigating; bounded real short capture.
- Rebuild uses the pinned signing certificate; no ad-hoc signature regression.
- Review screenshots, including long library and light/dark appearance.

`scripts/verify-desktop-layout.py` reads only accessibility IDs, geometry and enabled
states. It reports missing/out-of-window required controls without collecting
transcript or profile values. It does not start recordings or alter permissions.

## Results

Claude implemented Layout.swift, TranscriptView.swift and the presentation refactor.
Codex verified unchanged Model/runtime code, added explicit cancel buttons, empty
profile guidance and larger footer hit areas, then installed through the pinned
signing builder. Final 15 Swift tests passed. Actual geometry checks, four tabs,
light/dark screenshots, search, modal dismissal and a ~25-second recording while
browsing another meeting passed. See UI_LAYOUT_TEST_2026-09-08.json.

The smallest outer window is 900×652 (620 content + 32 native titlebar).
Baseline has 15 meetings; the live test increased it to 16. First search automation
typed into the still-focused title field; explicit AX focus corrected the test.
Sheet tests must inspect sheet descendants separately and wait for transitions.
No audio/transcript content was sent to Claude. Screenshots remain in local cache.
Long error details are capped in code, but no injected-error visual test was run.
