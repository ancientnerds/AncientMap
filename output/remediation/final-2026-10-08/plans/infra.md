# Workstream `infra`: infrastructure and close-out plan (2026-10-08)

Everything below was read or measured on 2026-10-08. Nothing was written to production or to tracked files. Query files are under `C:/tmp/wf_map_infra/`.

Paths in `scripts/...` and `docs/...` are relative to the worktree `C:/PythonProjects/AncientMap/.worktrees/db-final`. Its branch is 1 ahead of and 0 behind `origin/main` (3867fe1). The API and Lyra containers on the VPS restarted about 5 minutes before my check, so another session just deployed.

## 0. Corrections to the inputs

- **The static export is not pushed.** The state README says "static_exporter, then the LFS push and deploy". That is wrong. `git check-ignore` shows `public/data/sites/` is gitignored (`.gitignore:190`) and untracked. The export exists only on the VPS, and nginx serves it from the bind mount `/var/www/ancientnerds/public/data -> /app/public/data`. The deploy's `git clean -fd` (no `-x`) leaves it alone. D25 therefore needs no commit and no deploy.
- **D24 is not set up yet.**
  - `C:/PythonProjects/AncientMap-Offsite` holds only the image tree (939 entries, from 2026-09-20 and later waves). There is no `db/` folder and no evidence tarball.
  - The VPS has `backups/video-assets-offsite` (4.6 GB) and `backups/remediation-evidence` (5 MB, from 2026-09-21).
- **Acceptance draw `draw-2026-09-25b` is half-finished and stale.** Stage 1 is imported: 652 questions, of which 370 CORRECT, 87 WRONG, 37 UNVERIFIABLE, and 158 have no final verdict (re-asks owed). Stages 2 and 3, the deterministic checks and `RESULT` never ran. The database will move a lot, so this draw can only serve as an interim 2026-09-25 reading.

## 1. Existing tools

