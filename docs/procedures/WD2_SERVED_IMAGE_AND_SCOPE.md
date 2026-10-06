# WD2 - the served image (O6) and the E3 scope with Oceania (O7)

Lane WD2 of the finishing plan (`output/remediation/FINISH_PLAN_2026-09-26.md`, workstream WD).
Owner decisions of 2026-09-26, binding:

* **O6** "Belegt ersetzen, sonst leeren": a served image that does not show its site is replaced
  only by an image a vision check confirmed; otherwise the site serves no image.
* **O7** "Ja, Ozeanien wie Amerika": Oceania is in scope through 1500 AD, like the Americas (E3).

Every model judgement is an agent answering through `scripts/remediation/opus_handoff.py`;
no pipeline code calls a model. Since the owner's decision of 2026-10-03 the answering agents
are MiniMax ones (`MiniMax-M3.1-Flash-Preview`, stamped
`minimax/MiniMax-M3.1-Flash-Preview (MiniMax Code agent)`); the answers of 2026-09-30 carry
their Sonnet stamp and stay valid. Every production write is journalled
(`remediation_change_log` through `apply_remediation_change()`) by an existing writer, in steps of
at most 100 sites, each accepted with 0 deviations before the next.

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

A site that serves **no** image is `no-image` and its item is never read: the pre-check stops there,
so the claim of such a site is not in `PRECHECK.jsonl` at all. `export-replace` reads it itself
(`wanted_files`) and asks about those files, which is the only place a claim of a site without an
image can be examined; the no-image report of section 3.5 reads the same claim for the same reason.

**This departs from the specification, which sends only the images the pre-check does not
confirm, and needs the orchestrator's (or the owner's) sign-off before the run**, recorded in
AUDIT_LOG: `all` checks about 4,084 served images (about 341 check batches of 12), `unconfirmed`
about 1,184 (about 99 batches) - measured populations of section 5. Without the sign-off, run
`export-check --population unconfirmed`: the plan then keeps a pre-check CONFIRMED image unchecked
(`plan.py`, `decide_site`).

