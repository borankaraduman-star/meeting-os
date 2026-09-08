# Frozen fictional analysis acceptance set

12 cases, two per category. Claude Code independently authored the set. Codex reviewed references before any candidate evaluation: removed an inferred risk from a conditional statement; replaced a redundant unanswered-question case with an unnamed speaker commitment; strengthened one quoted-instruction case with an explicit attack example. No candidate outputs were used to make these edits.

`manifest.json` freezes the exact UTF-8 bytes of `cases.json`. Do not change this set or include its labels/text in tuning prompts. If a reference is later found invalid, record the issue and create a separately versioned suite; do not silently repair a failing candidate's score.

Cases are invented and published intentionally. Labels are not human-adjudicated ground truth. Independent review of candidate output remains mandatory. Compare semantic task identity before owner/date correctness; do not grade by task count alone. Decisions/risks/questions and unsupported summary facts require separate review. See the acceptance plan for fixed release gates and remaining natural-meeting validation.
