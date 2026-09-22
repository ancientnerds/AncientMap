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
(lanes, the chain acceptance, the stale-plan guard). Run these, or copy them over the old ones -
`lanes.py` has to travel with them.

## Lanes

Every write/acceptance tool takes `--lane` (default `mass`). A lane names the run directory, the dry
plan, the apply markers, the hold list, the reviewer logs and the journal stamp pattern at once, so one
run can never be read as another's (`lanes.py` has the table). The gap run is `--lane gap`:
`runs/gap`, `logs/_write_dry_gap/`, `logs/_write_apply_gap/`, stamps `phase3:gap-%`. Individual paths
can still be overridden (`--run-dir`, `--out`, `--rows`, `--apply-root`, `--hold`, `--stamp-like`).

| script | what it does |
| --- | --- |
| `lanes.py` | the lanes' paths and the one JSON-lines reader; no entry point |
| `write_dry_all.py` | builds the full write plan over every reviewed batch of a lane (`ALL_ROWS.jsonl`); touches no database |
| `make_holds.py` | writes the mass lane's hand-hold list (`_write_apply/HOLDS.jsonl`), keyed by `change_key`; refuses a rows file whose line order is not the one its line numbers were read against |
| `write_gate.py` | the writer: 100-site steps, conditional `WHERE`, journal row, read-back. Without `--apply` it is a dry run and says so. Refuses rows of another run and a rows file that is not the writer's plan today |
| `verify_writes.py` | the independent acceptance: asks production in both directions, follows the journal chain, prints `ERGEBNIS:` |
| `review_all.py` | drives the reviewer stage over every batch of a lane (4 workers, $8 cap on this pass's own spend) |
| `review_totals.py` | the reviewer census (`review_totals.txt`) |
| `found_summary.py` | the finder census over the model reports |
| `country_census.py`, `country_probe.py` | the country/boundary census (258 polygons, 96 spellings) |
| `scan_rows.py`, `show_rows.py` | find and inspect rows in the plan |
| `batch_summary.py` | per-batch counts |
| `gap_plan.py` | builds `PLAN.gap.jsonl` for the fields the mass run never judged, from a fresh read-only production export |
| `qid_repair.py` | renders the reviewed `site_external_ids` repair (`output/remediation/qid_repair/`) - plan, apply, rehearsal, rollback; applies nothing |

Each needs `PYTHONIOENCODING=utf-8`. The writer's child processes get the repository root and
`scripts/remediation` on their `PYTHONPATH` from `write_dry_all.writer_env()`, and they run under the
interpreter the tool was started with (`sys.executable`) - start the tools with the repo venv. A
console encoding once killed a whole write wave on a `print` before the first row; that is why the
gate reconfigures its own streams.
