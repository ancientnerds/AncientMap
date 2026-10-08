"""Identity discovery (final repair 2026-10-08, workstream map `plans/identity.md`, section 3).

Deterministic, read-only. Production is read once (`export.py`, one repeatable-read transaction)
and the wikidata items come from the local harvest (`entities.py`); everything after that is a pure
function of those files, so a run can be repeated and its counts compared. No model is asked here:
what these modules write is the *population* and the *evidence* the later question stages need.

* `export.py`         - the one production read (shown sites, ids, names, pairs, retired losers,
                        the period journal) and its tagged-export file;
* `entities.py`       - the wikidata items: the 2026-09-26 harvest plus a delta for the missing ones;
* `funnel.py`         - D13: records that describe a modern town or village (`IDENTITY_FUNNEL.jsonl`);
* `dup_clusters.py`   - D14: duplicate clusters (`DUP_CLUSTERS.jsonl`);
* `names_triage.py`   - D23: name defects and the rule-made spoken name (`NAMES_TRIAGE.jsonl`,
                        `SPOKEN_RULE.jsonl`);
* `scope_window.py`   - D20: the sites outside the E3 window (`SCOPE_WINDOW.jsonl`);
* `parents.py`        - D25: component sites (`PARENT_CANDIDATES.jsonl`).

The outputs are run data in the main checkout (`output/remediation/final-2026-10-08/identity/`,
gitignored); the code and its tests are what is committed.
"""
