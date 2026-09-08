Three concrete defects, each with an exact repro sequence:

**1. `openEvidence` rejects valid targets when `meetings` cache is stale/empty (App.swift `Model`, `Intelligence.swift openEvidence`)**

`memorySearch()`/`askMemory()` hit the backend directly and never touch `self.meetings`. `openEvidence` gates navigation on `meetings.contains(where:{$0.id==e.meeting})`.

- Launch app. `meetings` is still `[]` (first `snapshot` refresh hasn't returned).
- Immediately open the Memory tab, type a query, tap "Kayıtlardan yanıtla" — this returns real evidence for an existing meeting, independent of the snapshot cycle.
- Click that evidence before the first `refresh()` completes.
- `openEvidence` sees `!meetings.contains(...)` → sets `error="Kaynak toplantı bulunamadı."` and returns, even though the meeting genuinely exists. Navigation is silently dropped instead of retried once the cache catches up.

**2. `refreshIntelligence`'s single staleness guard drops legitimate global updates on meeting switch (Intelligence.swift `refreshIntelligence`, `updateAction`)**

`refreshIntelligence(mid)` gates the *entire* write (`analysis`, `actions`, `drafts`) on `mid==selected` at response time, but `actions`/`drafts` are cross-meeting lists (`ActionsView`'s "Tüm görevler"/"Boran'ın görevleri" filters only make sense if `m.actions` spans all meetings).

- On meeting A's Actions tab, mark a task "Tamamlandı" → `updateAction` calls `request(action_update)` then `refreshIntelligence(selected ?? "")` with `mid = A` captured at call time.
- Before that request returns, switch selection to meeting B (sidebar click).
- The response for A arrives; `mid(A) != selected(B)` → the guard discards the response, so the just-saved status change never reaches `m.actions`.
- Any Actions view visible during this window (e.g. "Tüm görevler") shows the task reverted to its pre-edit state, even though the backend write already succeeded, until the next 2s timer tick happens to refresh with the then-current `selected`.

**3. Round-tripping tabs silently cancels an in-flight evidence resolution (App.swift `Model.tab` didSet, Intelligence.swift `resolvePendingEvidence`)**

`tab`'s didSet unconditionally clears `pendingEvidence` whenever `tab != "transcript"`, with no distinction between "user explicitly navigated away" and "en route to Transcript already."

- Click evidence pointing into a currently-recording ("provisional") meeting whose segment hasn't synced yet. `pendingEvidence` is set and the "Kaynak bölümü bekleniyor…" banner shows, correctly waiting (`resolvePendingEvidence`'s processing/provisional guard).
- While waiting, click "Analysis" tab, then click "Transcript" tab again (a plausible reflex while waiting).
- The first tab change fires `tab`'s didSet with `tab != "transcript"` → `pendingEvidence=nil`. The return to Transcript doesn't restore it.
- The pending navigation is abandoned with no error and no banner — the segment will now never auto-focus once it arrives, and the user has no indication their evidence click was lost.
