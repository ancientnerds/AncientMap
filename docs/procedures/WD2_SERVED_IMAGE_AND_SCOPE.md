# WD2 - the served image (O6) and the E3 scope with Oceania (O7)

Lane WD2 of the finishing plan (`output/remediation/FINISH_PLAN_2026-09-26.md`, workstream WD).
Owner decisions of 2026-09-26, binding:

* **O6** "Belegt ersetzen, sonst leeren": a served image that does not show its site is replaced
  only by an image a vision check confirmed; otherwise the site serves no image.
* **O7** "Ja, Ozeanien wie Amerika": Oceania is in scope through 1500 AD, like the Americas (E3).

Every model judgement is an Opus agent answering through `scripts/remediation/opus_handoff.py`;
no pipeline code calls a model. Every production write is journalled (`remediation_change_log`
through `apply_remediation_change()`) by an existing writer, in steps of at most 100 sites, each
accepted with 0 deviations before the next.

All commands run from the repository root with the repo venv (`./.venv/Scripts/python.exe`,
abbreviated `$PY`) and `PYTHONIOENCODING=utf-8`. Output directories under `output/remediation/`
are gitignored.

---

## 1. The E3 rule with Oceania (O7) - code, done

**The one rule.** `pipeline/normalizers/dates.py`: `e3_region(record)` places a row in Oceania
first, then the Americas by the longitude window (-170..-30), then the rest of the world;
`passes_date_cutoff(record)` compares `period_end or period_start` with `E3_CUTOFFS` (Oceania 1500,
Americas 1500, rest 500). A row is Oceania when `country_key(country)` is in `OCEANIA_COUNTRIES`, or
names a state of `OCEANIA_PARTS` and its point lies in one of that state's Pacific boxes.

* `country_key` reads the text after the last comma, trimmed and lower-cased ("Queensland,
  Australia" is `australia`).
* `OCEANIA_COUNTRIES` is the UN M49 region 009 (Australia and New Zealand, Melanesia, Micronesia,
  Polynesia) as names **and** ISO 3166-1 alpha-2 codes, plus the island names Hawaii, Easter Island
  and Rapa Nui.
* `OCEANIA_PARTS` covers the states whose rows carry the state's name or code: Chile/`cl` (Rapa
  Nui), France/`fr` (French Polynesia, New Caledonia, Wallis and Futuna), United Kingdom/`gb`
  (Pitcairn), United States/`us`/`usa`/`united states of america` (Hawaii, Guam and the Northern
  Marianas, American Samoa, Wake). Western New Guinea stays Indonesia's (M49: South-eastern Asia).

**Where it is used** (every caller imports it; nothing re-types it):

| place | how |
|---|---|
| `pipeline/unified_loader.py` | the load-time cutoff for every source (its private pre-O7 copy is gone) |
| `pipeline/lyra/site_identifier.py`, `prospector/resolve.py`, `prospector/extract_radar.py` | pass `country` and `lat` with the date |
| `scripts/remediation/census/tests/t11_scope_window.py` | T11 decides the region with `e3_region` |
| `scripts/remediation/mechanical/lane.py` | `country_key_sql`, `in_oceania_sql`, `outside_e3_window()` render the same lists into SQL (`before_o7=True` keeps the text the applied scope-e4 lane ran with) |
| `scripts/remediation/phase4/plan4.py` | the `scope-pending` flag reads `passes_date_cutoff` |
| `ancient-nerds-map/src/shared/disclaimerContent.ts` | the public scope statement names Oceania |
| `docs/procedures/SITES_DB_REMEDIATION_2026-09.md` (E3), `PROJECT_LESSONS.md` | the statement of the rule |

`api/` and the visibility predicate do not code the date rule: the platform hides a site only by
`scope_status = 'retired'` (`pipeline/utils/public_sites.not_retired()`), which the scope lanes
write. The empire list's comment (`ancient-nerds-map/src/config/empireData.ts`) describes how that
curated list was chosen, not a runtime rule, and is not part of E3.

