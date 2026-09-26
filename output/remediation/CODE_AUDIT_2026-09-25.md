# Audit Report - backend (narrowed to the remediation) - 2026-09-25

**COMPLETE (2026-09-26).** Steps 0.5-5 were done at `4c8831a` (report `6e5d028`, then PAUSED). Steps
6-8 ran on branch `wip/audit-fix` (worktree `.claude/worktrees/audit-fix`, from `integrate/wave1` at
`0e821fc`), never in the main checkout: the acceptance judges import `prod_write` and
`mechanical.lane` there. **Final state: every Major and Minor finding is fixed except the three
MANUAL items; the quality gate passes (only Info and MANUAL remain) after one fix iteration and a
confirming audit.** The branch reaches the main checkout only by the orchestrator's merge, after the
running acceptance: it changes `prod_write.send`, `lane.sql_literal`, `plan.parse_tagged_export` and
`persist_verdicts.jsonl_lines`, which the judges import (their behaviour on today's data is the
same: LF-only SQL, no NUL, no U+2028 on production). The original findings below are kept as found;
the result is in "Result (Steps 6-8)" at the end.

## Scope and method

* **Deep review, 14 files** (`git diff --name-only 8a957b4 HEAD -- api pipeline`): `api/cache.py`,
  `api/routes/{founders_stats,radar,sites,stats_access}.py`, `api/services/lyra_tools.py`,
  `pipeline/lyra/{handlers/judge,quality_gate,site_identifier}.py`, `pipeline/static_exporter.py`,
  `pipeline/{stats_analysis,umami_db}.py`, `pipeline/utils/{country_lookup,globe_payload}.py`.
  Reviewed by the auditor, diff-first, with the whole file read around every hunk.
* **D1/D2/D6 review of the production-writing tooling**: `scripts/remediation/mechanical/{apply,lane,
  reversal,reversal_3_list,reversal_opus,wrong_both,citations,dangling_markers,scope,card_stats}.py`,
  `scripts/remediation/phase4/{write4,revert4,card_json,legacy4,scope4}.py`,
  `output/remediation/tools/{write_gate4,verify_writes4}.py`, `scripts/remediation/prod_write.py`.
  Five read-only reviewers read them in full. Each finding below says whether the auditor
  re-verified it against the code (**verified**) or not yet (**reported**).
* **Excluded as instructed** (the acceptance judges are running): `scripts/remediation/acceptance/**`,
  `opus_handoff.py`, `phase3/fetch_stage.py`, `phase3/ledger.py`, `output/remediation/{acceptance,
  handoff}/`. No finding fell in them.
* **Production**: read-only SELECTs only (below). No model API was called and nothing was pushed.

## Step 0.5 - files not in the Key Files table (INFO, D7-DOC)

`api/routes/founders_stats.py`, `api/routes/stats_access.py`, `pipeline/lyra/quality_gate.py`,
`pipeline/stats_analysis.py`, `pipeline/umami_db.py`, `pipeline/utils/country_lookup.py`,
`pipeline/utils/globe_payload.py` (new). Add them to the table in `docs/procedures/CODE_AUDIT.md`.

## Step 1 / 1.5 - mechanical scans and the contract check

* The scans on the 14 files found no eval/exec, no `utcnow()`, no bare `except:`, no secrets, no
  `shell=True` and no `.format()` SQL. The f-string SQL hits were checked: `sites.py:2068/2089` splice
  a table name from a closed list (pre-existing); `site_identifier.py:1723` splices only
  `site_key_sql(':name')`, a constant template around bind parameters. Every ILIKE uses
  `_escape_ilike`, and every `CAST(... AS uuid)` takes a bound, server-validated id.
* **P9**: `GET /api/sites/all` gained `fields: Literal["all","globe"] = "all"`, and `limit` is
  unchanged. The frontend callers (`DataStore.ts`, `DownloadManager.tsx`) send either no `fields`
  or `fields=globe`, so the contract is preserved.

## Gate measurements (baseline at 4c8831a, before any fix)

