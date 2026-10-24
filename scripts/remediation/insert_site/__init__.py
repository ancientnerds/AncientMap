"""D57: the journalled insert lane - new Ancient Nerds Originals for the high-demand sites.

Owner decision D57 (2026-10-24): the 38 high-demand in-scope sites without a curated page, plus Chaco
Canyon, become Ancient Nerds Originals (`source_id = 'ancient_nerds'`, so they get an SSR page, a card
and every lane) through a journalled insert lane: rehearsed, undone by retiring (never DELETE - the
source is protected), and the matching `site_proposals` rows closed as `approved` with
`promoted_site_id`. D58 (same day) is the scope rule: only the medieval Old World of Europe, Byzantium
and the Vikings is out, so L'Anse aux Meadows stays out.

No module here calls a model. The steps, each a pure function of its inputs plus one read:

* `candidates.py` - the candidate list: the CSV rows the 2026-10-08 hand review marked `in`, plus the
  pinned additions (Chaco Canyon), each resolved to its Wikidata item and English article; the pinned
  exclusions (D58) and parents (D25) beside them; a read-only production read says which are curated
  already and which proposals name them (`CANDIDATES.jsonl`, `CANDIDATES.md`);
* `research.py`   - the research handoff in the opus_handoff format: one question per candidate,
  answered by the `field_researcher` role in the fields lanes' answer format (`fields/answers.py`,
  rule `recheck`) plus a name, a country and the description's sources; imported with every quote
  found verbatim in its page (`DECISIONS.jsonl`);
* `plan.py`       - the insert plan from the decisions and a fresh read-only production read: one
  curated row per researched site with the exact column set a curated row carries, its
  `raw_data` provenance, its label and alias names, its external ids, its parent and the proposals
  it closes (`PLAN.jsonl`, `REFUSALS.jsonl`, `PLAN.md`);
* `writer.py`     - `APPLY.sql` and `ROLLBACK.sql` (the retirement through
  `apply_remediation_change()`, the scope lanes' one write path), pinned to the plan, then rehearse,
  probe-guards, apply, read-back, rehearse-rollback and accept.

`run.py` is the one command line. The runbook is docs/procedures/INSERT_SITES.md.
"""