**How `country` is stored** (read-only, 2026-09-26): the curated rows and `lookup_country`
(Natural Earth's `name`) spell names; `geonames` (101,375 rows) and `dare` (1,478) store ISO codes;
`earth_impacts` (84), `radiocarbon_paleo` (22) and `arachne` (1) store "Region, Country". Hawaii is
stored as `United States`/`US`, Easter Island's eleven curated rows as `Chile`, French Polynesia's
three as `France`.

**Measured on production (read-only, 2026-09-26, `in_oceania_sql()` and `outside_e3_window()`):**

* 45 curated Oceania rows - Australia 30, Chile 11 (Rapa Nui), France 3 (French Polynesia),
  Northern Mariana Islands 1 - all `scope_status` NULL.
* 75 curated rows lie outside the O7 window: 57 retired, 15 `in_scope`, 3 `pending`; **0 with no
  scope decision**. O7 moves no verdict of today's rows.
* scope-e4 retired **no** Oceania site for its date, so there is nothing to reinstate today. The
  scope review (section 2) re-reads every scope-e4 rule-(a) retirement under the O7 rule in every
  wave and plans `retired -> in_scope` for one that O7 carries.

Tests: `tests/pipeline/test_e3_oceania.py`, `tests/remediation/test_mechanical_scope.py`
(`TestTheWindowPredicate`: the rendered SQL evaluated in SQLite equals `not passes_date_cutoff`,
and `country_key_sql` equals `country_key`), `tests/remediation/test_t11.py`.

---

## 2. The E3 scope review - entries that are no archaeological site

`scripts/remediation/mechanical/scope_review.py`, the wave lane `scope-review-<wave>`
(`mechanical/lane.py`: `scope_review_lane`, `scope_review_readback`), written by
`mechanical/apply.py` like every mechanical lane.

**The decision** is Opus's, per site, with sources - never a pattern. The agent answers `site` or
`not_a_site` with a kind (`natural_formation`, `modern`, `object`, `legend_or_hoax`), one sentence
and verbatim quotes (prompt `scope-nonsite-v2`). A `not_a_site` **counts** only when its quotes
found word for word on the fetched pages (`opus_audit/quotes.py`) come from at least two websites
(every Wikimedia project - Wikipedia, Wikidata, Commons - and the known copies of Wikipedia -
Wikiwand, DBpedia, WikiZero, Alchetron, en-academic, ... - count as one; production is never
fetched). A counted `not_a_site` becomes `scope_status = 'retired'`, `scope_reason = 'E3: not an
archaeological site (<kind>): <sentence>'`; the found quotes and the agent are the journal row's
evidence. A `site` carries no quotes (`"quotes": []`; `check-answer` refuses one that does) and
writes nothing.

**Rounds.** Round 0 asks the funnel's candidates. Round N (every earlier round imported) asks
again, from the current export and of new agents: every site whose latest answer is an uncounted
`not_a_site` - the same prompt, as the acceptance judges re-ask, at most three asks at one premise
- and every site whose latest answer is a counted `not_a_site` about an entry that has moved since
(WD1 corrects name, type, point, country and dates in parallel; an answer about the old entry says
nothing about the new one). A round with nothing to ask is refused before it writes any file
("round N asks nothing"). The latest answer of a site decides: a moved entry answered `site` in a
later round is not retired. A `not_a_site` still uncounted after three asks stays as it is and is
listed in its `NONSITE_R<n>.jsonl`.

**Who is asked** (the funnel chooses questions, never answers): a shown curated site whose type is
one of `NON_SITE_TYPES` (Natural feature, Geological interest, Magnetic anomaly, Underwater
structures, Impact crater, Elongated skulls, Unknown), whose Wikidata item is an instance of a
natural feature (`NATURAL_CLASSES`: rock formation, mountain, lake, island, ...), that has no
Wikidata item in WD1's harvest, or that is `pending`. Measured read-only in section 5.

**Guards of the plan** (`build_plan`): a site retired since the question is skipped
(`already-retired`); a site whose premise - name, type, point, country, dates - moved since the
answer (WD1 corrects them in parallel) is skipped (`premise-moved`), and the next round asks it
again (runbook step 8); the premise is also the write's guard 5, so the transaction refuses a row
that moved after the plan.
The description is not in the premise: WA/WC rewrite it in parallel, and a new text of the same
entry does not move its scope. Each round renders its prompts from its own snapshot
(`SNAPSHOT_R<n>.jsonl`), so a refreshed export never makes an answered round stale.

**Waves.** A wave is at most 100 sites and a run stamp is applied once, so the plan is written wave
by wave: each wave has its own lane `scope-review-<label>` (label `YYYY-MM-DD[a-z]`), stamp
`<label>_mechanical-scope-review`, and directory `output/remediation/mechanical_scope_review/<label>/`.
`write` plans the first 100 open sites of the current export and refuses an export an earlier wave
was planned from - after a wave lands, export again and the written sites are no longer open.

### 2.1 Runbook

Prerequisites: WD1's harvest at `output/remediation/fields/harvest/` (SITES.jsonl covering every
curated site, `entities/<QID>.json`); the WE link pass (L5: generic or wrong Wikidata items) run
first, so the `wikidata`/`no-item` signals read the corrected items. Run it **after WD1's field
writes** where the order allows: an entry WD1 moves after its answer is asked again (step 8), which
costs a round.

