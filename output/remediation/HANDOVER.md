# Handover: the 2026-09 remediation of all 5,004 sites

Written 2026-09-22 at the end of the write action, for a session that does not have this one's
context - possibly in another harness. Read this first; `AUDIT_LOG.md` (5,233 lines) carries the
evidence behind every number below, and the plan is `docs/procedures/SITES_DB_REMEDIATION_2026-09.md`.

## 1. The task

Every one of the 5,004 `ancient_nerds` sites in the production database must be **correct** - and
Martin's expanded order of 2026-09-21 added three things to the original plan: the model must
**correct** the content and not merely flag it, it must **research online** and attach **evidence and
sources** to each correction, and everything only a human can do must be listed in one table
(`HUMAN_ONLY.md`).

The plan's own Phase 3 is finder → reviewer → only `refuted = false` is applied, through a
conditional `WHERE` with a journal entry. Only three columns are writable: `country`, `site_type`,
`period_start`. `description` and `card_description` are **report-only** (`model.py`).

## 2. State, measured 2026-09-22

| | |
| --- | --- |
| sites examined | **5,004** (all of them, not the 1,813 worklist) |
| fields judged | 24,255 over 4,852 sites |
| verdicts: correct / wrong / unverifiable | 11,747 / 4,708 / 7,761 (plus 37 with no readable verdict) |
| reviewer over the decided cases | confirmed 2,204 · refuted 2,202 |
| planned writes (writable columns only) | 1,074 rows at 1,022 sites |
| **written to production** | **994 rows at 1,022 sites** - 596 `site_type`, 389 `period_start`, 9 `country` |
| held by hand / stopped by the boundary check | 72 / 8 |
| planned rows deliberately left unchanged | 80 |
| acceptance, both directions | **0 deviations** |
| spend | ~**$31** (finder 25.87 + reviewer 4.65) |

The 7,761 unverifiable fields are a **search** problem, not a model problem: the pipeline has no
search route. Decision (2026-09-22): MiniMax supplies search, the reasoning stays on
`opencode-go/deepseek-v4.1-flash`.

## 3. Where everything lives

**Versioned** (a fresh clone has it):

| path | what |
| --- | --- |
| `scripts/remediation/phase3/*.py` | the runner: `discover_stage`, `fetch_stage`, `model_stage`, `review_stage`, `write_stage`, `mass_run`, `mutation_sweep`, `snapshot_plan` |
| `scripts/remediation/mechanical/` | the deterministic country repairs, with `--rehearse` and `--probe-guards` |
| `output/remediation/AUDIT_LOG.md` | the full record, every number and every adjudicated finding |
| `output/remediation/HUMAN_ONLY.md` | what only Martin can do (German, addressed to him) |
| `output/remediation/HANDOVER.md` | this file |
| `output/remediation/tools/` | the 12 instruments the write was run with - see their README |
| `output/remediation/phase3_runner/PIECE*.md` | the design briefs, including the 100-step write rule (PIECE6 §7) |
| `tests/remediation/` | the gate suite for all of the above |
| `docs/procedures/SITES_DB_REMEDIATION_2026-09.md` | the plan itself |

**Local only** (gitignored, on this machine, and not in a clone):

| path | what | size |
| --- | --- | --- |
| `phase3_runner/runs/mass/batch-*/` | **334 batch directories**, one per five sites: `answers/<site-id>%2F<field>.txt` (38,456 files), `evidence/<site-id>%2F<source>.txt`, `reviews/`, `writes/`, plus `input.json`, `fetch.json`, `model.json`, `review.json` | 195 MB |
| `logs/_write_apply/` | one `ROLLBACK.sql` per written chunk (428 files) and the `APPLIED.json` marker per batch (317) - the undo path | 27 MB |
| `logs/_write_dry/` | the full write plan `ALL_ROWS.jsonl` (1,074 rows) and `ALL_REFUSED.jsonl` (23,946) | 35 MB |
| `logs/` (the rest) | gate and acceptance logs, the hold list, the working copies of the instruments | ~150 MB |
| `phase3_runner/LEDGER.jsonl` | the cost ledger. It is *tracked* and 18 MB, which is worth a look | 18 MB |

