"""L5: the journalled link and name pass of the curated sites (HUMAN_ONLY B1-L, B1-N, Nr. 7).

Decided 2026-09-26 under the owner's O9 (`output/remediation/HUMAN_ONLY_DECISIONS_2026-09-26.md`):
an Opus agent reads each site; a Wikidata item or English Wikipedia title is written only when the
item or article names exactly this site (no type, no container, no sibling), otherwise the wrong
link is removed; a site is renamed only to a sourced name of that very site. L5 runs before WD1's
Wikidata harvest trusts the links (`site_external_ids`, where the harvest reads each site's QID and
enwiki title).

* `population.py` - who is read, and the production read (read-only) the questions are built from;
* `questions.py`  - the question and the exact answer shape;
* `handoff.py`    - the rounds of questions through `opus_handoff.py`, the agents' brief, the shape
                    check and the import (fetch, quote check, title resolution, decision);
* `web.py`        - the User-Agent and the title resolution (the refresh's query, L5's transport);
* `decide.py`     - the machine checks of an answer: quotes found (`opus_audit/quotes.py`), titles
                    resolved the way the daily refresh resolves them, a replacement item at the
                    site's place, the refresh's fixed point;
* `plan.py`       - the decisions as journalled writes: link steps of at most 100 sites through
                    `qid_repair.render_split(removals=True)` and the name lane `name-l5`
                    (`mechanical/lane.py`, written by `mechanical/apply.py`);
* `links.py`      - a link step's production commands (check, rehearse, probe-guards, apply, verify,
                    rehearse-rollback);
* `run.py`        - the CLI; the runbook is `docs/procedures/SITES_DB_REMEDIATION_2026-09.md`,
                    "WE lanes".
"""