```bash
PY=./.venv/Scripts/python.exe
SR=scripts/remediation/mechanical/scope_review.py
H=output/remediation/handoff/scope-review-2026-09-26

# 1. read production (read-only, one repeatable-read snapshot) -> export/export.jsonl
$PY $SR export
# 2. round 0: every funnel candidate, 12 per batch, into a new handoff
$PY $SR export-round --round 0 --handoff $H-r0
# 3. per batch B (r0-001, r0-002, ...; up to 16 agents at once, each its own batch):
$PY $SR brief --round 0 --batch-id B          # the agent's full instruction; it answers with
                                              # check-answer + opus_handoff.py answer
# 4. every answer recorded, nothing stale or malformed:
$PY scripts/remediation/opus_handoff.py validate --dir $H-r0
# 5. import: fetch every cited page once, check every quote -> NONSITE_R0.jsonl
#    (an answer out of shape stops it, all named, nothing written: delete those answer files
#    from the handoff, have them answered again, validate, import)
$PY $SR import-round --round 0
# 6. the next round N = 1, 2, ...: a fresh export, then the round into its own handoff. It
#    refuses "round N asks nothing" (exit 1, no file written) when no answer is left to ask
#    again - then go to step 7. Otherwise steps 3-5 with --round N, and step 6 with N + 1.
$PY $SR export
$PY $SR export-round --round 1 --handoff $H-r1
# 7. the next wave (<= 100 sites), from a fresh export:
#    PLAN.jsonl, SKIPPED.jsonl, PLAN.md, ROLLBACK.sql, SOURCE.json
$PY $SR export
$PY $SR write --wave 2026-09-26
# 8. after the wave's gates below: if its SKIPPED.jsonl lists `premise-moved` sites, step 6
#    (next round number) asks them again before the next wave; then step 7 with the next label
#    (2026-09-26b, ...) until `write` says "nothing to write".
```

Then the wave goes through the mechanical lane's gates, in this order:

```bash
L=scope-review-2026-09-26               # the wave's lane: scope-review-<the --wave label>
A=scripts/remediation/mechanical/apply.py
$PY $A --lane $L --check-primitive      # the journal primitive and the columns are as expected
$PY $A --lane $L --verify               # read-only read-back before (keep the output)
$PY $A --lane $L --interests            # other writers' interests in the rows
$PY $A --lane $L --emit                 # APPLY.sql, pinned to PLAN.jsonl
$PY $A --lane $L --rehearse             # APPLY.sql with COMMIT -> ROLLBACK against production
$PY $A --lane $L --probe-guards         # each guard refuses its own probe
$PY $A --lane $L --apply                # the write; the read-back must match both ways
$PY $A --lane $L --verify               # read-only read-back after
$PY $A --lane $L --rehearse-rollback    # ROLLBACK.sql, COMMIT -> ROLLBACK, on the landed rows
```