| Area | Tool and path | What it does |
|---|---|---|
| Handoff | `scripts/remediation/opus_handoff.py` (535 lines) | `export`, `answer --model <id>`, `validate`, and import done by each stage's own tool. `ANSWER_MODELS` has three keys: opus-5-5, sonnet-5-5, MiniMax-M3.1-Flash-Preview. |
| Handoff | `ANSWER_FAMILIES` (same file) | Maps model id to `opus`, `sonnet` or `minimax`. Used by `mechanical/scope_review.judged_by`. |
| Handoff | Callers of `ANSWER_MODELS` | `fields/handoff.py:774`, `phase4/handoff4.py:435`, `phase3/model_stage.py:106`, `served_image/mcode_driver.py:126` |
| Handoff | Pinning tests | `tests/remediation/test_opus_handoff.py`, `test_phase4_model.py`, `test_teaser.py`, `test_scope_review.py`, `test_served_image.py`, `test_mcode_driver.py`, `test_phase4_v3.py`. A mutation case sits in `phase3/mutation_sweep.py` around lines 15996-16559. |
| Disclosure strings | `scripts/remediation/phase4/model4.py:129-152` | `AI_SYSTEM_OPUS`, `AI_SYSTEM_CLAUDE` (Opus and Sonnet), `AI_SYSTEM` (Claude and MiniMax), and `AI_SYSTEMS`, the set a validator accepts. |
| Disclosure strings | Rebinding trap | `AI_SYSTEM` is the default of `teaser/run.outcome_rows:1300` and is compared with `==` in `WebProvenance` (`model4.py:1638`). The correction lane `mechanical/card_disclosure.py` is pinned to `AI_SYSTEM_OPUS -> AI_SYSTEM_CLAUDE`. |
| Calibration | `scripts/remediation/mcode_driver.py`: `copy_for_calibration`, `compare_answers`, `calibrate --prepare-only`, `_main_calibrate` | Gives the reusable logic. The `mcode exec` transport is not needed. O18 is "at least 90 % agreement and 0 false sources". |
| Backup | `scripts/remediation/00_backup_and_drill.sh`, `00_restore_drill.sh`, `00_prune_backups.sh`, `01_export_snapshot.sh` | Run on the VPS from `/var/www/ancientnerds/scripts/remediation`, which is the deploy checkout. The VPS crontab has two lines: Mon-Sat 03:15 UTC with `DO_DRILL=0 KEEP=7`, and Sunday 04:15 with `DO_DRILL=1`. |
| Static export | `pipeline/static_exporter.py` | CLI flags: `--no-library`, `--sites-only`, `--hubs-only`, `--no-gzip`. It refuses to run as root. |
| Static export | `api/routes/sites.py:1835-1880` | `POST /api/sites/rebuild-static` (founder auth, 202) runs it as a background job through `api/services/background_jobs.start_job`. The status endpoint is `GET /api/sites/rebuild-static/status`. The job takes a Postgres advisory lock, so it runs once across api and api2. |
| Static export | Nightly pattern | `api/routes/vector_sync.py:403` has `start_nightly_scheduler`, a 03:00 UTC loop with `InstanceLock`. |
| Card file | `api/main.py:136-165` and `api/services/card_descriptions.py` | The boot import upserts `public/data/card_descriptions.json` into `card_stats.card_description`. It overwrites on purpose and logs each overwritten value. It also inserts zeroed placeholder rows. |
| Card file | `scripts/remediation/phase4/card_json.py` | `--prerender`, `--regenerate`, `--check`. |
| Card file | `scripts/remediation/mechanical/teaser.py` | Imports `card_json` (line 95); `card-file --steps A-B` at line 1173. |
| Card file | Tests that touch the file | `tests/remediation/test_phase4_card_json.py`, `test_restart_overwriters.py`, `test_mechanical_teaser.py`, `test_phase3_write.py`, `tests/api/test_scope_read_paths.py` |
| Acceptance | `scripts/remediation/acceptance/{draw,redraw,questions,judge,answers,score,checks}.py` | `judge.py` subcommands: `export-stage1`, `brief`, `import-stage1`, `export-reask`, `export-stage2`, `import-stage2`, `export-stage3`, `import-stage3`, `deterministic`, `result`. |
| Acceptance | `output/remediation/acceptance/PROTOCOL.md` | 11 judged fields per site (F1-F11), 10 canaries, deterministic checks D1-D6, and the gates V1-V3 and A1-A3. |
| Shorts-side code | `pipeline/video/shorts_render.py:87` (`TEASER_NOTE`) | Says "Claude / Anthropic, MiniMax M3.1 Flash". |
| Shorts-side code | `pipeline/video/shorts_audit.py` (check S13 `card_traced`) | Already checks the card hash against its provenance. |
| Push | `.githooks/pre-push`, push lock `C:/PythonProjects/AncientMap/.git/main-push.lock` | Rule is in `output/remediation/MCODE_START.md` section 6. |
| Workflow tool | `agent(prompt, {model, effort, schema, label, phase})` | Precedents in `output/remediation/orchestration/*.js`: `wa-v3d-handoff.js` for answering pools and serialised import operators, `wb-mass.js`, `wd3-run.js`. |

## 2. Run state measured today

- **Production journal.** Max id 345369, last write 2026-10-07 18:11 UTC (`wb-teaser-card-s034`), 102,532 rows.
  - 4,900 sites are shown out of 5,004.
  - 4,900 have a `card_stats` row, of which 4,737 have a non-empty card.
- **Backups.**
  - The VPS has 7 nightly dirs (`2026-10-02` to `2026-10-08`) plus `2026-09-19_pre-audit` and `2026-09-21_pre-write`.
  - The 2026-10-08 03:16 dump is 892,757,235 bytes (879 MB per dir). The CSVs of 8 tables are present. Nightly runs have `DO_DRILL=0`, so the last drill was the Sunday 2026-10-04 run.
  - The VPS has 82 GB free (58 % used).
  - Workstation C: has about 19 GB free (the brief says 14).