### 3.3 The two vision stages

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
| no image | the site serves nothing | nothing; the measured reason is the answer's `basis` in `REPLACE.jsonl` |
| claimed | the site serves nothing, its item claims a file (P18/P373) and a claimed file was called `depicts` | thumbnail := the rendering the agent was shown (`wd2-thumb`) - the whole write, the site has no image row to move |
| unjudged | a claim-only plan, the site serves an image this run did not judge | nothing; the site keeps what the delivered run left it |

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
#   --claimed-only instead exports only the sites that serve no image while their Wikidata item
#   claims a file: for a run that does not re-judge the served images (they were judged and
#   delivered on 2026-09-30). It is refused while a judged image failed, its record carries no
#   check_sha256, and the plan then leaves every site that serves an image as "unjudged".
#   only when N > 0 (with N = 0 no handoff exists; import-replace says so and `plan` goes on):
#   per batch: brief / check-answer / answer as above, then validate --dir $H-replace, and
$PY $S import-replace --run-dir $R              # -> REPLACE.jsonl
$PY $S no-image-report --run-dir $R             # -> NO_IMAGE_REPORT.jsonl, NO_IMAGE_SUMMARY.json
$PY $S plan --run-dir $R                        # -> chunks/chunk-NNN, EXPECTED.jsonl, PLAN_SUMMARY.json
```

`EXPORT_REPLACE.json` names, per site, every Wikidata file that was not shown (`unavailable`:
`missing`, `not a picture` with its MIME type, or `unfetchable` with the refusal) and every failed
image without a candidate (`without_candidates`) - those sites are cleared.

### 3.6 The no-image report (`no_image_report.py`) - one measured reason per site

The goal asks for the no-image remainder to be reported **per site with its measured reason**, not
left open. This is the one clause no vision model can block, and it writes nothing outside the run
directory. A row per curated site that serves no image, plus one per retired curated site, with the
claim it was decided on, the state the export recorded for that claim, and a `detail` sentence in
words. `NO_IMAGE_SUMMARY.json` carries the counts that close over the read
(`curated = shown + retired`, `shown = confirmed + unconfirmed + no_image`) and
`addressable_remainder`, the number the goal counts down.

The five reasons, in the order they are decided: `no-wikidata-item` (the pre-check found no item),
`no-image-claim` (the item holds no P18 and no P373), `claimed-no-file-named` (the item names a P373
category and the category lists no file - `wanted_files` is the one reader, so such a site is
invisible to `export-replace`, which asks only about named files), `claimed-awaiting-vision-check`
(the claim named a file and the run exported candidates) and `claimed-no-file-is-a-picture` (every
named file is no still picture). Retired curated sites carry `retired`.

It refuses by name instead of counting: a claiming site the export does not list, a site the
export asks about that does not serve nothing, an export pinned to another pre-check, a shown site
without a pre-check row. The export is read exactly when a claim names a file.

Measured on production 2026-10-05 (run `served-image-2026-10-05`): of 5,004 curated sites 104 are
retired, 3,661 serve an image (2,722 the item vouches for, 939 it does not) and 1,239 serve nothing
- 307 without a Wikidata item, 688 with an item that claims no image, 4 whose category names no
file, 240 open. `claimed-no-file-is-a-picture` is reachable but measured 0.

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

### 3.7 The import-hero lane (WD2/IH) - the 2025 import's own link becomes the hero

Owner decision 2026-10-05, 17:43: the hand-linked image of the 2025 import comes back as the site's
hero. Not a fresh match against Wikidata - *that* picture, the one the owner linked himself.

`scripts/remediation/import_hero/` (`read`, `plan`, `verify`). One source, and it is the only
surviving copy of that hand-linked image:

```
data/raw/ancient_nerds/ancient_nerds_original.geojson   # 2025-12-18, 5,995 features, field Images
```

The loader wrote that field into `unified_sites.thumbnail_url` (`pipeline/unified_loader.py:1200`);
the remediation since replaced, demoted or hid most of those rows. The join (`plan.join_import`)
matches on the source URL first and on the folded title second - the same rule the period lane's
join proved - and carries the ambiguity as a flag instead of picking one.

**The five rules** (`plan.plan`, one `Change` each):

| rule | what it moves |
|---|---|
| `ih1` | the hero flag onto the row of the file the import links |
| `ih2` | the flag off the row that held it |
| `ih3` | an excluded row of that file becomes visible (the site's *first* picture) |
| `ih4` | `thumbnail_url` onto the row that now shows the hero |
| `ih5` | the row's `title`, `author`, `license`, `license_url`, `original_url`, `commons_page_url` and the file's size - all of them name the same file, so a row can never credit one picture while showing another |

`ih5` is why the shared writer's `WRITABLE` carries `title`, `license` and `license_url`: a fetch
that wrote the pixels but no attribution would leave a row crediting its previous file.
`PAGE_COLUMNS` (`pipeline/utils/public_sites.py`) is untouched - a test binds that set to the exact
SELECT the page renders.

**Two refusals, both named per site** in `IMPORT_HERO_REFUSALS.jsonl`:

* `local_file_too_small` - the row exists but its local derivative is under 1600x900. The plan takes
  a `fetched` manifest of 1600 px downloads (`import_hero/fetch.py` builds one entry per site: the
  eleven `FETCH_COLUMNS`, refused by name when the download does not carry all of them); without one,
  the site is refused rather than promoted onto a picture too small to show. Measured 2026-10-05:
  380 of the 807 already serve their import file and only lack the flag, 427 must replace the file
  first. The local name follows the owner's decision of that day: **the Commons name verbatim, only
  the extension becomes `.webp`** - production holds two conventions (26,027 rows named after a
  readable title, 18,746 after the Commons name), and the name is public, so the wave picks one
  instead of adding a third. The file lands in the offsite copy of the image tree, which this lane
  reads as the picture (section 3.2), and the VPS copy has to follow it - the two must not drift.
* `no_target_row` - no row of that site holds the file. 133 of them have no row at all and 59 link
  no Commons file, so no row can be named; those two groups are the owner's `thumbnail_url` decision,
  not gallery rows. The remaining 410 need an INSERT, which this writer does not do
  (`chunk_writer.lint_statement` refuses INSERT; `apply_remediation_change()` is UPDATE-only).

**The INSERT wave, applied 2026-10-06** (runs `-006`, `-007`, `-008`). Measured on the read
`9a5c3b28…` (4,900 shown sites, 47,691 image rows):

* **The fetch: 417 targets, 147 files, 270 refusals by name.** The 476 `no_target_row` sites split
  into 150 that carry no image row at all (the owner's decision of 2026-10-05, 18:32 — 57 of them
  were downloaded before the insert plan refused them, because the fetch's target rule is coarser
  than the insert plan's), 236 whose file never arrived, and 90 that got a row. All 147 files were
  verified against their manifest on the offsite tree, packed, transferred and verified again inside
  the api container: **147/147, 0 missing, 0 size mismatches**, the served tree at **50,239 `.webp`**.
* **The wave: 87 rows over 2 chunks, 1,376 journal rows**, both chunks through the five steps of
  section 3.6 (`insert_writer.py`, the shared writer's five commands over a statement that creates
  a row), acceptance `ok: true`, **87/87 on all three questions** (read `13bb095a…`).
* **Three sites needed no row at all.** `no_target_row` compared the *title in the import's link*
  with the stored row's name, and Commons' upload slugs differ from the file's title for reasons of
  its own: `The_East_Facade_pf_the_Parthenon…` (a typo in the import) for `…_of_the_…`,
  `East_Terrace_(4961323529).jpg` for `Mount_Nemrut_-_East_Terrace_(4961323529).jpg`, and one title
  that gained `zyklopenhaftes`. All three sites *hold* the file - the fetch resolved the link to the
  same `original_url`. So `plan._target_row` now matches on the resolved upload URL when the fetch
  has one, which is the same key the unique constraint `(site_id, original_url)` holds, and the
  insert plan refuses such a site as `already_holds_the_file`. The three got the hero lane's `ih1` +
  `ih4` instead (run `-007`).
* **A rule that had to be corrected because the acceptance refused it:** `ih4` took the *fetched*
  file name whenever a fetch existed, even where `ih5` never rewrote the row. On those three sites
  that pointed the thumbnail at a file nobody had ever fetched. The thumbnail now names the row the
  site serves, and takes the fetched name only where the wave renames that row (run `-008`, 3 rows,
  acceptance `ok: true`). The acceptance learned the same identity: with the fetch manifest it
  accepts a served row by its upload URL instead of the slug in the import's link.

**Three columns the fetch does not carry, measured on production 2026-10-06:** `wiki_images`
declares `is_lead`, `sort_order` and `source_type` NOT NULL without a default, so the insert
statement has to write them. `sort_order` is derived (the next free number of that site), `is_lead`
stays false (the import's link is the owner's picture, not a measured lead image) and `source_type`
is `wikimedia`, which 49,683 of the 49,691 curated rows carry. The journal therefore carries
**fourteen** rows per inserted site, not eleven.

**A site whose every row is hidden today** is named `may_empty` in its chunk header
(`Planned.may_empty`), not excluded from the wave: unhiding the row gives it its *first* picture,
which is not a hero move, and a reversal that restores "no image" is a faithful undo the writer's
guard would otherwise refuse (measured 2026-10-05: 35 of 1,555 sites, and the pilot's 3 of 100 that
made `--rehearse-rollback` stop). The guard stays strict; the exception is on the record.

**What the wave is proven at, in four layers** (measured 2026-10-06): the acceptance's 87 of 87 on
a fresh read; 147 of 147 files verified against their manifest inside the api container; **87 of 87
files over HTTP - `200`, the manifest's exact `Content-Length`, `image/webp`, including the 78 whose
file name carries a space**; and 8 of 8 sampled site pages naming the inserted file. The last layer
is the one that catches what the container check cannot: a name nginx refuses or a URL a browser
mangles. The canonical page form is the one `sitemap-sites.xml` lists,
`/sites/<country slug>/<name slug>-<site_id[:8]>`; `sitemap-sites.xml` holds exactly 4,900 URLs, the
shown curated sites.

**The acceptance** (`import_hero/verify.py`) asks production, never the plan: for every site of the
wave's chunks, does the page serve the file the import links, does the thumbnail name that row, and
is there exactly one live hero row. It writes `ACCEPTANCE.json` and names every site that fails a
question. `served_image/run.py accept` is the other acceptance and asks a different question
("does production equal this lane's `EXPECTED.jsonl`"); the import-hero lane writes the shared
writer's `PLAN.jsonl` and no `EXPECTED.jsonl`, and its question is the owner's - is *this* picture
the one on the page.

```bash
PY=./.venv/Scripts/python.exe
R=output/remediation/import_hero/import-hero-2026-10-05-002
IH=scripts/remediation/import_hero
# 1. read production (read-only) -> READ.json, and the join -> IMPORT_CLAIMS.json
# 2. plan (read-only, writes only into the run directory) -> chunk-001..016/,
#    IMPORT_HERO_REFUSALS.jsonl, IMPORT_HERO_SUMMARY.json
# 3. per chunk, the writer's five steps in section 3.6's order, each accepted with 0 deviations
# 4. acceptance over all chunks -> ACCEPTANCE.json
```

Applied 2026-10-05 (`c4976a9`, `b5aa98c`): 1,555 sites, 4,642 rows, 16 chunks, 35 `may_empty`,
1,555 of 1,555 on all three acceptance questions (read `0e62aea4…`, 2026-10-05T17:58:27Z). Replanning
the same lane over a fresh read yields **0 rows** (`REMAINDER.json`, run `-003`) - the lane is at its
end, and what it still refuses is 807 `local_file_too_small` + 469 `no_target_row`, both by name.

Applied 2026-10-06: the 807 `local_file_too_small` first (runs `-004`, `-005`: 310 sites fetched and
accepted 310 of 310), then the INSERT wave (runs `-006`, `-007`, `-008`, above). After all of it the
read of run `-008` counts **4,900 shown curated sites, 1,344 of them without a live hero, 0 sites
with two**, 47,778 image rows and **583 live heroes still under 1600x900** (552 after this wave: 31
of them lost the flag to a fetched 1600 px row). Both of those counts move again in §3.7.2, where the
owner lowered the floor for 243 sites.

**The thumbnail question, asked properly** (2026-10-06): of the shown curated sites with a live
hero, **all 3,556 name the served row** - the T1 rule holds everywhere it is visible. A first
measurement without the `scope_status IS DISTINCT FROM 'retired'` filter reported "54 sites whose
live hero's thumbnail points somewhere else" (32 remote `upload.wikimedia.org` URLs, 22 a local
path naming another file); **all 54 are `retired`**, which the site does not render. A number that
reads like a defect and is not one usually means a filter is missing, not that the database is
wrong.

### 3.7.1 What is left, and why each class cannot be closed from here (measured 2026-10-06)

"Without a live hero" is the stricter question than "shows nothing". `served_row()`
(`ORDER BY is_hero DESC, is_lead DESC, sort_order` over the rows that are not excluded) is what the
page actually serves, so a site with rows but no hero flag still shows its lead row. The four
numbers that describe the finished state, over the 4,900 shown curated sites:

| the page… | sites |
|---|---:|
| serves a gallery row | **3,578** |
| serves only its `thumbnail_url` | 153 |
| **serves nothing at all** | **1,169** |
| shows two heroes at once | 0 |

(Before the floor wave of §3.7.2; after it, measured with the same script over the same question:
3,616 / 140 / 1,144 / 0.)

The 1,169 split by cause, and why no write closes them from here:

* **852 carry no image row at all.** 150 of them are the owner's decision of 2026-10-05 (18:32) -
  a site with only a `thumbnail_url` gets no gallery row made up out of nothing; the other 702
  never had one either. Nothing to serve means a **new picture** is needed: that is the candidate
  search (`import_claims`, P373 categories) and its vision stage, not this writer.
* **317 have rows, and every one of them is excluded** (171 sites one row, 54 sites twenty). Those
  exclusions are the vision lane's recorded decision (`remediation_change_log.test_id =
  'WD2/served-image'`, run stamps `served-image-2026-09-30-*`, 2,072 rows over 354 sites). These are
  exactly the sites rule `ih3` unhides when the import's picture *is* one of their rows - and after
  the waves above it unhides not one of them, so for these 317 the import's picture is no row of
  the site. Un-doing a model's judgement without a new judgement is not a thing this lane may do.
* **The 270 refusals of the INSERT fetch, by class** (`FETCH_FAILURES.jsonl`, counted by pattern):
  213 the Commons original is itself narrower than 1600 px (a fetch cannot deliver pixels the file
  does not have), 15 without `author_url`, 12 without `license_url`, 11 panoramas 1600 px wide and
  under 900 px high, 9 Commons hosts no file of that name at all (one API call over all nine
  confirms every page answers `missing`, e.g. `File:Thul Hairo Khan.jpg`), 5 without `author_url`
  and `license_url`, 3 whose name carries a character the served tree may not hold, 1 without author
  and `author_url`, 1 an SVG. **Only the last three are our own rules**, and they would buy 4 sites
  at the price of a naming convention no other site uses; the other 267 are facts about the files.

The 583 live heroes under 1600x900 are the same story from the other side: their row holds the
owner-linked picture, but the Commons original of that picture is narrower than the lane's floor.
Both numbers are floors this lane set itself, and raising either is a decision, not a fix.

**The list behind those numbers**: `output/remediation/import_hero/RESTBESTAND_2026-10-06.jsonl`,
1,169 lines, one per site, with its class, the rows it has, what the 2025 import links, what the
import-hero lane refused it for and **what would close it**; the counts are in
`RESTBESTAND_2026-10-06_SUMMARY.json`. The four closers, measured per site and not assumed:

| what would close it | sites |
|---|---:|
| `no_picture_at_all` - the import links nothing, and none of these carries a wikidata id | **1,081** |
| `import_picture_is_no_row` - the import links a picture that is no row of the site | 36 |
| `import_picture_never_fetched` - such a picture, refused by the fetch (`FETCH_FAILURES.jsonl`) | 26 |
| `import_picture_too_small` - the picture is a row, but its local file is under 1600x900 | 26 |

A count is a fact about today; that file is what the next campaign works from.

### 3.7.2 The floor the owner lowered (2026-10-06), and exactly what it released

Owner decision, 2026-10-06: *"for these cases the existing picture becomes the hero"* - the size a
local file must reach comes down for the sites that already have a picture. **The floor is a run
parameter, not a second constant**: `run.py plan|fetch --min-width W --min-height H`, written into the
run directory as `FLOOR.json` and read back by every later step of that run, because a plan at one
size and a fetch at another would refuse exactly what the other accepted (`_floor_of`, `run.py`).

The pair is measured, not chosen: of the sites the lane refused as `local_file_too_small`, **every
one holds a row of at least 800 px width and none below**, and the smallest of their heights is
337 px (800x600 and taller for the rest). So 800 px of width clears all of them and no width below
800 would, and the height has to travel with it - hence **800x300**.

Run `-009` (`FLOOR.json`, `IMPORT_HERO_SUMMARY.json`, `ACCEPTANCE.json`, `chunk-001..003`):

* planned **243 sites / 727 rows** in 3 chunks, applied with the five writer steps each
  (299 + 299 + 129 rows), **accepted 243/243/243/243** on the fresh read `d0c3852a…`
  (2026-10-06T16:16:41Z), 0 problems, and **243/243 serve the file over HTTP with the exact
  `file_size_bytes` of their row** (23 of those names carry non-ASCII characters and need URL
  quoting before a request leaves the process - that is a fact about the check, not the site).
* What the floor actually released, counted per promoted row: **131 at 800 px width, 111 at 1600 px,
  1 at 1599 px**. The 112 sixteen-hundred-wide rows were refused only by the *height* half - they are
  1600x600 up to 1600x899, not small pictures. A floor of width alone would have left them stuck
  behind a rule whose own purpose is to keep strip images out.
* **The lane's own floor is empty**: replanning the same read at 1600x900 yields **0 rows / 0 sites**,
  and **every one of the 243 was refused at 1600x900 as `local_file_too_small`** - 0 exceptions. The
  wave is the whole remainder of the hero lane, not a selection from it.
* **Still refused at the owner's floor, by name**: 7 sites, all of them 800 px wide and **177-298 px
  high** (row ids 60884, 73893, 76407, 83714, 93021, 99542, 102572). A 800x177 strip is not a
  picture of a site, and the owner named a width; the height is this lane's own rule and it stops
  there.

Effect on the numbers of §3.7.1, the same script over the wave's two reads (a row counts as served
when it is neither `is_excluded` nor `scope_status = 'retired'`; both columns total 1,284 sites
without a served row, the §3.7.1 table's 153 + 1,169 total 1,322 - one site sits on the other side of
the bucket boundary there, so the two are not to be subtracted):

| over the 4,900 shown curated sites | read `-009` | read after `-009` |
|---|---:|---:|
| serves a gallery row | 3,578 | **3,616** |
| serves only its `thumbnail_url` | 152 | 140 |
| **serves nothing at all** | 1,170 | **1,144** |
| shows two heroes at once | 0 | 0 |
| live hero under 1600x900 | 552 | 772 |
| live hero under **800x300** | 22 | **19** |

The hero count under the lane's own floor *rises*, and that is the point: 243 heroes now point at the
picture the 2025 import hand-linked, 131 of them the 800 px derivative. Under the owner's floor it
falls. Of the rest inventory this wave closed **26 of 26 `import_picture_too_small`** and 12 more
that already had a row (`ih3` unhides the only row of a site that showed nothing). Untouched, because
they need a new picture rather than a lower bar: **1,081 `no_picture_at_all`**, 36
`import_picture_is_no_row` and 26 `import_picture_never_fetched` for the INSERT lane.

```bash
PY=./.venv/Scripts/python.exe
IH=scripts/remediation/import_hero
CW=scripts/remediation/gallery_audit/chunk_writer.py
R=output/remediation/import_hero/import-hero-2026-10-06-009
$PY $IH/run.py plan --run-dir $R --min-width 800 --min-height 300
for C in $R/chunk-001 $R/chunk-002 $R/chunk-003; do
    $PY $CW $C --check --rehearse --apply --readback --rehearse-rollback