What the gates check: the transaction writes only curated rows, only `scope_status`/`scope_reason`,
only rows that still hold the planned old value **and** the planned premise (guard 5), exactly the
planned number of rows, each with its journal row; the read-back compares plan, journal and data
both ways and prints the scope counts, the O7 residual (curated rows outside the window with no
decision), the retirements as no archaeological site, the Oceania rows retired for their date and
rows with a status but no reason. A wave is accepted when `--apply` reports the read-back clean and
the after-read shows exactly the planned deltas (0 deviations). Then step 8.

**Undo** of a landed wave (after its `--rehearse-rollback` passed): send its pinned `ROLLBACK.sql`
through the project transport, then read back:

```bash
$PY - <<'EOF'
import sys; sys.path[:0] = [".", "scripts/remediation"]
from mechanical import apply as A
from mechanical.lane import resolve_lane
from prod_write import send
lane = resolve_lane("scope-review-2026-09-26"); d = A.lane_dir(lane)
records = A.load_records(d / "PLAN.jsonl")
sql = A.verify_pinned(d / "ROLLBACK.sql", plan_path=d / "PLAN.jsonl",
                      expected=A.rollback_statement(records, lane))
proc = send(sql); print(proc.returncode, proc.stdout, proc.stderr)
EOF
$PY $A --lane scope-review-2026-09-26 --verify
```

The reversal journals under `<stamp>-rollback` and refuses rows that moved since the write.

After the waves: the retired sites leave the static export, sitemap, Qdrant and card draws with the
next WF export (`public_sites.not_retired()`); IndexNow and a push as in WF. The scope waves need
**no card_stats recompute**: they write only `scope_status` and `scope_reason`, and neither is an
input of a card (`mechanical/card_stats.py`, `INPUT_COLUMNS`).

---

## 3. The served image (O6)

`scripts/remediation/served_image/` (`state`, `commons`, `precheck`, `vision`, `plan`, `run`),
written by the shared image writer `scripts/remediation/gallery_audit/chunk_writer.py`.

### 3.1 How a site's served image is chosen (read at the source)

* The **site page** (`api/routes/sites_html.py`) and the country hub show the first `wiki_images`
  row of the site that is not excluded, `ORDER BY is_hero DESC, is_lead DESC, sort_order`
  (`gallery_audit.worklist.served_row`); the hub falls back to `unified_sites.thumbnail_url`.
* The **globe popup** (`SitePopup/gallery/useGalleryData.ts`: `heroImageOverride || thumbnailUrl ||
  wikiHero`) and the static export's `im` show `thumbnail_url` first.

A site therefore serves its served row on the page and its `thumbnail_url` on the globe. The lane
checks the page's image (or, without a live row, the thumbnail) and then points the thumbnail at
the checked image, so both show the same confirmed picture (`gallery_audit/decide.py` rule T1).

### 3.2 The pre-check is evidence, not a filter

`precheck.py` marks a served image **CONFIRMED** when its Commons file is the site's Wikidata image
(P18) or lies directly in the site's Commons category (P373) - read from WD1's harvest, the file's
categories asked of Commons once. The design sent only the unconfirmed images to the vision check.
**Measured before relying on it** (section 5): of the 10 served images the fresh acceptance
(`draw-2026-09-25b`, stage 1) judged WRONG, the pre-check CONFIRMS 8 - three by P18 (Thasos: a
satellite view of the island; Grabbist Hillfort: the town seen from the hill; Gilwern Hill: a
tramway) and five by P373 (an information panel at Kłopot, a ritual photo at Iximche, a moss
photograph at Mynydd Carningli, a mountain view, the Tayma stones in the Louvre). A pre-check
CONFIRMED is wrong about as often as the images overall, so **every served image goes to the vision
check** (`export-check --population all`, the default). `--population unconfirmed` is the original
design, kept as an explicit choice only. The pre-check's status travels with each decision as
evidence.

**This departs from the specification, which sends only the images the pre-check does not
confirm, and needs the orchestrator's (or the owner's) sign-off before the run**, recorded in
AUDIT_LOG: `all` checks about 4,084 served images (about 341 check batches of 12), `unconfirmed`
about 1,184 (about 99 batches) - measured populations of section 5. Without the sign-off, run
`export-check --population unconfirmed`: the plan then keeps a pre-check CONFIRMED image unchecked
(`plan.py`, `decide_site`).