Everything here is regenerable at ~$31 and a few hours, which is why it is not in git. To carry the
whole movable state to another machine there is one archive, made for exactly that:

    output/remediation/run-2026-09-22-complete.tgz     # 34 MB, 49,470 entries
    # tar -czf run-2026-09-22-complete.tgz -C output/remediation phase3_runner/runs \
    #     logs/_write_apply logs/_write_dry logs/_country_mismatches.txt logs/review_totals.txt

The **results** of the write are durable in production regardless: every one of the 994 rows has a
`remediation_change_log` row with old and new value, so the undo path is reconstructible from the
database even without those files.

## 4. How to run it

```bash
cd /c/PythonProjects/AncientMap
export PYTHONIOENCODING=utf-8
export PYTHONPATH="C:/PythonProjects/AncientMap;C:/PythonProjects/AncientMap/scripts/remediation"

# the gate suite - DB-less, and the only definition of "green" (2026-09-22: 2467 passed, 3 skipped)
./.venv/Scripts/python.exe -m pytest -q -rs --timeout 90 -m "not integration and not live_llm"

# the writer: dry first (it prints "Probelauf, es wird nichts geschrieben"), then for real
./.venv/Scripts/python.exe output/remediation/logs/write_gate.py --step 100
./.venv/Scripts/python.exe output/remediation/logs/write_gate.py --apply --step 100

# the independent acceptance - asks the database in both directions
./.venv/Scripts/python.exe output/remediation/logs/verify_writes.py

# a read-only database question (there is no local database; production is the one that counts)
ssh ancientnerds "docker exec -i ancient_nerds_db psql -U ancient_map -d ancient_map \
  -v ON_ERROR_STOP=1 -t -A -F '|'" < some.sql
```

The mass run's own driver is `scripts/remediation/phase3/mass_run.py`; it hashes the phase-3 sources
before every batch, which is why nothing under `phase3/` may be edited while it runs.

## 5. Decisions already taken (do not re-open without Martin)

1. The 72 rows held by hand stay held - the proposals were not proven.
2. The United Kingdom's parts are spelled by region: **`Northern Ireland`**, not `United Kingdom`.
3. The 4 rows refused as "not writable in the columns' shape" are not written.
4. The 29 geopolitical census rows are left as they are.
5. Deploy only after all 5,004 are through - **that condition is now met**.
6. The search route (A3) is **MiniMax** - search service only, reasoning stays on deepseek.
7. B7/B8/B9/B10 are decided (2026-09-21); see `HUMAN_ONLY.md`.
8. Never push to `main` from an agent session: a push is a live deploy, and `.githooks/pre-push`
   aborts anyway when the working tree differs from the pushed commit.

## 6. Open work

- **`Northern Ireland` (5 rows).** Five written rows say `United Kingdom` - factually right, and the
  boundary check accepts it, but not the decided spelling. The route is **not** the discover prompt:
  it is frozen at round 5's wording and a second wording would mix two conventions into one answer
  store. The right home is the **mechanical lane** (`scripts/remediation/mechanical/`), which
  rehearses its statement against production and can be shown to fail.
- **The MiniMax search route.** No search route exists in the pipeline today. This is the lever for
  the 7,761 unverifiable fields.
- Remaining strands, all recorded: the 6th `P3/scope` question, the third evidence route
  (`unified_sites.source_url`), `[H] SECURITY 3 / BACKEND B7`, the mypy `api/` debt, Phase 4-6
  (22 Irish rows + the 83-census worklist), the final adversarial self-audit.
- `HUMAN_ONLY.md` holds everything that needs Martin: the push (104 commits, local only), the export
  of the corrected data to the globe, and the (site, field) questions.

