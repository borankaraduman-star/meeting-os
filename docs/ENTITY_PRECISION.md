# Closed-set name and term precision

Benchmark reference JSON accepts optional `entity_universe`, a fixed list of names and terms including plausible wrong additions. Declare it before looking at model output and reuse it across configurations. Example:

```json
{"text":"İpek checkout konuştu.","entities":["İpek","checkout"],"entity_universe":["İpek","Boran","checkout","backlog"]}
```

For hypothesis `İpek Boran backlog konuştu.`, true positives=1, false positives=2, false negatives=1, precision=1/3 and universe recall=1/2. The existing entity_recall field retains its original supplied-gold-list meaning; entity_universe_recall uses the new universe denominator. Do not average or compare these denominators interchangeably.

Scoring counts unique normalized phrase types with whole-token matching. Duplicate/case-equivalent entries collapse. Repeated mentions are not counted, nested phrases can both count, Turkish suffix variants are not automatically matched, and wrong contextual attribution is not detected. This is not open-world NER: an invented name outside the universe is invisible. Human auditing and WER remain necessary.

Missing universe produces null precision/counts, not a false100% result. Empty prediction gives null precision; no gold terms gives null recall. Malformed universes fail before any benchmark inference or output directory creation. Legacy references continue to work. Numeric results appear in report.json, with a clearly labeled closed-set precision column in REPORT.md.

Validation:13 entity/benchmark tests passed, including incorrect additions, empty gold/prediction, normalization, boundaries, report integration and pre-inference rejection. Actual Claude Code reviewed the diff; its validation-timing concern was addressed by reference preflight. No human accuracy improvement is claimed by adding this measurement.
