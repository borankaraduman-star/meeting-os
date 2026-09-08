**1. Quote verification false positives/negatives**
Exact-match string verification against source transcript will fail on ASR artifacts (punctuation, casing, filler-word removal, speaker diarization splits), causing true quotes to be flagged "unverified" or hallucinated near-quotes to slip through if matching is fuzzy/normalized too aggressively.
*Safeguard:* Normalize on a documented, narrow rule set (whitespace/case only), store both raw and normalized offsets, and surface match confidence rather than a binary pass/fail.

**2. Stale source hash drift silently invalidating derived state**
If the transcript/audio is re-processed (re-run ASR, corrected speaker labels) but the hash isn't recomputed and propagated, downstream analyses/tasks keep referencing quotes and summaries tied to a source that no longer matches — manual edits compound this by making it unclear which parts are still hash-verified vs. user-overridden.
*Safeguard:* Track hash + edit provenance per field, not per record; invalidate only unedited fields on hash mismatch, and flag edited fields as "manually verified, source-independent."

**3. SQLite version/task concurrency corruption**
Versioned analyses plus durable tasks with manual edits risk write races or partial writes (crash mid-transaction) leaving orphaned task references to non-existent or superseded analysis versions.
*Safeguard:* Wrap version+task writes in a single transaction, use foreign keys with `ON DELETE RESTRICT`, and add a startup integrity check for dangling references.

**4. On-device task draft over-trust**
MLX-generated task drafts may fabricate assignees, deadlines, or action items not actually present in the meeting, especially on ambiguous/overlapping speech — since generation is unconstrained by quote-verification, it lacks the same evidentiary check as summaries.
*Safeguard:* Require each draft task to link to a verified supporting quote before being marked "ready," else mark "unverified — needs review."

**5. Manual export handoff data staleness**
Since exports to Codex/Claude are explicit and manual, a user could export an outdated analysis version after later edits/corrections, propagating stale or reverted content into external tools with no automatic sync-back.
*Safeguard:* Stamp exports with version ID + timestamp and warn if the source analysis has changed since last export.