- **Static export.** `sites/index.json` is 362,667,649 bytes, mtime 2026-10-06 09:19 UTC. Journal writes since then (about 2 days) are not in it. `hubs.snapshot.json` is from 2026-10-06 09:21.
  - No `job:rebuild-static` row was found, and nothing schedules the job. My query selected a nonexistent column, so re-check the heartbeat row with `SELECT * FROM pipeline_heartbeats`.
  - `save_json` writes in place with `open(path, "w")`, so readers can see a truncated file for part of the roughly 4-minute run.
- **Card file.** The 2026-10-07 sitting wrote it as 4,826 cards, with `card_json.py --check` at 0 deviations.
- **Old renders.** `video-assets/shorts/` holds 16 site dirs (olympia, puma-punku, federsee, giza, gochang, ishtar-gate, karatepe, machu-picchu, nazca-lines, pamukkale, rano-raraku, senegambian, stonehenge, tahai, teotihuacan, tomb-of-jahangir). Each has 8-26 mp4 files. Beside them lie `kerbatch`, `voice-samples`, logs, `AUDIT-REPORT.md` and `QA-NOTES.md`. HUMAN_ONLY_DECISIONS Nr. 11 retired them. `site_shorts` has 0 rows.
- **Answer census.** `model_census/ANSWERS_TRUE_MODEL.jsonl` stops at 2026-10-04: 11,456 Opus answers and 8,471 Sonnet answers. The MiniMax answers after 10-03 are not in it.

## 3. Steps per decision

### 3.1 Execution machinery for Claude-only answering (D6, D7, D10)

**3.1a Stamps and roles (code).**
1. `opus_handoff.py`: add `HAIKU_MODEL = "anthropic/claude-haiku-5-5 (Claude Code agent)"`. Add `"claude-haiku-5-5"` to `ANSWER_MODELS` and `"haiku"` to `ANSWER_FAMILIES`. Update the docstring (lines 9, 43). Keep the MiniMax entries, because about 2,000 or more recorded MiniMax answers must stay valid.
2. Per-role stamps without changing `ANSWER_KEYS`. That frozen shape is write-once and checked by `read_answer`. The stamp stays the real model.
   - New file `scripts/remediation/claude_roles.py` holds a `ROLES` registry: role, model id, effort, calibration pool, sealed threshold, calibration result sha256.
   - Add a `--role` flag to `answer`. It refuses a role whose registered model differs from `--model`, and writes `answered_by = "<role>:<agent>"`.
   - `served_image/mcode_driver.py` and `fields/handoff.py` keep working because they read only `model`.
3. Calibration reuses `mcode_driver.copy_for_calibration`, `compare_answers` and `Agreement.passed`, moved to a transport-free module.
   - The threshold is O18: at least 90 % agreement and 0 false sources. Seal it per role in `output/remediation/roles/SEAL.json` before the run, with the sha256 of the pool and of `claude_roles.py`.
   - A failing role moves up one tier (Haiku to Sonnet to Opus) and is re-calibrated.
4. Disclosure string `model4`:
   - Do not rebind `AI_SYSTEM`. Add a new byte-pinned string, `AI_SYSTEM_CLAUDE_2610`, "Claude Opus and Claude Sonnet (Anthropic) ... an-sites-remediation-2026-10". Add Haiku to it only for writes where Haiku produced a stored result.
   - Add it to `AI_SYSTEMS`.
   - Make the new-write defaults (`teaser/run.outcome_rows`, `WebProvenance`) use it. `WebProvenance`'s `!= AI_SYSTEM` check becomes `not in AI_SYSTEMS`.
   - Leave `card_disclosure.py` pinned to its pair (`AI_SYSTEM_OPUS`, `AI_SYSTEM_CLAUDE`).
   - Consider a disclosure correction lane for the 715 WD3/WD4 MiniMax rows and 167 gap cards (D10) only for what survives re-checking.
