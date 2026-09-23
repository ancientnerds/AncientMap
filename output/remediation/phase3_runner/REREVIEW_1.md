# Re-review of the 77 written rows whose reviewer contradicted itself - rule fixed before the call

Written 2026-09-23, before any call of this re-review. Its sha256 goes into `AUDIT_LOG.md` with the
result.

## The rows

`output/remediation/logs/review_holds/WRITTEN_HELD_BY_PHRASE.jsonl`: the 77 rows the mass lane wrote
to production (stamps `phase3:batch-*`) whose reviewer answered `REFUTED: NO` while its `WHY:` line
names a failing half (`review_stage.failing_half`, the writer's `RULE_REVIEW_CONTRADICTS` of
2026-09-23). 48 `site_type`, 29 `period_start`, in 69 batches. It is the class the owner decided to
leave unwritten for the 72 held rows (HANDOVER decision 1, HUMAN_ONLY B7); these 77 were written
because the hand read missed them (by that read: 62 genuine contradictions, 10 false holds, 5 mixed).

## The rule (one draw, no re-rolling)

Each row gets **exactly one** new reviewer call: the frozen `REVIEWER_QUESTION`, the finder's own
unchanged answer, the finder's own evidence (`runs/rereview1/<batch>/`, copied byte for byte from
`runs/mass`). The row is **kept** only when that one new verdict is a clean clearance:

1. `REFUTED: NO`, and
2. no problem on the answer (the writer's `applies`), and
3. its `WHY:` line names no failing half (`review_stage.failing_half` is None).

Every other outcome - `YES`, `UNRESOLVED`, unreadable, a problem, a contradicting `WHY:` - **reverses**
the row through the journal (new value = the journal row's old value, conditioned on the live value
still being the written one), and the field is listed as open, not as corrected.

A reversal restores the curated value that stood before the remediation. It does not claim that
value is right; it withdraws a correction whose support did not hold.