### 3.3 The two Opus stages

* **served-check** (12 images per batch agent): `depicts` (the site itself, its remains, a drawing
  or reconstruction of it, or an object found there), `region_or_type` (region, landscape, town, a
  view from the site, a map, a generic example, a portrait, a museum object not from the site, a
  panel, plants or animals), `other_site` (a namesake, a neighbour, a comparison). The picture is
  the file production serves: a gallery row from the offsite copy of the image tree
  (`C:/PythonProjects/AncientMap-Offsite`, accepted only at the row's `file_size_bytes`; read on
  2026-09-26: no VPS image is newer than the copy), a thumbnail by its URL. A thumbnail whose
  address serves no picture but names a Commons file Commons still holds as a still picture is
  shown through that file's 1280 px rendering and carries a repair - that rendering's URL (all 262
  Commons `/thumb/` thumbnails ask a width Commons no longer renders - HTTP 400; 10 are the only
  image of their site). One whose file is gone, or is no still picture, is recorded `unfetchable`
  and goes to replacement.
* **served-replace** (candidates packed to at most 36 pictures per agent, a site never split): for
  every image the check did not call `depicts`, every other live gallery row (`G1`, ...) and the
  item's P18 and first 12 P373 files the gallery does not hold (`W1`, ...), each shown as a file.
  The agent gives each a verdict and picks the best one it called `depicts` - a `G` whenever one
  depicts the site - or none. A `W` file is shown - and stored when picked - as its 1280 px Commons
  rendering, and only when it is a still picture (`commons.picture_url`: JPEG, PNG, GIF, WebP,
  TIFF, SVG). `cmtype=file` lists every file of a category; measured on 2026-09-26, a PDF, a WebM
  and a DjVu answer a JPEG page or frame as their rendering and an MP3 or FLAC Commons' file-type
  icon, so the MIME type decides. A file that is no still picture, or whose rendering is not
  served, is listed under `unavailable` in `EXPORT_REPLACE.json` and never stops the export. The
  original is never stored: the first 12 originals of Category:Casa Grande Ruins National Monument
  are 9.0-20.1 MB each (measured 2026-09-26), a TIFF original no `<img>` can show.

### 3.4 The plan (`plan.py`) - one rule per outcome

| outcome | when | rows (rule) |
|---|---|---|
| confirmed | the check says `depicts` | `thumbnail_url` := the served row's local file if it names anything else (`wd2-align`); a repaired thumbnail := the rendering of its file the check was shown (`wd2-thumb`) |
| replaced | a `G` pick | hero flag off the old hero, onto the pick (`wd2-hero`); thumbnail := the pick's local file (`wd2-align`); every live row judged `other_site` - the served one by the check, a `G` by the replacement stage - excluded (`wd2-exclude`); a `region_or_type` row stays in the gallery |
| cleared | no `G` depicts | every live row (each judged: the served one by the check, the rest as candidates) excluded and unheroed (`wd2-exclude`); thumbnail := the confirmed `W` file's rendering the agent was shown, else NULL (`wd2-thumb`) |
| no image | the site serves nothing | nothing |

A live row nobody judged is never excluded (the plan refuses). Chunks of at most 100 sites; a
cleared site is named in its chunk as one that may lose its last live image.

### 3.5 Runbook

Order: after the scope review's waves (a retired site is not read), after L5 and WD1's harvest.
Before `export-check`: the orchestrator's sign-off on `--population all` (section 3.2), recorded in
AUDIT_LOG.