| Gate | Result |
|---|---|
| `pytest -q -rs --timeout 300 -m "not integration and not live_llm"` | 7164 passed, 4 skipped, 57 deselected (234 s) |
| `ruff check api/ pipeline/` (0.15.11) | clean |
| `ruff format --check` on the 14 files | clean |
| `lint-imports` | 2 kept, 0 broken |
| `vulture api/ pipeline/ .vulture_whitelist.py --min-confidence 80` | clean |
| `mypy api/ --no-error-summary`, CI-equivalent (mypy-only venv `C:/tmp/mypyci`, as CI installs no deps) | clean |
| same in the repo venv (all deps installed; not what CI runs) | 93 errors, all pre-existing, none in the diff's lines (HANDOVER "mypy api/ debt (A7)") |
| `semgrep scan --config .semgrep api/ pipeline/` | 0 findings |
| Lyra import check (`markdown`/`nh3` absent) | OK |

**Read-only production checks (2026-09-25):**
* 0 CR and 0 LF in curated `description`s, 0 CR in `card_stats.card_description`, and 0 CR / 0 LF
  in any of the 19,200 journal `old_value`/`new_value` rows. So the Windows CRLF translation (M2)
  has not written anything yet.
* 0 U+2028 / U+2029 / U+0085 in curated `name`, `description` or `raw_data` or in card texts. So the
  `splitlines()` readers (m9) would not break on today's data.

## Quality gate (provisional - Step 4)

| Condition | Result |
|---|---|
| Critical findings = 0 | PASS (the reviewer's one "Critical" is re-graded Major: M1) |
| Major security findings (D2) = 0 | PASS |
| Hardcoded secrets = 0 | PASS |
| New anti-patterns (P1-P14) = 0 | PASS (the name-key residual M10 is pre-existing, see there) |
| Deprecated API usage (P6) = 0 | PASS |
| No eval/exec on external data | PASS |
| API contract preserved (P9) | PASS |
| DB schema compatible (P10) | PASS (no schema change in scope) |
| JWT signing key enforced | PASS (`mint_stats_token` refuses an empty secret) |
| LLM prompt guards, Docker pins, credit/OAuth/webhook/tier | not in scope (no such file changed) |

This was the provisional gate of Step 4; the final gate is at the end ("Quality gate (final)").

## Findings

### Backend (the 14 files) - reviewed by the auditor

Every change reads as correct. The checks behind that:
* `/sites/all`: `json.dumps` sees only JSON-native types (Float columns, isoformat timestamps,
  JSONB). The raw gzip response agrees with Starlette 0.50's GZipMiddleware (it passes a
  `Content-Encoding` response through, and `Vary` is set explicitly). `sites:*` invalidation still
  matches the `:f=` keys.
* The radar UNION rewrite gives one row per (card, news item), so the non-distinct aggregates
  (`jsonb_agg(facts)`, `AVG`, `MODE`) are unchanged.
* The Qdrant retired-site filter casts only UUID point ids.
* The alias INSERT works as written: SQLAlchemy's psycopg2 dialect calls `register_uuid`, and
  `uq_usn` exists.
* `recompute_quality_passed`: the judge always stores a populated `audit_gate_failures`.
* `globe_funnel`: `sum(not_reached) == gave_up` holds.
* The static-export preflight covers every writer.
* The country tables are consistent with `NAME_TO_ISO` (checked programmatically).

* **[MAJOR] M10 D1 - Python-keyed `name_normalized` comparisons and writes** (pre-existing, in the
  changed file `pipeline/lyra/site_identifier.py`). `_check_name_an_match` (1665-1700) and
  `_promote_to_unified_sites` (2500-2575) compare, and write, `normalize_name()` against a column
  Postgres keys as `left(lower(unaccent(name)),500)`. The same residual exists in the `radar.py`
  alias merge and the `sites.py` batch upload. AUDIT_LOG (name-key item) lists these as "not changed
  here". The boot's alias UPDATE never recomputes a key from `name`, so promotion-written alias keys
  stay divergent. **ACTION: MANUAL** - the write paths need a production rehearsal (ROLLBACK), which
  this audit may not run. The read-only `_check_name_an_match` part is fixable here.
