# The instruments of the 2026-09 remediation

These are the scripts the write action was actually run with, copied here out of
`output/remediation/logs/` (which is scratch and not versioned) so that a fresh clone has them.
They are working code, not a library: no package, no tests of their own, each one a
`python <file>` entry point.

**They locate their data relative to their own path** (`Path(__file__).resolve().parent`), and that
data - `_write_dry/`, `_write_apply/`, `phase3_runner/runs/` - lives in `output/remediation/logs/`.
Run them from there, not from here. A fresh clone has no such directory - the archive named in
`../HANDOVER.md` restores it - so restore the data first and then put the scripts beside it:

    tar -xzf output/remediation/run-2026-09-22-complete.tgz -C output/remediation
    mkdir -p output/remediation/logs
    cp output/remediation/tools/*.py output/remediation/logs/

| script | what it does |
| --- | --- |
| `write_dry_all.py` | builds the full write plan over every batch (`_write_dry/ALL_ROWS.jsonl`); touches no database |
| `make_holds.py` | writes the hand-hold list (`_write_apply/HOLDS.jsonl`), keyed by `change_key`; must be re-run after every edit |
| `write_gate.py` | the writer: 100-site steps, conditional `WHERE`, journal row, read-back. Without `--apply` it is a dry run and says so |
| `verify_writes.py` | the independent acceptance: asks production in both directions, prints `ERGEBNIS:` |
| `review_all.py` | drives the reviewer stage over every batch (4 workers, $8 cap) |
| `review_totals.py` | the reviewer census (`review_totals.txt`) |
| `found_summary.py` | the finder census over the answer files |
| `country_census.py`, `country_probe.py` | the country/boundary census (258 polygons, 96 spellings) |
| `scan_rows.py`, `show_rows.py` | find and inspect rows in the plan |
| `batch_summary.py` | per-batch counts |

Each needs `PYTHONIOENCODING=utf-8`, and the writer needs `PYTHONPATH` to include the repo root and
`scripts/remediation` for the subprocess it starts. A console encoding once killed a whole write
wave on a `print` before the first row; that is why the gate now reconfigures its own streams.