```bash
PY=./.venv/Scripts/python.exe
S=scripts/remediation/served_image/run.py
R=output/remediation/served_image/served-image-2026-09-27     # the date names the journal stamp
H=output/remediation/handoff/served-image-2026-09-27

$PY $S read --run-dir $R                        # production, read-only -> READ.json (written once)
$PY $S precheck --run-dir $R                    # WD1's harvest; refuses a shown site it lacks;
                                                # PRECHECK.jsonl/.json written once (a new harvest
                                                # is a new run directory, from `read` on)
$PY $S export-check --run-dir $R --handoff $H-check  # pins READ.json's and PRECHECK.jsonl's sha256
#   per batch B (check-001, ...; up to 16 agents at once):
$PY $S brief --run-dir $R --handoff $H-check --batch-id B    # the agent's full instruction
#   (the agent opens each picture with its Read tool, answers, runs check-answer, records with
#    opus_handoff.py answer)
$PY scripts/remediation/opus_handoff.py validate --dir $H-check
$PY $S import-check --run-dir $R                # -> CHECK.jsonl (unfetchable thumbnails included)
$PY $S export-replace --run-dir $R --handoff $H-replace   # prints "questions": N
#   only when N > 0 (with N = 0 no handoff exists; import-replace says so and `plan` goes on):
#   per batch: brief / check-answer / answer as above, then validate --dir $H-replace, and
$PY $S import-replace --run-dir $R              # -> REPLACE.jsonl
$PY $S plan --run-dir $R                        # -> chunks/chunk-NNN, EXPECTED.jsonl, PLAN_SUMMARY.json
```

`EXPORT_REPLACE.json` names, per site, every Wikidata file that was not shown (`unavailable`:
`missing`, `not a picture` with its MIME type, or `unfetchable` with the refusal) and every failed
image without a candidate (`without_candidates`) - those sites are cleared.

Per chunk, in order, each accepted with 0 deviations before the next:

```bash
CW=scripts/remediation/gallery_audit/chunk_writer.py
C=$R/chunks/chunk-001
$PY $CW $C --check               # offline: the files are the plan's, no DELETE
$PY $CW $C --rehearse            # APPLY.sql with COMMIT -> ROLLBACK against production
$PY $CW $C --apply               # the write, then the two-way read-back (plan = journal = data)
$PY $CW $C --readback            # read-only, again
$PY $CW $C --rehearse-rollback   # ROLLBACK.sql on the landed rows, rolled back
$PY $S accept --run-dir $R --chunk $C   # read-only: every site serves what the plan says
```

What the gates check: inside the transaction every planned site is curated, every image row lives
on its site and still holds its old value, exactly the planned rows move, at most one hero per site,
no hero on an excluded row, a site keeps a live image unless its chunk names it; the read-back
compares plan, journal and data both ways. `accept` re-reads production and names every site whose
served row or thumbnail differs from `EXPECTED.jsonl`, or that has two heroes or an excluded hero;
it exits 0 only with 0 deviations.

**Undo** of a landed chunk (after its `--rehearse-rollback` passed):

```bash
$PY - <<'EOF'
import sys; sys.path[:0] = ["scripts/remediation", "scripts/remediation/gallery_audit"]
from pathlib import Path
import chunk_writer as CW
d = Path("output/remediation/served_image/served-image-2026-09-27/chunks/chunk-001")
chunk = CW.check_delivered(d)
proc = CW.pv.run_psql((d / "ROLLBACK.sql").read_text(encoding="utf-8"), check=False)
print(proc.returncode, proc.stdout, proc.stderr)
print(CW.readback(chunk, rollback=True))     # [] = every row is back at its old value
EOF
```

**After the last accepted chunk - the card_stats recompute.** The chunks change a card input:
`has_thumbnail = bool(thumbnail_url)` (`api/cardgame/generator.py`, `site_card_stats`) turns false
for a site cleared to NULL and true for a site that had none and gets a `W` pick; `thumbnail_url`
is one of the card inputs (`mechanical/card_stats.py`, `INPUT_COLUMNS`). The image rows count as
before - an exclusion deletes no row, and the card counts every row. So a card_stats wave of its
own follows, through the mechanical lane like every card_stats wave (`card-stats-<label>`, a new
label):

```bash
CS=scripts/remediation/mechanical/card_stats.py
W=2026-09-27                               # a card_stats wave label no earlier wave used
$PY $CS --wave $W --export                  # production, read-only -> mechanical_card_stats/$W/export/
$PY $CS --wave $W --write                   # PLAN.jsonl, PLAN.md, SKIPPED.jsonl, BASIS.json, ROLLBACK.sql
L=card-stats-$W
```