* [INFO] `stats_access.py`: the stats session is now 30 days (owner decision). The Founder role is
  only checked at the handoff, so a revoked founder keeps access until expiry.
* [INFO] `static_exporter._writable` uses `os.access`, which checks the *real* uid; its docstring
  says "effective user".
* [INFO] `SQL_GLOBE` adds two full-history scans of `website_event` (`first_ending`, `measured`):
  "one query" is not "one scan". Founder-only dashboard.
* [INFO] `sites.py` `_build_sites_payload` is ~165 lines (moved, not new): D3 backlog.
  `"gzip" in accept-encoding` ignores `q=0`, the same as Starlette.

### Tooling - Major

* **M1 D1 `write_gate4.py:592-597` `acceptance_problems` fails open on a concatenated log**
  (verified). It needs only one lane line, `RESULT: 0 deviation(s)` *anywhere*, and a last line of
  `ACCEPT_EXIT=0`. A `--lane` run with deviations and `ACCEPT_EXIT=1`, followed by an appended
  `--boot-logs` run, is accepted. Fix: exactly one `RESULT:` and one `*_EXIT=` line; the result is
  `lines[-2]`; the lane line comes first. (Reviewer graded it Critical; re-graded Major because it
  needs an operator to append two runs.)
* **M2 D1 `prod_write.py:48-55` `send()` and `phase3/write_stage.py:328-335` `run_sql()`: CRLF on
  Windows** (mechanism verified, 0 production damage). `text=True` writes stdin through a
  TextIOWrapper, which turns `\n` into `\r\n`. Any multi-line literal would be stored with CR, and
  every guard, rehearsal and read-back sends the same translated literal, so none would notice.
  Fix: send `sql.encode("utf-8")` without `text=True` and decode stdout/stderr; make
  `write_stage.run_sql` delegate to `prod_write.send` (this also removes the duplicated
  `PSQL`/`SSH_HOST` constants and adds the channel timeouts). The test is a real local child that
  echoes its stdin as hex. Three test fakes must return bytes (`test_prod_write.py` x2,
  `test_image_chunk_writer.py:1005`).
* **M3 D1 timeouts in the phase-4 tools** (verified). A timeout in `run_sql` raises a raw
  `TimeoutExpired`, and `write4.exit_line` and `write_gate4.run_batches` catch only
  `SystemExit`/`WriteRefused`. The result is no `STOPPED.json` and no `WRITE_EXIT=` line. Data stays
  safe (the next preflight reads the stamp). Fix: with M2 a timeout arrives as `OutcomeUnknown`;
  `run_batches` marks `STOPPED.json` `{"outcome": "unknown"}`, and `exit_line` prints
  `WRITE_EXIT=5` (the same code as `apply.EXIT_UNKNOWN`).
* **M4 D1 `write_gate4.py:677` `--batch` skips a stopped batch** (verified). Only the selected
  batches are checked for `STOPPED.json`. Fix: check `apply_root.glob("*/STOPPED.json")` always.
* **M5 D1 `write_gate4.py:797` `--step` has no upper bound** (verified). The owner's "after every
  hundred, a check" can be bypassed with `--step 5000`. Fix: refuse `--step` > 100.
* **M6 D1 `phase4/write4.py:1009` P5 clears (or keeps the March card) while the live provenance
  names card X** (verified). This happens after a card-scope hold added once P4 had written. Fix,
  plan-side only (the render stays pinned): refuse the site in `plan_cards` when
  `written.get(site)` is not None and `card_to_write` returned None ("revert the site first").
  This matters for the Phase-5 sitting.
* **M7 D1 `mechanical/wrong_both.py:296` `_PREFIX` has no right boundary** (verified by probe).
  `AD 5th century` reads as year 5; so do `AD 90s`, `AD 1.500` and `AD 900.5`. The four applied
  period corrections all use the year-then-era form. Fix: append `(?![^\W_]|[.,]\d)`.
* **M8 D1 `mechanical/scope.py:470` a loser found with two survivors keeps whichever pair came
  last** (verified). In a triangle the outcome depends on pair order. Fix: refuse such a loser as
  `survivors-disagree`, the rule that already covers found-vs-listed conflicts.