5. Tests:
   - Update the pinning tests to assert the new keys.
   - Add new tests for the `--role` refusal, the haiku stamp, the 4-string `AI_SYSTEMS`, and the new-write default.
   - Mutation-sweep cases in `phase3/mutation_sweep.py`: drop the haiku key; accept a role/model mismatch; rebind `AI_SYSTEM`; accept a stamp outside `ANSWER_MODELS`. Run the sweep in a scratch worktree, because the sweeps import `prod_write`.
6. Format by hand with ruff 0.15.11 (`ruff format`). CI's ruff covers only `api/` and `pipeline/`, so `scripts/` and `tests/` are unchecked.

**3.1b How this session answers (workflow).**
- One workflow per stage. `agent(prompt, {model, effort, label, phase})` uses the role's registered model and effort; the model id comes from `ROLES`.
- Each agent follows the `handoff brief` / `answer` pattern from `wa-v3d-handoff.js`: it records answers through `opus_handoff.py answer --role R --model M`, never a hand-written file.
- Import operators are Haiku low, serialised through a promise lock (precedent: `serial()` in `wa-v3d-handoff.js`).
- The tree guard must be kept. After each batch, a `git status` check on tracked files voids a batch that wrote into the checkout. This happened on 2026-10-03 with `wd3-r0-b0296`.
- Width: at most 3 concurrent agents that fetch the web (Wikimedia throttling, above). Agents that only read local files can run up to the harness cap of `min(16, CPUs-2)`. Memory suggests about 14 for RAM. Do not mix a web-fetching stage with other fetching stages.
- Never treat HTTP 403/429 as a finding; `curl` the URL first (`reference-wikimedia-ip-throttling-parallel-agents`).

**3.1c Calibration pools (already-judged cases).** Recorded Opus/Sonnet answers are in `output/remediation/handoff/*`. Exclude MiniMax-answered rounds as ground truth.

| Role (D6) | Pool | Size | Threshold |
|---|---|---|---|
| Card writer, Opus high; hook rating, Opus medium | Hook rating has no recorded ground truth. Use the 2,828 accepted WB cards (judge-passed) for writer plus mechanical contract checks. For hook rating, use the 60 hand-drawn cards of the design run (mean 1.98/5) as an agreement set. | 60 | 90 % within 1 point |
| Fact checker, Sonnet high; web verifier, Sonnet high | WB check/verify batches answered by Opus (`wb-*`, `wc-verify-02`) | 3 batches, about 15 questions each | at least 90 % and 0 false sources |
| Period/field research, Sonnet high | WD1 and WD3 Opus/Sonnet-answered rounds | 3 batches (24 questions, as `fields-02`) | at least 90 % where both sides decide, and 0 false sources |
| Adversarial re-check, Opus high | The Opus re-judge of the 934 DeepSeek decisions (481 kept, 453 reverted) | 40 cases | at least 90 % |
| Image prefilter (photo, map, text), Haiku low | Only 135 labelled `wiki_images.image_kind` rows in production (105 site_photo, 17 artifact, 9 map_or_document, 3 painting_or_artwork, 1 other), plus `gallery_audit/calibration-2026-09-25-opus` (189 jobs). This is thin; a failing Haiku moves to Sonnet. | 135 | at least 90 % |
| Image "shows this site", Sonnet medium | `gallery_audit/calibration-2026-09-25-opus`, `vlm_pilot/SAMPLE.jsonl` (155), the 2,170 Sonnet image checks | 100 | at least 90 % and 0 false depicts |
| Pilot verdict/audit, Opus xhigh | Not calibrated against ground truth. Calibrate against canaries (A-2 below). | 10 canaries | at least 9 of 10 |
| Operators, Haiku low | Command-only: no model judgement. A mismatch with the recorded numbers fails the stage. | n/a | exact |

### 3.2 D24: backups, cross-copy as a routine