then the gates of section 2.1 with this `L`, in the same order (`--check-primitive` ... `--rehearse-rollback`),
accepted with 0 deviations. `BASIS.json` and `ROLLBACK.sql` are the applied plan's only when they
come from the `--write` run that is applied (`card_stats.py`'s docstring).

After the chunks: the globe reads the static export, so the new thumbnails show with the next WF
export; the page and the hub read the database at once.

---

## 4. Tests and the mutation sweep

* `tests/remediation/test_served_image.py` - the read, the pre-check (written once, pinned by the
  check export), Commons (what a picture is, no rendering taken for the original), both stages,
  the thumbnail repair, the candidates (still pictures, unserved renderings listed), the plan
  (other sites out of a replaced gallery), the acceptance.
* `tests/remediation/test_scope_review.py` - the funnel, the answers (a site carries no quotes,
  the copies of Wikipedia), the rounds (in order, never empty, three asks at one premise, a moved
  entry asked again) and their quote check, the plan's guards (the latest answer decides), the
  waves, the wave lane and its read-back.
* `tests/remediation/test_t11.py` - T11's quotes of `dates.py` stand in `dates.py`.
* `tests/remediation/test_mechanical.py` - the scope-review wave runs through every generic lane
  test (`ALL_LANES`: apply, commit states, read-back, probes, identity) with a fabricated plan.
* `tests/pipeline/test_e3_oceania.py`, `tests/remediation/test_mechanical_scope.py` - section 1.
* `scripts/remediation/mechanical/mutation_sweep.py wd2` - every WD2 guard removed one at a time
  must turn its named test red (the group `WD2_CASES`, 84 cases; the last run's output is
  `output/remediation/mechanical/evidence/23_mutation_sweep_wd2.txt`). It rewrites the source
  files in place and restores them: run it on an otherwise idle worktree.

---

## 5. Measurements (read-only, 2026-09-26)

**How:** `served_image/run.py read` and `precheck` against WD1's harvest
(`.claude/worktrees/wd1/output/remediation/fields/harvest`, 5,004 sites, 4,633 with an item, 4,536
entities), run directories and a throwaway sample builder outside the repository
(`C:/tmp/wd2_measure/`). The sample: the 60 sites of `draw-2026-09-25b` plus the 140 other curated
sites with the smallest md5(site id), 198 of them shown.

| population | sites | serve an image | CONFIRMED by P18 | by P373 | unconfirmed | serve nothing |
|---|---|---|---|---|---|---|
| sample | 198 | 155 | 34 | 78 | 43 | 43 |
| every shown site | 4,926 | 4,084 | 794 | 2,106 | 1,184 | 842 |

So the pre-check confirms 112 of 155 served images in the sample (72 %) and 2,900 of 4,084 overall
(71 %). Against the acceptance's stage-1 verdicts on the same files: CORRECT 30 (27 CONFIRMED),
WRONG 10 (**8 CONFIRMED**), UNVERIFIABLE 1 (CONFIRMED). The served files are the ones the
acceptance asked about.

The thumbnails (every shown site): 2,246 local files, 1,416 Commons originals, 262 Commons `/thumb/`
renderings - every one at a width Commons no longer renders - and 24 on other hosts. Of the 157
sites whose thumbnail is all they serve: 133 Commons originals, 14 other hosts, 10 broken
renderings, no local file.

`export-check` of the sample (a throwaway handoff, no answers, no writes): 154 questions in 13
batches, 1 thumbnail recorded unfetchable (a deleted Commons file, HTTP 404), 1 broken `400px`
thumbnail shown through its file (Ayanis Kalesi, whose file is a photograph of Toprakkale).

**The scope review's funnel** (`scope_review.py export` and `export-round --round 0` into a
throwaway directory, WD1's harvest): 5,004 curated rows exported, **526 questions in 44 batches** -
signals `no-item` 362, `wikidata` 131 (mountain 74, island 23, cape 7, valley 6, rock formation 5,
forest 5, lake 4, peninsula 3, river 3, canyon 1, volcano 1, anomaly 1), `type` 56, `pending` 14
(a site can carry several). The Baltic Sea Anomaly, the three Bosnian "pyramids" and the Yonaguni
Monument are among them. Many `mountain` items are hillforts whose item is the hill - the agent
decides each; a wrong item is L5's to fix first.