* **M9 D1 `mechanical/apply.py` (`cmd_apply` after COMMIT, `_value_rows`) exits 1 = REFUSED for a
  committed write** (verified). `verify_interests` reads through `read_rows`, which splits on `|`;
  a curated value containing `|` or a newline raises an uncaught ValueError. That breaks the
  docstring's "never as a refusal". Fix: read `_value_rows` as JSON (`psql_json_reader`), like
  `_cell_value_rows` does.
* **E5 D1 `verify_writes4.py:261-282` + `write_gate4.py:371-376` a round-2 re-write whose plan
  changed can never be accepted** (reported, partly read). It fails closed, but it blocks the
  documented round-2 flow after `audit4 hold` + `revert4 --site`. Fix: keep each archived round's
  `PLAN.jsonl` and judge its reverted links against it.
* **C3 D1 scope premise lacks `site_external_ids.wikidata_qid`** (reported). **ACTION: MANUAL** -
  changing `SCOPE.premise_sql` re-renders the applied `scope-e4` statements and breaks their
  pinned rollback. Do it with the next scope wave and a re-export.

### Tooling - Minor (all to be fixed test-first unless marked)

* m1 `apply.py:1351` `--apply` does not re-verify the pinned `ROLLBACK.sql` (reported).
* m2 `apply.py:1067/1309` the rehearsal `startswith(head)` check is a tautology; refuse unless there
  is exactly one `\nCOMMIT;\n` (reported).
* m3 `lane.py:78` `sql_literal` passes NUL: psql's line reader truncates at NUL and flips quote
  parity (reported). Refuse `\x00` only; newlines are legitimate.
* m4 `lane.py` `Lane.__post_init__`: nothing refuses `$$` in the values spliced inside `DO $$`
  (source, test_id, run_stamp, confidence, owned values, `premise_sql`). Every constant is clean
  today (reported).
* m5 dead code: `apply.py:127-138` `DEFAULT_PLAN`, `DEFAULT_OUT`, `change_key()` and
  `rollback_change_key()`; `card_stats.py:801` `CardStatsPlan.changed_sites`; `write4.py:76` unused
  `quote` import, `write4.py:177` `RULE_NOT_WRITTEN`, `write4.py:494` `WritePlan4.site_ids`
  (reported, grep-confirmed by the reviewers).
* m6 `reversal.py:147` an empty quote text passes every evidence check (verified).
* m7 `dangling_markers.py:239/354` `premise_of` crashes with AttributeError on a non-dict
  provenance, which makes the later non-dict branch unreachable (verified).
* m8 `citations.py:210` `premise_of` is test-only, and `classify` never checks the export's premise
  against the description (verified).
* m9 `splitlines()` in the psql readers (`plan.py:1376, 1427`, `write_stage.py:377`) also splits on
  U+2028/2029/0085, which Postgres JSON does not escape. It fails closed; 0 such characters on
  production today. Use `split("\n")`.
* m10 `wrong_both.py:551` `else:` treats any column as country; use `elif COUNTRY` and refuse the
  rest (verified).
* m11 `scope.py:36-39` vs 640: an undated Museum without a decision is planned `pending`, not
  refused as the docstring says (verified).
* m12 D7 docstring drift: `scope.py:42` ("two decisions refused"; the code refuses only the
  duplicate) and `reversal.py:607` `keep_the_period_label` (verified).
* m13 `plan.UUID_RE` and the lane validators use `^...$` with `.match`, which accepts a trailing
  newline; a held pair id could then silently not match (reported).
* m14 `write_gate4.render` rewrites a STOPPED batch's plan and statements (reported).
* m15 `verify_writes4.py:240` a row planned twice is silently accepted (verified).
* m16 `verify_writes4` acceptance: the planned-row count and the `--allow-stamp` patterns are not
  tied to the step (reported).
* m17 `verify_writes4.py:679` the card-file check ignores the exit status and accepts any
  `*_EXIT=` tag (reported).
* m18 `verify_writes4.py:781` duplicates `write_stage.utf8_streams`, and `:381` hard-codes
  `'_description_provenance'` (reported).