1. New `scripts/remediation/offsite_sync.py`, run from the workstation by Windows Task Scheduler. It is modelled on `AncientMap-LaneWatchdog`, weekly on Sunday at about 06:00 UTC, after the 04:15 drill. It does the following:
   - scp the newest `database_*.dump` to `C:/PythonProjects/AncientMap-Offsite/db/`.
   - Run `sha256sum` on the VPS and hash the local copy; compare them; keep a `SHA256SUMS` file on both sides.
   - Keep the newest 2 dumps locally: 2 x 0.9 GB.
   - Tar `output/remediation` excluding `*.env`, `handoff/` and `pages/` caches, push it to `backups/remediation-evidence/` on the VPS, and verify the sha256 on both sides.
   - Exit non-zero and write a loud line if the newest dump is more than 26 h old (there is no `MAILTO`; A4 is dropped).
2. Pre-wave dump: before each write wave, run `DO_DRILL=1 ./00_backup_and_drill.sh <date>_remediation` on the VPS. About 2 min, plus 625 MB container I/O.
   - **Trap:** a stamp not ending in `_remediation` is never pruned (0.9 GB each). A stamp ending in `_remediation` is pruned after 7, and the stamp just taken is protected.
   - The prune keeps only the newest 7 `_remediation` dirs. A pre-wave dump from early in a long campaign can be pruned within 7 days. Copy it locally the same day.
3. Image tree: re-sync is a large download (20 GB base, then 1600-px waves). Do not do this at scale without a go: C: has 19 GB free. Restrict to a changed-file manifest and flag it.
4. Docs: close A4/A5 in `HUMAN_ONLY.md` as "dropped by D24".

### 3.3 D25: static export after every wave, and nightly

1. Make the file replace atomic. In `pipeline/static_exporter.py::save_json`, write to a temp file in the same directory and `os.replace`. Apply to the `.gz` as well. Add a test in `tests/pipeline/test_static_export_preflight.py`.
2. Nightly: add `start_static_export_scheduler()` in a new `api/services/static_export_schedule.py`, started beside `start_nightly_scheduler` in `api/main.py:266`. Time: 04:30 UTC, after the 03:15 backup and the 03:00 reindex. It calls `start_job(REBUILD_STATIC_JOB, _run_static_export)` and swallows `JobAlreadyRunning`.
   - The lock makes it run once across api and api2. A deploy during the 4-minute run kills the child and leaves the status "interrupted"; the next night repairs it.
   - Layer contract: `api` may import only listed `pipeline` families; the exporter is run as a subprocess, so no new import crossing.
3. After every wave (the trigger): the lane's closing step calls the export through a new CLI `python -m api.services.rebuild_static` in the API container. It takes the same advisory lock so it cannot overlap the nightly job. Run it as the container user, never `-u root`.
4. Freshness check `scripts/remediation/static_export_check.py`. It runs on the VPS: `scp` the script, `docker cp` it into the container, then `docker exec ancient_nerds_api python /tmp/x.py`. Do not pipe it over `docker exec -i`, which swallows ssh stdin. It compares `sha256(left(description,500))` and the card text of every shown site in the DB against `d` / `cd` in `index.json`. Do not download the 362 MB file to the workstation. Acceptance: 0 differing sites.
5. First run now: export, then the freshness check. The globe popup still shows removed sentences until then.
6. Docs: replace "LFS push" wording in HANDOVER/state notes and the runbook step 3; fix the `PROJECT_LESSONS` text if it needs the new scheduler.

### 3.4 D25: the card file rendered from the DB instead of the boot import

The owner wants the database to be authoritative. The only consumer of `public/data/card_descriptions.json` is the boot import. The frontend and the static exporter read `card_stats.card_description` from the database. I grepped `ancient-nerds-map/src`: no hits.

