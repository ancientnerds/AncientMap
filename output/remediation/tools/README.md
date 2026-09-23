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

Phases 4 and 5 add three lanes, one per row group of `scripts/remediation/phase4/write4.py`, each
with its own journal family: `p4` (descriptions, `phase4:p4-%`), `p4l` (legacy disclosure,
`phase4l:p4l-%`) and `p5` (cards, `phase5:p5-%`); their plans, statements and markers live in
`logs/_write_apply_p4|_p4l|_p5/<batch>/`. They are written by `write_gate4.py`, not by the phase-3
gate.

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
| `gap_plan.py` | builds `PLAN.gap.jsonl` for the fields the mass run never judged, from a fresh read-only production export; its item rule (`withheld_reason`, `shared_counts`) reads every rule of the external-id repair's waves 1-3, and the sitelink lane passes every wave (wave 4 names no site: it plans from its resolution record) |
| `sitelink_plan.py` | builds the sitelink lane's plan: the mass run's UNVERIFIABLE writable fields (4,342) asked again with up to three of the item's other-language Wikipedia articles, each pinned to a revision; drops every key another lane wrote (the fresh journal, checked against `logs/search_lane/written_keys.txt`), the mass lane planned, or a hand decision holds (B2 countries, the 29 B10 census rows, duplicates); withholds an item the repair waves or the owner-case classifier set aside, each under its rule (`suspect-link`, and the item is the site's place: `container-item`, `item-is-not-the-site`, `item-is-a-locality`); refuses the bot-generated wikis and reads Swedish only for Swedish and Finnish sites; reports how many country fields the stored point already verifies (T02). `census`, `export` (read-only SELECTs), `sitelinks` (read-only Wikidata and Wikipedia GETs, 1 s per host), `plan`, `measure`; `--pilot` for the gold-standard pilot. Commands below |
| `qid_repair.py` | renders the reviewed `site_external_ids` repair - plan, apply, rehearsal, rollback; applies nothing. Wave 1 (`output/remediation/qid_repair/`, applied 2026-09-23), with `--wave 2` the wrong links among the B1 name findings whose name does not match (`output/remediation/qid_repair/wave2/`, applied 2026-09-23), and with `--wave 3` the kept names whose link is a generic concept or a shared item (`output/remediation/qid_repair/wave3/`, researched by `bcases/run.py research --suspects`; 2 replacements, the other 37 sites listed as keep-type, duplicate-candidate, link-right or unresolved). Waves 2 and 3 are researched by `scripts/remediation/bcases/qid_research.py` and gated at 1 km. With `--wave 4` the 20 curated `source_url` values that hold two URLs joined by a newline (`output/remediation/qid_repair/wave4/`, not applied): `resolve --wave 4` reads production (read-only) and resolves the English Wikipedia URL through the boot refresh's own `enwiki_title_from_url` + `resolve_titles` into the versioned `RESOLUTION.json`; `render` plans from that file alone - `source_url` keeps its first URL through `apply_remediation_change()`, the article becomes `enwiki_title` + `wikidata_qid` (an `INSERT` with old value NULL where the site holds no row of the kind, guarded; its reversal deletes exactly that row by value), and no page, a disambiguation page, a place-level item (`bcases.qid_research.is_site_kind`, the gate of waves 2-3) or an item another curated site carries is listed, not written - a shared item also as a duplicate candidate; a refusal the rule gets wrong is overridden only by a hand-read entry (`WAVE4_HAND_READ`: Petra) that names that refusal and quotes its evidence. 50 rows; migration `0023` may reach the deploy only after this wave is applied |
| `score_search_pilot.py` | scores a search pilot's run directory against the gold standard: the four thresholds sealed in `phase3_runner/SEARCH_PILOT.md`, as sealed, beside them what the writer itself would write, and what each of the writer's three 2026-09-23 rules refuses on its own (`--run-dir`, `--prefix`, `--progress`, `--gold`). `--lane sitelink` scores the sitelink pilot (`phase3_runner/SITELINK_PILOT.md`) against the same four thresholds, threshold 4 counted over its articles (`TRANSPORTS`) |
| `measure_review_holds.py` | measures the writer's period-bucket gate and reviewer contradiction hold on the mass lane's pinned plan, its 72 hand holds and two read-only production exports (written keys, the journal's `period_start` rows); writes the two lists of written rows `HUMAN_ONLY.md` B11 asks about to `logs/review_holds/` (`--out-dir`), nothing else |
| `write_gate4.py` | the Phase-4/5 writer's driver: `--group P4|L|P5 --run <run>`; plans and renders every write batch (dry run by default), `--rehearse` runs each batch's statement ending in `ROLLBACK`, `--apply --step 100` writes one step of at most 100 sites per invocation with preflight, read-back and inverse proof, then stops and prints the `verify_writes4.py` command; `--accept <its output>` records the step's acceptance, and `--apply` refuses to write while the last step has none (`STEP.json`); after a `revert4`, `--close-reverted` closes a step that had no acceptance and `--apply --round 2` writes the reverted batches again, each only on a read-only proof that the round before is reverted (`docs/procedures/PHASE4_CONTRACTS.md` section 7, "After a revert"); prints `WRITE_EXIT=` |

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

## The sitelink lane's runbook (Opus handoff, 2026-09-23)

Every model judgement is answered by Opus agents through the handoff (owner order 2026-09-23, no
DeepSeek any more; `scripts/remediation/opus_handoff.py`): a driver's export writes each question's
exact prompt, the agents answer, `validate` checks every answer, the driver's import reads them.
Nothing else buys a model call. The pilot first; the lane only when `score_search_pilot.py --lane
sitelink` exits 0 - all four thresholds of `phase3_runner/SITELINK_PILOT.md` hold - and that result
is recorded. One ledger for everything (`phase3_runner/LEDGER.jsonl`). A handoff directory is one
round: it is answered only after its export's progress (`progress.export.json`) shows
`"stopped": null` and `"failed": {}`, and an exported question is never replaced - if the evidence
has to change after an export (a target the fetch recorded as failed in `fetch.json`, fetched again
with `run.py fetch --live`), remove the handoff directory before any answer exists and export again.
The pilot's import writes `logs/sitelink_gold/progress.json`, which the scorer reads for threshold 4.
`test_sitelink_plan.py` parses these commands with the drivers' own parsers.

It runs on gitignored state: the plans (`sitelink/pilot/`, `phase3_runner/PLAN.sitelink.jsonl`),
the census snapshot (`snapshot/`: the judge reads its `site_type` list), the run directories and the
handoff directories.

```bash
cd /c/PythonProjects/AncientMap && export PYTHONIOENCODING=utf-8
PY=C:/PythonProjects/AncientMap/.venv/Scripts/python.exe; M=output/remediation; T=$M/tools
P3=scripts/remediation/phase3; OH=scripts/remediation/opus_handoff.py; L=$M/phase3_runner/LEDGER.jsonl

# == the pilot: the sealed plan, batches slkg-0001 and slkg-0002, 39 finder questions
P=$M/sitelink/pilot/PLAN.sitelink-gold.jsonl; R=$M/phase3_runner/runs/sitelink-gold
G=$M/logs/sitelink_gold; HF=$M/handoff/sitelink-gold-finder; HR=$M/handoff/sitelink-gold-reviewer
# 1. plan: the sealed one, never rebuilt for the pilot
sha256sum $P    # d8a78e58f02255570bd6a7c94dd42b0a04fdbddadca440b9bc12e39dabc28b81, or it does not apply
# 2. fetch and 3. finder export: prepare, fetch, then the judge writes its prompts to $HF (no model)
$PY $P3/mass_run.py --live --jobs 2 --plan $P --run-dir $R --ledger $L --log-dir $G \
    --progress $G/progress.export.json --handoff-export $HF
# 4. Opus answers: for each line of $HF/*/MANIFEST.jsonl whose answer_path does not exist, an agent
#    reads $HF/<prompt_path>, writes its answer text (the shape the question asks for) to a file, and
$PY $OH answer --dir $HF --batch-id <batch_id> --stage finder --label <label> \
    --answered-by <agent> --text-file <answer.txt>
# 5. validate: exit 0 only when every question is answered, in shape, by Opus, for its exact prompt
$PY $OH validate --dir $HF
# 6. finder import: the judge on the answers - ledger line first, answers/, model.json
$PY $P3/mass_run.py --live --jobs 2 --plan $P --run-dir $R --ledger $L --log-dir $G \
    --handoff-import $HF
# 7. reviewer export (it asks about the finder's answers)
$PY $T/review_all.py --lane sitelink --run-dir $R --ledger $L --log-dir $M/logs/review_sitelink_gold \
    --handoff-export $HR
# 8. Opus answers, as in 4
$PY $OH answer --dir $HR --batch-id <batch_id> --stage reviewer --label <label> \
    --answered-by <agent> --text-file <answer.txt>
# 9. validate
$PY $OH validate --dir $HR
# 10. reviewer import: each batch's review.json
$PY $T/review_all.py --lane sitelink --run-dir $R --ledger $L --log-dir $M/logs/review_sitelink_gold \
    --handoff-import $HR
# 11. score: exit 0 only when all four sealed thresholds hold; it reads $R and $G/progress.json
$PY $T/score_search_pilot.py --lane sitelink

# == the lane: only after step 11 passed and its result is recorded (SITELINK_PILOT.md, AUDIT_LOG.md)
# 12. plan, rebuilt then: the pins age, and `plan` refuses a sitelinks.json resolved under other inputs
IN="--mass-run $M/phase3_runner/runs/mass --data $M --rows $M/logs/_write_dry/ALL_ROWS.jsonl \
    --written-keys $M/logs/search_lane/written_keys.txt --country-census $M/logs/_country_mismatches.txt"
$PY $T/sitelink_plan.py census --mass-run $M/phase3_runner/runs/mass
$PY $T/sitelink_plan.py export
$PY $T/sitelink_plan.py sitelinks $IN
$PY $T/sitelink_plan.py plan $IN
PL=$M/phase3_runner/PLAN.sitelink.jsonl; RL=$M/phase3_runner/runs/sitelink; GL=$M/logs/sitelink_mass
HLF=$M/handoff/sitelink-finder; HLR=$M/handoff/sitelink-reviewer
# 13.-16. the finder's round, as 2-6
$PY $P3/mass_run.py --live --jobs 4 --plan $PL --run-dir $RL --ledger $L --log-dir $GL \
    --progress $GL/progress.export.json --handoff-export $HLF
$PY $OH answer --dir $HLF --batch-id <batch_id> --stage finder --label <label> \
    --answered-by <agent> --text-file <answer.txt>
$PY $OH validate --dir $HLF
$PY $P3/mass_run.py --live --jobs 4 --plan $PL --run-dir $RL --ledger $L --log-dir $GL \
    --handoff-import $HLF
# 17.-20. the reviewer's round, as 7-10, on the lane's own run (runs/sitelink, logs/review_sitelink)
$PY $T/review_all.py --lane sitelink --ledger $L --handoff-export $HLR
$PY $OH answer --dir $HLR --batch-id <batch_id> --stage reviewer --label <label> \
    --answered-by <agent> --text-file <answer.txt>
$PY $OH validate --dir $HLR
$PY $T/review_all.py --lane sitelink --ledger $L --handoff-import $HLR
# 21. the write plan, no database: logs/_write_dry_sitelink/ALL_ROWS.jsonl
$PY $T/write_dry_all.py --lane sitelink
# 22. write_gate dry ("dry run, nothing is written"): read its refusals, holds and rows before 23
$PY $T/write_gate.py --lane sitelink --step 100
# 23. apply: production, 100-site steps, each read back; a short write or a deviation stops the wave
$PY $T/write_gate.py --lane sitelink --apply --step 100
# 24. the independent acceptance: RESULT: 0 deviation(s)
$PY $T/verify_writes.py --lane sitelink
```

Once the lane is written and accepted, its plan is pinned like the mass lane's
(`lanes.REVIEWED_PLAN_KEYS_SHA256`, "A lane that has written keeps its plan" above).
