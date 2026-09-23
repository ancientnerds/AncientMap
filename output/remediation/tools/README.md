# The instruments of the 2026-09 remediation

These are the scripts the write action was actually run with, copied here out of
`output/remediation/logs/` (which is scratch and not versioned) so that a fresh clone has them.
They are working code, not a library: no package, each one a `python <file>` entry point. Since
2026-09-22 they have tests (`tests/remediation/test_remediation_tools.py`).

**They locate their data relative to the repository** (`lanes.py`: three levels above the script,
which is the repository both from here and from a working copy in `output/remediation/logs/`), and
that data - `logs/_write_dry*/`, `logs/_write_apply*/`, `phase3_runner/runs/` - lives in
`output/remediation/logs/` and `output/remediation/phase3_runner/`. They can be run from here
directly. A fresh clone has no such data - the archive named in `../HANDOVER.md` restores it:

    tar -xzf output/remediation/run-2026-09-22-complete.tgz -C output/remediation

The working copies that were run on 2026-09-21/22 are still in `logs/`; the copies here are newer
(lanes, the chain acceptance, the stale-plan guard, the stops of 2026-09-23). Run these from here;
the old copies in `logs/` should be deleted rather than run, because they lack every guard below.

## A lane that has written keeps its plan

A lane's `ALL_ROWS.jsonl` stops being scratch the moment its first batch is written: it is the plan
the production rows were reviewed and written from, and the hold list and the acceptance read it. A
re-plan with the writer's rules of today is a different file under the same name - on 2026-09-22 the
citation check turned the mass lane's 1,074 rows into 1,028, and the acceptance then reported its 44
correct production writes as deviations. So:

* `write_dry_all.py` refuses to write into the dry root of a lane that has an `APPLIED.json`; a
  measurement goes to `--out`;