1. Remove the boot import: the block `api/main.py:136-165` and `api/services/card_descriptions.py` (the import, the loader and the stale-id handling). Keep the `_backfill_card_stats` task, which fills placeholder rows. A new site still needs a `card_stats` row; today 4,900 of 4,900 shown sites have one. A new row can be created by the card lane that writes the card, or by `backfill_placeholder_stats` if the card write inserts the zeroed row first.
2. Remove `public/data/card_descriptions.json` (1,094,256 bytes, tracked) and `phase4/card_json.py`. Remove the `card-file` command and the `CJ` import from `mechanical/teaser.py` (lines 93-95, 1066-1097, 1173, 1193). The sitting's database read-back is `accept --step N`. Only delete the file after the removed import is deployed, so that no boot reads it.
3. Tests to adapt or delete: `tests/remediation/test_phase4_card_json.py`, `test_restart_overwriters.py` (its guard exists only for the boot overwrite), the card-file parts of `test_mechanical_teaser.py` and `test_phase3_write.py`, `tests/api/test_scope_read_paths.py`. Mutation-sweep cases around `card_json` in `phase3/mutation_sweep.py` go.
4. Effect on process: the push lock is no longer needed around card writes. A card write is database-only. The lock stays for pushes.
5. This is a code push (a live deploy, rebuilds api and lyra). Run the Lyra-image import check from CLAUDE.md before pushing. Order: merge `origin/main`, gates, one push of a fixed SHA, then check that the commit reported by `http://localhost:8000/` equals HEAD. Confirm "0 `[STARTUP] Card description overwritten`" is moot, and that `card_stats` counts are unchanged before and after.
6. Docs: `CARD_DESCRIPTIONS.md` 5.5 ("The card file: rendered from the database, pushed at once") and 5.4's order of writing become "database only". `FIELD_CONTRACT.md` says "authoritative copy = the JSON file" and must change.

### 3.5 D25: archive the 16 old renders

- Move (never delete) the 16 slug dirs from `video-assets/shorts/` to `video-assets/shorts-archive-2026-10-08/` on the same drive, so no copy and no disk growth. Leave `kerbatch`, `voice-samples`, `QA-NOTES.md` and `AUDIT-REPORT.md` where they are, or move them with the logs. Write a `MANIFEST.sha256` of the mp4 files before and after the move.
- The `video-assets-offsite` copy on the VPS (4.6 GB, from 2026-09-17) is a separate backup. Do not touch it. Shorts-side code is untouched. No render, no upload.

### 3.6 D25: the final per-field error-rate measurement (WF)

Reuse the acceptance tooling. The gate is gone (O1, 2026-09-26); this is a report only.

1. Draw: new draw with a new sealed seed (PROTOCOL says the next seed is 20260926 -> already used by `draw-2026-09-25b`; use the next one) after the last write wave of the DB repair. `redraw.py` excludes earlier draws' samples. Seal `PROTOCOL.md` and `draw.py` sha256 in AUDIT_LOG before the draw.
2. Sample size: 60 sites gives a 0/60 Clopper-Pearson upper bound of about 6 %. For per-field rates, I recommend 100 sites (1,100 questions); 0/100 gives about 3.6 %.
3. Judges: Opus xhigh (the "pilot verdict/audit" role) for all three stages. Stage 1 is one question per (site, field). Stage 2 is a second independent judge on each WRONG. Stage 3 handles UNDECIDED. Each judge answers one question of a site.
4. Commands (from the repository root; `J=scripts/remediation/acceptance/judge.py`):
   - `$J export-stage1`, `brief`, `opus_handoff.py validate`, `import-stage1`
   - `export-reask` (at most 2 rounds), `export-stage2`, `import-stage2`
   - `export-stage3`, `import-stage3`, `deterministic`, `result`
5. Needed code changes:
   - `judge.py` and `questions.py` refer to Opus-only judges. Allow the registered Opus xhigh role.
   - Remove or relax the V3 gate in `score.py`, since O1 lifted it. Read-only checks D1-D6 stay.
   - New field: the shorts-v1 card checks (no name, 160-190 characters, two sentences). Add them to `checks.py` as deterministic D7 for the cards lane.