* m19 `revert4` has no cross-family check: reverting `phase4:` leaves a live `phase5:` card without
  provenance (reported).
* m20 `write4.holds_value` compares raw_data as floats while guard 4 compares jsonb exactly. It
  fails closed but aborts the whole chunk (reported).
* m21 `write4.plan_cards` has no `card_stats` row check, so one site blocks its whole P5 batch
  (fails closed; reported). Needs the S0 export to carry the flag.
* m22 P2 duplicated quoting helper: `write_stage._sql_text` = `lane.sql_literal`. Plan: one
  `sql_literal` in `prod_write.py`, re-exported by both, with m3's NUL refusal (reported).

### Tooling - Info

* The invariant-2 comment ("both directions", `apply.py:716`) sits inside the sha256-pinned render.
  Correcting it would re-pin every lane and invalidate the on-disk `ROLLBACK.sql` verification. The
  other direction is covered by `moved = expected` plus apply-once.
* `named_values` (wrong_both) does not check that a counted revert names the written value. The
  sealed RULES.md decides this; 0 of 42 cases today.
* Zero-change plans raise after `PLAN.jsonl` is written (scope, citations, reversal, wrong_both); a
  stale `ROLLBACK.sql` is refused by `verify_pinned`.
* `--host` is not validated against a leading `-` (`prod_write`, `write_stage`, `verify_writes4`).
* `commit_state` looks at the run stamp only (concurrent applies); `_text` turns non-string JSON
  into its repr; `reversal_metrics` uses `str(i)`, not `int(i)`.
* `legacy4` treats `""` like a description; `scope4` accepts non-canonical UUIDs (fails closed);
  `card_json` argparse abbreviations; `apply_chunk` pins the header, not the body; `hero_repair`
  maps a non-zero exit to a plain failure (legacy lane).

### Outside the repository - ACTION: MANUAL

* `C:\Users\marti\AppData\Local\Temp\gettext.py` (736 bytes, 2026-09-23, a URL fetcher) shadows
  Python's standard `gettext` for any interpreter started with `%TEMP%` as its working directory.
  A reviewer's vulture run from `/tmp` executed it. Delete or rename it.

## Result (Steps 6-8)

Done in the planned order (M2+M3, M1, M4, M5, M6, M7, M8, M9, E5, then the Minors), each fix with a
failing test first and a mutation case (labels `audit-fix:` in both sweeps), swept in the worktree.

### Fixed (one line each)

* **M1** `write_gate4 --accept` takes only one whole clean run: lane line first, exactly one
  `RESULT:` and one exit line, the clean result right before `ACCEPT_EXIT=0` (`254ac43`).
* **M2** `prod_write.send` sends UTF-8 bytes, no text-mode pipe (the Windows LF -> CR LF is gone);
  `write_stage.run_sql` delegates to it: channel timeouts, one `PSQL`/`SSH_HOST` (`f420f71`).
* **M3** a psql timeout is `OutcomeUnknown` everywhere: `run_batches` marks `STOPPED.json`
  `{"outcome": "unknown"}`, `write4.exit_line` prints `WRITE_EXIT=5` (`f420f71`).
* **M4** every `STOPPED.json` of the apply root stops a run, whatever `--batch` selects (`2f631ae`).
* **M5** `--step` is 1-100 (`STEP_MAX`) (`2f631ae`).
* **M6** P5 refuses a site whose live provenance names a card P5 will not write
  (`live-provenance-names-an-unwritten-card`: revert it first) (`795ef56`).
* **M7** wrong_both's `AD <year>` has a right boundary: `AD 5th century`, `AD 90s`, `AD 1.500`,
  `AD 900.5` read as no year (`3a36594`; the applied plan holds no prefix-form quote).
* **M8** a scope loser found with two survivors is refused `survivors-disagree`, in any pair order
  (`8dc7832`).
* **M9** `apply._value_rows` reads JSON, so a `|` or a newline in a value no longer turns a
  committed write into exit 1 (`b0d0d64`; the read-only `interests` digest re-pinned, no write,
  undo, rehearsal or probe digest moved).
* **M10 (read part)** `site_identifier._check_name_an_match` keys in Postgres through
  `site_matcher._match_site_ids` (`89653b1`).
