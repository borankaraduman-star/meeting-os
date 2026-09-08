Two concrete findings in the empty-state / filtered-list logic:

**1. The single `rows.isEmpty` fallback conflates "no meeting selected" with every terminal meeting status.**
```swift
if m.rows.isEmpty { ContentUnavailableView("Dinlemeye hazır", ...,
    description:Text("Bir toplantı kaydedin veya ses dosyası açın...")) }
```
This fires identically whether nothing is selected, or a meeting is selected but `processing`/`provisional`/`failed`/`incomplete`/`canceled`. For a selected-but-failed/canceled meeting, telling the user to "record or open a file" is actively misleading — they already have a meeting, and the real remediation (recover/retry, or wait) is shown elsewhere (`activity` text, recover button) but not reflected in this placeholder at all. A user could re-record thinking nothing happened.

**2. `filteredRows` silently drops the search filter when a segment is focused, and there's no "no matches" state or reachable clear action for search alone.**
```swift
var filteredRows:[Row] { if let id=focusedSegment { return rows.filter { $0.id==id } }; return search.isEmpty ? rows : rows.filter { ... } }
```
- If `focusedSegment` is set, whatever the user types in the search field is silently ignored (early return before the `search` branch) — the field looks live but does nothing, which is a hidden/unsafe interaction rather than misleading copy per se.
- If `search` alone narrows `filteredRows` to zero while `rows` is non-empty, the view renders nothing: the `ScrollView`'s `ForEach` is empty and the fallback `ContentUnavailableView` is gated on `m.rows.isEmpty`, which is false. Result is a silent blank pane with no indication search matched nothing.
- The existing "Tüm konuşmayı göster" button is only shown `if m.focusedSegment != nil`, not when `search` is the cause of an empty/narrowed list — so there's no button-driven way to clear a fruitless search; only manually deleting the text field content works.

These are the two spots the planned "no matches" + clear/show-all button, and the status-aware empty state, need to address.
