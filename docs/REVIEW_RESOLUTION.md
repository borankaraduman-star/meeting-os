# Claude Code checkpoints

Two compact read-only Sonnet reviews used the existing authenticated Claude Max
session. API-key environment variables were removed for both invocations.
Only design/source excerpts were sent; no meeting audio/transcript/profile data.
Codex retained implementation ownership. No duplicate implementation agents.

Architecture review: shared host clock + capture gap events; explicit profile
model IDs; isolated benchmark processes; VAD padding; session leakage guard.
The review's suggestion to forbid *speaker* overlap across enrollment and test
was not adopted: cross-meeting identification requires the same known speakers.
Sessions must be disjoint; unknown speakers are additional held-out test cases.

Adversarial review findings 1–5 and 7–8 were validated and fixed: short tails
borrow voice context without duplicating timeline; missing identity/ASR metrics
remain unknown; process launch/wait failures update meeting status; missing
memory values are not zero; screen/audio permission errors are actionable.

Finding 6's assertion that one 3-second sample outweighs many equally weighted
samples was not supported by the implementation. Keep one equal vote per
explicitly enrolled sample; enrollment is never inferred. Added a regression
for contradictory zero-norm centroids so conflicting samples abstain safely.
Threshold calibration and sample quality still require held-out human recordings.

Additional local fixes: SpeechBrain's YAML pretrained path is overridden with
the downloaded local directory; otherwise it tried HF references and correctly
failed in offline mode. Static whisper.cpp build avoids missing dylib rpaths.
Generated app xattrs are cleared before ad-hoc signing for reproducible rebuilds.

## Native desktop checkpoint

Accepted and fixed: unread stderr pipe (nullDevice + 10-second bridge timeout),
normal-quit process handling (defer exit until stop/drain/finalize), atomic
profile enrollment plus label, idempotent enrollment of the same segment,
lightweight UI payloads, model/runtime persistence, main-app TCC usage strings,
explicit canceled-before-audio state, active recording selection and source status.

Not adopted as findings: live.py already created a draft meeting with capture_dir
before launching the recorder, forwarded SIGINT, drained chunks, waited native
exit, and marked incomplete on failure. These review claims were based on missing
context. SQLite meetings are explicitly ordered newest-first. Finalization creates
a separate record intentionally; UI edits are disabled on provisional records,
so manual live corrections cannot silently disappear. Same-name different people
are explained in profile UI; distinct display names are required.

Native stdout loss is tested; recorder owns capture-native.jsonl independently.
macOS system permission dialog was not bypassed when the computer-use tool denied
access. GUI import/label/reopen passed; actual GUI capture awaits first-run OS consent.

## Final checkpoint

The final review's claimed numpy truth-value crash does not reproduce: Embedder
returns `unit(...tolist())`, a Python list, and real human inference passed.
Still changed the pipeline condition to explicit `is not None` for a future
array-returning adapter. The claimed absent enrollment quality validation is
already enforced by Store.enroll_segment (including prohibited flags and 3-second
minimum), with regression tests; it is not duplicated in the bridge. Added an
explicit complete-meeting guard to desktop label/text/enroll actions so UI timing
cannot submit edits to processing meetings. CLI finalization and the native UI
already implement the provisional→separate-final-record path; provisional records
are intentionally retained for recovery, not converted in place.
