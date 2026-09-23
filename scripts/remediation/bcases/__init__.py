"""The owner cases of HUMAN_ONLY section B (B1 names and coordinates, B2 country vs coordinates,
curated duplicates), decided from data wherever the data decides them.

The owner's instruction for these cases (2026-09-22/23) was "implement the recommendations" of the
remaining-work map (`output/remediation/logs/remaining_map_2026-09-22.json`, block "B - owner cases").
This package is that implementation, and it writes nothing to production:

* `collect.py` - the only part that leaves the machine: one read-only export of the 5,004 curated rows
  and the Wikidata and Wikipedia answers the classes need, each cached once;
* `classify.py` - pure functions of those files: every record carries its class and the evidence the
  class was decided from;
* `coord_plan.py` - the coordinate write plan in the guarded shape of `qid_repair.py` (render, check,
  verify, rollback), through `apply_remediation_change()`, applied by nobody here;
* `qid_research.py` - the candidates behind the second wave of `output/remediation/tools/qid_repair.py`
  (the wrong Wikidata links among the B1 name findings whose name does not match - a kept name on a
  suspect link is flagged, `link_suspect`, and left for a later wave);
* `run.py` - the command line.

`output/remediation/bcases/` receives the per-class JSON lines, the duplicate list the scope lane
consumes (`DUPLICATES.jsonl`: `loser_id`, `survivor_id`, `evidence`) and the coordinate plan.
"""