* `verify_writes.py` and `make_holds.py` refuse a rows file whose change keys are not the pinned plan
  of a written lane (`lanes.REVIEWED_PLAN_KEYS_SHA256`; the mass lane's is `0b7ad95d...`);
* `write_gate.py`'s stale-plan refusal does not tell anyone to re-plan a lane that has written.

## What stops a wave

`write_gate.py` stops, and marks nothing applied, when a writer call wrote fewer rows than it was
handed (its pre-flight found a moved row and wrote none of the chunk - an exit code 0), when a step's
read-back finds a deviation, and before anything when a hold names no planned row. A stopped batch
carries `STOPPED.json`; a later run refuses it until a person has read it and removed the marker.
`verify_writes.py` needs every planned row to be either written (with exactly the planned values) or
withheld (a hold, or a boundary refusal of `write_gate.gate`); a planned row that is neither is a
deviation. A later stamp may change a lane's rows only if it is named with `--allow-stamp`.

## Lanes

Every write/acceptance tool takes `--lane` (default `mass`). A lane names the run directory, the dry
plan, the apply markers, the hold list, the reviewer logs and the journal stamp pattern at once, so one
run can never be read as another's (`lanes.py` has the table). The gap run is `--lane gap`:
`runs/gap`, `logs/_write_dry_gap/`, `logs/_write_apply_gap/`, stamps `phase3:gap-%`. The sitelink
run is `--lane sitelink`: `runs/sitelink`, `logs/_write_dry_sitelink/`, `logs/_write_apply_sitelink/`,
stamps `phase3:slk-%` (its pilot's batches are `slkg-NNNN`, in `runs/sitelink-gold`, and never write).
Individual paths can still be overridden (`--run-dir`, `--out`, `--rows`, `--apply-root`, `--hold`,
`--stamp-like`).

| script | what it does |
| --- | --- |
| `lanes.py` | the lanes' paths, the one JSON-lines reader, the database seam (the writer's `run_sql`, `_json_rows`, `_sql_text`) and the pins of written lanes' plans; no entry point |
| `write_dry_all.py` | builds the full write plan over every reviewed batch of a lane (`ALL_ROWS.jsonl`); touches no database; refuses to replace the plan of a lane that has written |
| `make_holds.py` | writes the mass lane's hand-hold list (`_write_apply/HOLDS.jsonl`), keyed by `change_key`; refuses a rows file that is not the mass lane's pinned plan |
| `write_gate.py` | the writer: 100-site steps, conditional `WHERE`, journal row, read-back. Without `--apply` it is a dry run and says so. Refuses rows of another run, a rows file that is not the writer's plan today and a hold that names no row; stops on a short write and on a read-back deviation |
| `verify_writes.py` | the independent acceptance: asks production in both directions, follows the journal chain (the planners' rule, `scripts/remediation/journal_chain.py`), checks every row against the plan and the withheld set, prints `RESULT: N deviation(s)` (was `ERGEBNIS:` until 2026-09-23) |
| `review_all.py` | drives the reviewer stage over every batch of a lane (4 workers, $8 cap on this pass's own spend) |
| `review_totals.py` | the reviewer census (`review_totals.txt`) |
| `found_summary.py` | the finder census over the model reports |
| `country_census.py`, `country_probe.py` | the country/boundary census (258 polygons, 96 spellings) |
| `scan_rows.py`, `show_rows.py` | find and inspect rows in the plan |
| `batch_summary.py` | per-batch counts |
| `gap_plan.py` | builds `PLAN.gap.jsonl` for the fields the mass run never judged, from a fresh read-only production export; its item rule (`withheld_reason`, `shared_counts`) reads every rule of the external-id repair's three waves, and the sitelink lane passes all three |
| `sitelink_plan.py` | builds the sitelink lane's plan: the mass run's UNVERIFIABLE writable fields (4,342) asked again with up to three of the item's other-language Wikipedia articles, each pinned to a revision; drops every key another lane wrote (the fresh journal, checked against `logs/search_lane/written_keys.txt`), the mass lane planned, or a hand decision holds (B2 countries, the 29 B10 census rows, duplicates); reports how many country fields the stored point already verifies (T02). `census`, `export` (read-only SELECTs), `sitelinks` (read-only Wikidata and Wikipedia GETs, 1 s per host), `plan`, `measure`; `--pilot` for the gold-standard pilot. Commands below |
| `qid_repair.py` | renders the reviewed `site_external_ids` repair - plan, apply, rehearsal, rollback; applies nothing. Wave 1 (`output/remediation/qid_repair/`, applied 2026-09-23), with `--wave 2` the wrong links among the B1 name findings whose name does not match (`output/remediation/qid_repair/wave2/`, applied 2026-09-23), and with `--wave 3` the kept names whose link is a generic concept or a shared item (`output/remediation/qid_repair/wave3/`, researched by `bcases/run.py research --suspects`; 2 replacements, the other 37 sites listed as keep-type, duplicate-candidate, link-right or unresolved). Waves 2 and 3 are researched by `scripts/remediation/bcases/qid_research.py` and gated at 1 km |
| `score_search_pilot.py` | scores a search pilot's run directory against the gold standard: the four thresholds sealed in `phase3_runner/SEARCH_PILOT.md`, as sealed, beside them what the writer itself would write, and what each of the writer's three 2026-09-23 rules refuses on its own (`--run-dir`, `--prefix`, `--progress`, `--gold`). `--lane sitelink` scores the sitelink pilot (`phase3_runner/SITELINK_PILOT.md`) against the same four thresholds, threshold 4 counted over its articles (`TRANSPORTS`) |
| `measure_review_holds.py` | measures the writer's period-bucket gate and reviewer contradiction hold on the mass lane's pinned plan, its 72 hand holds and two read-only production exports (written keys, the journal's `period_start` rows); writes the two lists of written rows `HUMAN_ONLY.md` B11 asks about to `logs/review_holds/` (`--out-dir`), nothing else |

Each needs `PYTHONIOENCODING=utf-8`. The writer's child processes get the repository root and
`scripts/remediation` on their `PYTHONPATH` from `write_dry_all.writer_env()`, and they run under the
interpreter the tool was started with (`sys.executable`) - start the tools with the repo venv. A
console encoding once killed a whole write wave on a `print` before the first row; that is why the
gate reconfigures its own streams.

## The sitelink lane's plan (2026-09-23)

The run, the census snapshot, the mass lane's pinned plan and the two production lists are not in git;
in a worktree, point the flags at the main checkout (`M` below). Nothing here buys a model call.

```bash
cd /c/PythonProjects/AncientMap && export PYTHONIOENCODING=utf-8
T=output/remediation/tools; PY=./.venv/Scripts/python.exe; M=output/remediation
IN="--mass-run $M/phase3_runner/runs/mass --data $M --rows $M/logs/_write_dry/ALL_ROWS.jsonl \
    --written-keys $M/logs/search_lane/written_keys.txt --country-census $M/logs/_country_mismatches.txt"
# the lane (-> sitelink/lane/, phase3_runner/PLAN.sitelink.jsonl, batches slk-NNNN)
$PY $T/sitelink_plan.py census --mass-run $M/phase3_runner/runs/mass   # 4,342 questions, 3,124 sites
$PY $T/sitelink_plan.py export                                          # read-only SELECTs
$PY $T/sitelink_plan.py sitelinks $IN                                   # read-only GETs, pins revisions
$PY $T/sitelink_plan.py plan $IN                                        # summary.json: counts, geometry
# the pilot (-> sitelink/pilot/, PLAN.sitelink-gold.jsonl, batches slkg-NNNN; SITELINK_PILOT.md)
$PY $T/sitelink_plan.py census --pilot --mass-run $M/phase3_runner/runs/mass
$PY $T/sitelink_plan.py export --pilot
$PY $T/sitelink_plan.py sitelinks --pilot $IN
$PY $T/sitelink_plan.py plan --pilot $IN
# a dry fetch of the pilot's evidence (fetch only, its own scratch ledger), then its measure
R=$M/phase3_runner/runs/sitelink-gold-dry2
$PY scripts/remediation/phase3/run.py prepare --plan $M/sitelink/pilot/PLAN.sitelink-gold.jsonl --run-dir $R
for b in slkg-0001 slkg-0002; do $PY scripts/remediation/phase3/run.py fetch --live --run-dir $R \
    --batch-id $b --ledger $M/logs/sitelink_scratch/LEDGER.dry2.jsonl --pacing-dir $M/logs/pacing; done
$PY $T/sitelink_plan.py measure --pilot --run-dir $R --out $M/logs/sitelink_scratch/measure_pilot2.json
# the pilot's score, once SITELINK_PILOT.md's run has been made
$PY $T/score_search_pilot.py --lane sitelink
```

`plan` refuses a `sitelinks.json` resolved under other inputs than today's (another item, withholding,
stored country or evidence room): run `sitelinks` again. The mutation proof is
`scripts/remediation/phase3/mutation_sweep.py "sitelink: "`.