6. Report: per-field error counts with severity and Clopper-Pearson 95 % intervals, UNVERIFIABLE per field, stage-2 refutation rate, canary recall. Write `RESULT.json` and `RESULT.md`, and the verdict file sha256 into AUDIT_LOG.
7. Interim measurement: finishing `draw-2026-09-25b` is optional and cheap (158 re-asks plus 87 stage-2 questions plus deterministic). It would give a 09-25 baseline to compare against. Skip it if budget matters.

### 3.7 Docs

- **`CLAUDE.md` top paragraph.** It still says "no Claude... MiniMax Code since 2026-10-03" (the model-agnostic changes are partial). Rewrite it:
  - Claude only per D6 (Opus 5.5, Sonnet 5.5, Haiku 5.5 per role).
  - The stamp names the real model; MiniMax stamps stay valid for the rows already written.
  - The remediation state of 2026-10-08.
  - The "Studio" paragraph still says "inside a MiniMax Code session"; flag it, but do not change the Studio rules.
- **`output/remediation/HANDOVER.md` section 0.** Add a section 0.0.0 above 0.0, since 0.0 says "this section wins" for the MiniMax era. Content: the D1-D35 summary, the new roles and stamps, the new run state, and the removed card file and boot import.
- **`docs/procedures/CARD_DESCRIPTIONS.md`.**
  - 1.3/1.4: the name is never in the card (D1 supersedes).
  - O4/D2: 160-190 characters stands.
  - O6/D5: the old March cards stay.
  - O10/D11: the AI notice stays off.
  - 5.5: the card file section.
  - The `shorts-v1` contract C1-C20 from `teaser_design_digest.md`.
- **`AUDIT_LOG.md`.** Add the decisions record, the sealed thresholds and the calibration results as they come.
- **`HUMAN_ONLY.md`.** Close A4 and A5. Note that Shorts decisions D26-D35 are recorded for later and nothing is produced.
- **Shorts-side code the card lane needs** (not production of Shorts): `TEASER_NOTE` in `pipeline/video/shorts_render.py:87` is a constant naming MiniMax. Build it from `_card_provenance.ai_system` (as the digest proposes) and drop MiniMax for new cards. `shorts_audit` S13 stays. Provenance v3 for the card and its tests belong to the cards workstream.

### 3.8 Push discipline

1. Take the lock `C:/PythonProjects/AncientMap/.git/main-push.lock` (session name and UTC time). If it exists, wait. It did not exist when I checked. Keep it until your own push is deployed.
2. `git fetch`, merge `origin/main` first (another session pushes today, including `c1429a5` Haiku chat and `3867fe1`). Then `git log origin/main..HEAD` to be sure you push only your own commits.
3. Run `ruff format --check api/ pipeline/` yourself. The pre-push hook does not run it, and CI does.
4. `git push` of a fixed SHA. The hook runs all gates (pytest, ruff, lint-imports, vulture, type-check, vitest, knip), about 20-30 min. Do not commit while it runs.
5. Poll CI with `gh run list --branch main` and compare the full `headSha`. A short `--commit` sha finds nothing. Do not pipe `gh run watch` or `ruff` into `tail`; the pipe hides the exit code.
6. After deploy: `curl localhost:8000/` on the VPS and check that `commit` equals HEAD. A green run alone is not proof.
7. A `package.json`/`ffmpeg-static` 503 can kill the whole frontend build: retry with an empty commit.

## 4. Dependencies on other workstreams

- Every description change makes that site's card stale (the description sha256 changes). So the cards workstream must finish after the descriptions workstream per site. The static export check and the WF draw come last.
- WF must be drawn after the last write wave (periods, coordinates, images, duplicates, re-targets) and after the cards. Otherwise a drawn site changes under the judges.
- Role calibration (3.1) must exist before any other workstream answers a question. Make this the first deliverable.
- The card file removal (3.4) should land before the next card write wave. A card write then no longer needs a file push or a card-file sitting.
- D14 merges and D13 re-targets change ids and names. After them the static export must be re-run, and `card_stats` rows of retired losers must be handled by the owning workstream.
- The `ai_system` string choice (3.1a-4) affects the descriptions workstream's WC/WN writers as well, since they use `WebProvenance`.