done
$PY $IH/run.py accept --run-dir $R
```

```bash
PY=./.venv/Scripts/python.exe
R=output/remediation/import_hero/import-hero-2026-10-06-006
IH=scripts/remediation/import_hero
# the INSERT wave: the fetch (resumable), the plan, the writer, the acceptance
$PY $IH/run.py fetch         --run-dir $R --root $OFFSITE --target insert --start
$PY $IH/run.py insert-plan   --run-dir $R
$PY $IH/insert_writer.py $R/chunk-001 --check --rehearse --apply --readback --rehearse-rollback
$PY $IH/run.py insert-accept --run-dir $R
```

**The static export is not part of this.** A hero or licence change dates the rendered page
(`pipeline/utils/public_sites.py`), so the globe shows the previous picture until the next export
run; the page and the hub read the database at once and already show the new one.

---

## 4. Tests and the mutation sweep

* `tests/remediation/test_served_image.py` - the read, the pre-check (written once, pinned by the
  check export), Commons (what a picture is, no rendering taken for the original), both stages,
  the thumbnail repair, the candidates (still pictures, unserved renderings listed), the plan
  (other sites out of a replaced gallery), the acceptance.
* `tests/remediation/test_import_hero.py` - the import is read with its keys, the join (URL first,
  folded title second, ambiguity kept), every rule `ih1`-`ih5`, both refusals by name, the fetch
  manifest's whole `imageinfo` answer, `may_empty` (a site that shows nothing today is named, a site
  with a live image never is), the chunk writer's five steps, and the acceptance's three questions
  including the thumbnail that names the old row and the hidden row that a thumbnail alone does not
  excuse.
* `tests/remediation/test_import_hero_insert.py` - the insert plan's refusals (`no_row_at_all`,
  `not_fetched`, `already_holds_the_file`), the statement's five guards and three invariants, the
  journal read back from the row it created, the reversal's DELETE naming the triple the lane wrote,
  the lint's two shapes, and the acceptance.
* `tests/remediation/test_import_hero_slug_match.py` - a Commons slug that differs from the file's
  title: the plan finds the row through the resolved upload URL, the insert plan refuses it by name,
  `ih4` names the row the site serves, and the acceptance takes the same identity.
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