* **E5** a reverted round keeps its `PLAN.jsonl`, the lane plan carries its rows tagged
  `round_stamp`, and `verify_writes4` judges each reverted link against its own round (`18a5562`).
* **m1** `--apply` re-verifies the pinned `ROLLBACK.sql`; **m2** a rehearsal needs exactly one
  `COMMIT` line, the tautological `startswith` check is gone (`2301167`).
* **m3 + m22** one `prod_write.sql_literal`, refusing NUL; `lane` re-exports it and
  `write_stage._sql_text` is it (`86c666e`).
* **m4** a spliced `$$` that would end the `DO` block is refused, checked on the rendered block
  (`13e3715`).
* **m5** the dead code is gone: `apply.DEFAULT_PLAN`, `DEFAULT_OUT`, `change_key`,
  `rollback_change_key`; `CardStatsPlan.changed_sites`; write4's `quote` import,
  `RULE_NOT_WRITTEN`, `WritePlan4.site_ids` (`7590ded`).
* **m6** a reversal quote without text is no evidence (`3523e6c`).
* **m7** `dangling_markers.premise_of` mirrors `jsonb - text` for a non-object provenance
  (`64792e8`).
* **m8** `citations.classify` checks the export's premise against its description (`8cda900`).
* **m9** every psql JSON reader splits at LF only (`prod_write.jsonl_lines`, moved from
  `persist_verdicts`, which re-exports it) (`7401c67`).
* **m10** wrong_both refuses a column that is not the country instead of treating it as one
  (`2f4e0dc`).
* **m11** an undated Museum without a decision is refused, not planned `pending`; **m12** the two
  docstrings say what the code does (`43d4de8`; the applied scope plan holds no such row).
* **m13** the mechanical validators anchor with `\Z`, not `$` (`1a045ee`).
* **m14** a STOPPED batch is left exactly as it stopped (`eeba7e5`).
* **m15** a row the lane plan names twice is a `PLANNED TWICE` deviation (`96a9d8a`).
* **m16** `--accept` compares the lane line's planned rows with the lane plan and refuses an
  `--allow-stamp` pattern that covers the step's own stamps (`8c9b63d`).
* **m17** the card-file check needs exit status 0 and exactly one `ACCEPT_EXIT=0` (`088bb04`).
* **m18** `verify_writes4` uses `write_stage.utf8_streams` and `model4.PROVENANCE_KEY`; the live
  read renders byte-identical (`fa4c2c3`).
* **m19** `revert4` refuses a site's `phase4:` rows while its `phase5:` card is live (`aa8c3b2`;
  the reviewed `P5_REVERT` pin carries the new guard).
* **m20** the P4 preflight compares raw_data numbers as jsonb does, as exact decimals (`8cbabff`).
* **m21** P5 refuses a site without a card_stats row in the plan (read-only `card_row_sites`), so
  it no longer blocks its whole batch (`1a5c1a4`).
* **Step 0.5 (Info, D7-DOC)** the seven files are in the Key Files table (`9f639c3`).

### Remaining findings

* **[MAJOR] M10 D1, write part - ACTION: MANUAL.** `_promote_to_unified_sites`, the `radar.py`
  alias merge, the `sites.py` batch upload and the boot's alias UPDATE still write or compare a
  Python-keyed `name_normalized`. A write path needs a production rehearsal ending in ROLLBACK
  against the live keys, which this audit may not run.
* **[MAJOR] C3 D1 - ACTION: MANUAL.** The scope premise lacks `site_external_ids.wikidata_qid`;
  changing `SCOPE.premise_sql` re-renders the applied `scope-e4` statements and breaks their pinned
  rollback. With the next scope wave and a re-export.
* **Outside the repository - ACTION: MANUAL (owner).** `%TEMP%\gettext.py` (above).
* The Info items above stand (Step 6 skips Info).
* No finding fell in `scripts/remediation/acceptance/**` or `opus_handoff.py`, so nothing waits
  "after the acceptance" there.

### Confirming audit (Step 7) and the loop (Step 8)