## 5. Estimated model answers

| Stage | Answers |
|---|---|
| Role calibration, about 8 roles at 40-135 cases | about 500 |
| WF measurement, 60 sites: 660 stage-1 + 10 canary + about 160 re-asks + about 90 stage-2 + about 15 stage-3 | about 935 |
| WF measurement, 100 sites (my recommendation) | about 1,570 |
| Optional finish of `draw-2026-09-25b` (158 re-asks, about 87 stage-2, a few stage-3) | about 250 |
| Backups, export, card-file removal, archive, docs | 0 (code, shell and docs; operators only) |

The re-ask rate (158 of 652, 24 %) comes from the 09-25b run. It is high because quote checks fail. Budget for it.

## 6. Risks and traps

- **Wikimedia and web fetch.** At 4 or more parallel fetchers the office IP gets 403/429, and verifiers write false UNVERIFIABLE (nine false findings on 2026-10-07). Keep to 3. Test the URL with `curl` before accepting a finding. General search engines are blocked here; the WebSearch tool works.
- **Disk.** C: has 19 GB free (brief says 14). Worktrees cost about 4.2 GB each. The offsite image sync (20 GB base) and the 362 MB export download should not happen at scale. The WF `pages/` cache grows. Prune `handoff/` and `pages/` out of the evidence tarball.
- **Non-atomic export write.** `save_json` truncates the 362 MB file in place. Readers can see a short file for part of the run. Fix in 3.3 before scheduling it.
- **A deploy kills a running `docker exec` export.** Run the post-wave export after the last deploy.
- **Concurrent exports.** The plain CLI takes no lock. Two exports at once corrupt the files. Use the job path or the new locked CLI. Never run as root (the 2026-08-18 root-owned files).
- **Card file removal.** Until the removal is deployed, a foreign push still re-imports the old file over new cards, so keep the push lock for card writes until then. Removing the import must land together with deleting the file. Check the commit on `localhost:8000/`.
- **A stamp must name the real model.** The 2026-10-01 census found 8,471 answers stamped Opus that Sonnet wrote. A role registry that lets `--role` and `--model` diverge would repeat it, so the refusal in 3.1a-2 is binding.
- **Do not rebind `AI_SYSTEM`.** Pinned consumers and 17+ WN provenances break.
- **A prepared agent that edits files.** A field-fill agent once rewrote five production files. Keep the tree guard on every batch.
- **MiniMax rows.** Do not use a MiniMax-answered batch as calibration ground truth. D10 re-checks all of them.
- **VPS `output/` is root-owned and old** (`_batch*.json`, `_fix_descs.py`). It once broke a deploy checkout mid-way. Do not write there.
- **Backup prune.** `KEEP=7`, only `*_remediation` dirs. A pre-wave dump from early in a long campaign can be pruned; copy it locally.
- **No `MAILTO`.** A failed nightly backup tells nobody. The workstation routine's age check covers this.
- **The Windows shell.** The `bash` tool in a `mcode` session was PowerShell; here it is Git Bash. Patch scripts go in via Write, not heredocs (backslash loss). Keep scratch scripts in a subfolder of `C:/tmp/wf_map_<label>/`, never `%TEMP%` (a `gettext.py` there once shadowed the stdlib).
- **An agent-run `du` on `output/remediation` and `video-assets`** exceeded the 120-s tool timeout. Avoid recursive size scans of the main checkout.
- **Gates.** The pre-push hook takes 20-30 min and aborts on a dirty tracked tree. `main` was red once from a test that read production over ssh; keep new tests DB-less.
- **Shorts.** No render, no upload, no OAuth (owner: "die shorts videos aber noch nicht herstellen"). The archive step and the `TEASER_NOTE` change are the only Shorts-side work here.