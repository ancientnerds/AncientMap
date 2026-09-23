# Opus re-verification of every DeepSeek-decided production row - rules fixed before the first verdict

Written 2026-09-23, before any audit agent ran. Owner order (Martin, 2026-09-23): no DeepSeek any
more, everything with Opus. The sha256 of this file is recorded in `AUDIT_LOG.md` with the results,
so the rules cannot move once the verdicts are known.

## Scope

`INPUT.jsonl` (built from a read-only export of `remediation_change_log` joined with the write
plans; sha256 in `AUDIT_LOG.md`): every `phase3:*` row in production (1,011: the mass run's 994 and
the gap lane's 17), minus the 77 rows the re-review already decided by hand
(`logs/review_holds/REREVIEW_1_FINAL.jsonl`: 45 reverse, 32 keep) = **934 rows** (site_type 554,
period_start 371, country 9). Each row carries the evidence files the finder was shown, its answer,
the reviewer's files, the old value, the written value and today's value.

## How a row is judged

The judge reads the field definitions first (`docs/procedures/FIELD_CONTRACT.md` 2.1 and 3; the
finder's false-alarm list `FALSE_ALARMS` in `scripts/remediation/phase3/model_stage.py`; the period
buckets `pipeline.utils.text.PERIOD_BUCKETS`), then the row's evidence files, then - where they do
not decide - the web (WebSearch/WebFetch, reputable sources only). Verdicts:

- `keep` - the written value is right for this site by the field's definition (a `site_type` must be
  a canonical type, `normalize_site_type(v) == v`; a coarser source does not refute a finer type; a
  `period_start` is the sort key of the site's securely attested start, and a round era value is not
  an error by itself).
- `revert` - the written value is wrong for this site, or the change was not warranted (the old value
  is at least as well supported, or the finder's reason is one of the false alarms).
- `wrong-both` - the written value is wrong and so was the old one; the judge names the right value
  with a verbatim quote and its source.
- `undecidable` - the evidence and the web do not decide it.

Every verdict cites at least one verbatim quote with its source (an evidence file path from the row,
or a URL). **A verdict whose quotes cannot be found verbatim (whitespace-normalised) in the cited
evidence file or fetched page does not count**; the row is judged again.

## Decision rule

1. Pass 1: one Opus judge per row (batches of about 15 rows).
2. A pass-1 `revert`, `wrong-both` or `undecidable` goes to pass 2: a second, independent Opus judge
   that does not see pass 1.
3. Both passes in {`revert`, `wrong-both`, `undecidable`} -> the row is **reverted** to its old value
   through the journal-reversal lane (a write that cannot be confirmed does not stay: HUMAN_ONLY B7's
   principle, "lieber eine Zeile zu wenig als eine unbelegte Zeile in der DB"). If pass 2 says `keep`,
   a third judge sees the evidence and both reasonings and decides `keep` or `revert`.
4. Pass-1 `keep` rows stand. A seeded sample of 60 of them (seed 20260923) is judged again
   independently; if more than 3 of the 60 (5 %) come back not `keep`, **every** pass-1 `keep` is
   judged a second time under rule 3.
5. `wrong-both` rows carry a proposed value; it is **not** written by this audit. It goes to a later
   correction lane that writes only with a machine-verified verbatim quote.
6. Rows whose value a later lane already replaced (`superseded`) are judged but never reverted by
   this audit.

Nothing here writes to production. The reversal is planned and applied by the mechanical
journal-reversal lane, with its own rehearsal, read-back and rollback.