## 7. Traps that cost real time here

- **A pipeline's exit status is its last command's.** Always read the log's own
  `GATE_EXIT=` / `WRITE_EXIT=` / `DRIVER_EXIT=` / `REVIEW_EXIT=` / `PYTEST_EXIT=` line. A background
  wrapper's exit-code 0 is not the run's exit code.
- **A dry run is not a write, and it is the cheapest proof.** `write_gate.py` without `--apply`
  writes nothing and still measures the whole plan against production.
- **A write that "failed" may have written nothing.** Prove it: re-run the dry gate and compare the
  numbers. That is how the cp1252 crash below was shown to have left the database untouched.
- **Encoding.** A console that cannot encode a site name killed a whole wave on a `print` **before**
  the first row, because `PYTHONIOENCODING=utf-8` was missing from a background launch. The gate now
  reconfigures its own streams.
- **The `.env` file is policy-protected.** Never read it; establish a credential's presence
  functionally. `LyraSettings` reads it at runtime - that is the pipeline's business, not the agent's.
- **`matched_0` is the load-bearing number of a write.** If a planned row no longer holds the old
  value the plan assumed, the write must affect 0 rows - not "close enough".
- **The journal table is project-wide.** `remediation_change_log` carries rows from other phases
  (`is_hero` 5,438, `image_kind` 105, `mechanical-country` 35); this action's rows are stamped
  `phase3:batch-…`. Never present the table's total as this action's count.
- **Never point the integration tests at production.** They INSERT test rows into `unified_sites`.
- **Never weaken a check to make it green**, and never edit a test to match prose - if a test really
  encodes a superseded defect, rewrite it strictly stronger and say why.
- **Do not trust `comm`/`sort` across Linux and Windows** without fixed collation, and remember a
  Windows Python writing `/tmp/x.sql` writes `C:\tmp\x.sql`, not Git Bash's `/tmp`.
- **Commit messages and apostrophes.** A message written through a Python single-quoted triple
  string makes the apostrophe awkward, and rather than escape it I wrote around it - which is how
  three commit messages in this action came out as "the file is own numbers". Escape it, or use a
  double-quoted string.

## 8. Portability to another harness

- The **write path is harness-independent**: conditional `WHERE`, journal row, `ROLLBACK.sql`,
  read-back, and an acceptance that re-reads the database. It was proven on production.
- The **model stages are not**: `model_stage.py` spawns `pi -p --mode json` (`pi.cmd` on Windows).
  Running the finder/reviewer under Claude Code needs an adapter that produces the same answer files
  and the same `model.json` shape - or a re-run under Pi.
- **The cost difference is measured, not guessed**: the same token volume on a Claude model came out
  about 68x the DeepSeek price (18,610 judgements: DeepSeek $17.07, the Claude comparison $1,156).
  The harness is not what made this cheap; the model and the narrow context did.
- Everything an agent writes down is **English**; `HUMAN_ONLY.md` and the chat stay German because
  Martin reads exactly those.

### What a foreign machine does not get from this repository

| needed | where it lives | who can supply it |
| --- | --- | --- |
| the 107 commits | local only, never pushed | Martin - a push to `main` is a live deploy, so it is his call |
| the run state (195 MB) and the undo path | `output/remediation/run-2026-09-22-complete.tgz`, 34 MB | copy the file, then see the tools README for the restore order |
| the SSH alias `ancientnerds` | the user's SSH config, outside the repo | Martin, or use the VPS address directly |
| the database credentials | `.env`, policy-protected - never read it, establish a credential's presence functionally | Martin |
| the Python environment | `.venv/` locally; the repo carries the `requirements*.txt` | rebuild it |
| the Pi CLI | only the model stages need it (`pi -p --mode json`) | install Pi, or write the adapter |

Everything else - the code, the plan, the audit, the instruments, the tests - is in git.