* **Scope**: the same 14 backend files and the production-writing tooling, plus every file the
  branch changed (`git diff --name-only 0e821fc HEAD`).
* **Step 1** on the diff: no eval/exec, `utcnow()`, bare `except:`, `shell=True`, `.format()` SQL
  or secrets. The new SQL splices only constants and quoted values (`write_gate4.card_rows_sql`,
  `revert4.card_left_live`, `verify_writes4.live_sql`, byte-identical to before).
* **Step 2**: every changed function re-read; no new finding. The first confirming pass's suite
  found two phase-3 sweep anchors the fixes had moved (`p4 model: NaN is read as JSON`,
  `p4 write_gate4: a reverted round's statements are dropped`); re-anchored and swept, both caught
  (`7321676`). The second pass is clean: 2 iterations of the 3 allowed.
* **Steps 3-4**: no Critical, no open Major or Minor outside MANUAL.

### Quality gate (final)

| Condition | Result |
|---|---|
| Critical findings = 0 | PASS |
| Major security findings (D2) = 0 | PASS |
| Hardcoded secrets = 0 | PASS (gitleaks over the branch's commits: no leaks) |
| New anti-patterns (P1-P14) = 0 | PASS (M10's write part is pre-existing and MANUAL) |
| Deprecated API usage (P6) = 0 | PASS |
| No eval/exec on external data | PASS |
| API contract preserved (P9) | PASS (no endpoint changed) |
| DB schema compatible (P10) | PASS (no schema change) |
| JWT signing key enforced | PASS |
| Only Info or MANUAL findings remain | PASS |

### Gates (2026-09-26, in the worktree at the branch head)

| Gate | Result |
|---|---|
| `pytest -q -rs --timeout 300 -m "not integration and not live_llm"` | 7148 passed, 75 skipped, 57 deselected (261 s). Every skip is gitignored data a worktree lacks (Natural Earth map units, the production snapshot, the phase-3 worklist, bcases cache); the main checkout's baseline was 7164 passed, 4 skipped |
| `ruff check api/ pipeline/` (0.15.11) | clean |
| `ruff format --check` on the 34 touched `.py` files | clean |
| `lint-imports` | 2 kept, 0 broken |
| `vulture api/ pipeline/ .vulture_whitelist.py --min-confidence 80` | clean |
| `mypy api/ --no-error-summary`, CI-equivalent (`C:/tmp/mypyci`) | clean (exit 0) |
| `semgrep scan --config .semgrep api/ pipeline/` | 0 findings, 0 errors |
| Lyra import check (`markdown`/`nh3` absent) | OK |
| gitleaks on `0e821fc..HEAD` | no leaks |
| Mutation, phase-3 sweep, every case on a changed file | 407/407 caught, tree byte-identical |
| Mutation, mechanical sweep, every case on a changed file | 476/476 fired (14 needed the Natural Earth cache, copied into the ignored worktree cache and re-run: all fired); no `# mutant` left |

### The `\r` check (M2; read-only, `BEGIN READ ONLY ... ROLLBACK`, 2026-09-25 ~23:00 UTC)

* `remediation_change_log`: **0 of 19,200** rows carry a CR in `old_value`, `new_value`,
  `run_stamp`, `test_id`, `change_key` or `confidence`; **0** in `evidence` (raw or JSON-escaped).
  The journal covers 34 (table, column) pairs.
* Live values: **0** curated `unified_sites` rows with a CR in `name`, `description`,
  `period_name`, `site_type`, `country` or `raw_data`; **0** journalled `unified_sites` rows (any
  source) with one in `name`, `description`, `raw_data`, `scope_reason`, `source_url`,
  `thumbnail_url`; **0** in any `card_stats` text column; **0** in `site_external_ids.value`; **0**
  in `wiki_images` `author`, `author_url`, `commons_page_url`, `original_url`, `image_kind`.
* The one CR in the checked tables is a `unified_site_names` row of a `canmore_scotland` site
  (`ALLT A' BHROCHAIN` + CR, site `56dd5efd-a6b6-4dc0-8801-a36ecf9045d5`) that **no journal row
  names**: connector data, not the transport. The Windows CRLF translation never reached
  production.
