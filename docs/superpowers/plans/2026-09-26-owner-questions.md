# Studio build: questions for the owner (collected, asked only on request)

Owner rule (2026-09-26): collect questions during the build and present them only when the owner
asks. Until then the build takes the spec's or the recommended path and records the choice here.
Compliance items (Mapbox video rights, quotation rules, music licence, Remotion headcount) are parked
in spec §9 by owner decision and are not asked.

## Decided 2026-09-26 (first round)

| # | Question | Owner decision | Consequence for the build |
|---|---|---|---|
| 1 | Disk C: 20-27 GB free: may old worktrees go? | massrun now; globeload after its baselines are saved; remediation worktrees when the lane is done | `AncientMap-massrun` removed (clean, commit on main, snapshot identical to the main checkout): 33 GB free. |
| 2 | Theo run `afe7c26a` (old code) auto-publishes an M3 paper | Let it publish | Left alone. |
| 3 | pypdf into the shared venv | Install | `pypdf==6.19.0` installed. |
| 4 | Who starts the weekly writing session? | The owner (`/theo-write`) | The `theo-write` skill is started by hand; no scheduler is built. |
| 5 | `DISCORD_WEBHOOK_URL` | Not for now | Notices stay in `thinking_log` (the spec's unset path); nothing else to build. |
| 6 | UFO/UAP paper Roswell date (7 vs 8 July 1947) | Via the corrections log after go-live | Add to the acceptance steps: first real `theo_publish --correct`. |
| 7 | Channel | Same channel as the site Shorts | Package/description need no channel switch. |
| 8 | Cadence | Weekly ~12-15 min + 3-5 Shorts as trailers | Shorts derivation stays out of scope for this build (spec §9), noted for later. |
| 9 | Video release gate | **Final video only** (no separate script approval) | The `studio-video` skill runs case file -> script -> render -> package without stopping for the owner; the owner reviews the final package before the manual upload. |
| 10 | YouTube upload + retention measurement | Manual for now | Upload off, `register-youtube` records the id afterwards (as specified). |
| 11 | First full episode | Owner decides later | Acceptance (c) renders only the Baalbek claim-5 slice. |
| 12 | Community loop ("You asked") | Decide later | Not built. |

## Decided 2026-09-26 (second round: questions collected by the plan checkers and fixers)

| # | Question (checker ids) | Owner decision | Plans to change |
|---|---|---|---|
| 13 | Video poster on the paper page (evidence, fix:A/B/C) | **Own studio thumbnail as poster** (served from our server, no YouTube request before the click) | A: optional `poster` in C6 `--register-video`, checked against `research-images/<request_id>/video_<youtube_id>.jpg`; C: `register-youtube` uploads `package/thumbnail_1280.jpg` and sends the key; B: poster `<img>` in PaperVideo; spec 2.7 |
| 14 | Type B world distribution (registry-5, fix:D) | **Globe distribution take** (globe turns once, named places as labelled pins, the rest as small dots projected per frame) | as planned in D |
| 15 | Source of the distribution dots (registry-1, capture-1) | **From our database by `site_id`** (curated coordinates, the same the globe shows), not a full case-file place per dot | C: case file/capture spec accept `site_ids` for dots, resolved locally from the repo-root `public/data` site export (no network, no DB); D: distribution take draws them; spec 4.5/4.10 |
| 16 | TDM-reserved sources (spec-C: 2.3 vs 3.5) | **Cite them like any source and read them live for the fact check**; only the automatic archive completion keeps skipping them (the automated full-text fetch is the part the EU TDM opt-out covers) | A: archive completion unchanged (skip + record reason); C: fact check reads TDM-reserved sources live, no "re-source or remove"; spec 2.3/3.5 |
| 17 | Legacy rewrite: URL (publish-15, spec-A) | **Slug and published_at stay**, via `paper correct --republish` (journalled, full gates) | as planned in C |
| 18 | Legacy rewrite basis for the 28 papers without a dossier (dossier) | **Owner decides per paper at rewrite time**; both paths stay (fresh Theo run, or `--report-file` without dossier) | as planned |
| 19 | Founder-published papers on republish (publish-2) | **The founder stays credited as publisher** (`published_by` unchanged on republish) | A: republish keeps `published_by` |
| 20 | Republish of a paper with corrections (fix:C) | **Build now**: the studio fills `result.corrections` from the published log | C |
| 21 | Notice on republish (fix:A) | **Same `paper_published` notice as a first publish** | A |
| 22 | Theo host scripts (fix:A, ownership) | **Retire them** (`entitaet_research_host.py`, `smoke_theo_host.py`, `theo_ab_compare.py`, `theo_test_run.py` + their tests/docs refs) | A |
| 23 | AI disclosure in the Medium copy (spec-B) | **No**: the disclosure line stays on the paper page only | B: make sure the Medium copy does not get it |
| 24 | Thumbnails (render, confirm1:render) | **3 candidates for YouTube's A/B test + `episode thumbnail SLUG --frame N`**; never show the answer | C: CLI + package (`thumbnail_1..3`); D: still.ts per candidate |
| 25 | Thumbnail text | **Short teaser, 2-4 words** (question/riddle, NERV style, never the answer) | C: script field + validator; D: Thumbnail composition draws it |
| 26 | Hook caption punctuation (timeline-1) | **Shown** inside multi-word lines | as planned |
| 27 | Selected-site label in video mode (spec-D-8) | **Stays visible**; only hover tooltips are hidden | as planned |
| 28 | Platform recording sharpness (spec-D-7) | **1.5x zoom cap is enough** | as planned |
| 29 | Age-filter platform moment (spec-D-1) | **No** | nothing to build |
| 30 | Full-episode spine check (fix:C) | **Strict** (slices exempt) | as planned |
| 31 | Type C orders of magnitude (confirm1:registry) | **Linear only, never a log axis** ("logarithmisch versteht niemand und ist nicht sehr bildlich"): UnitGrid up to 1:400; beyond that a linear zoom-out block (Powers-of-Ten style: the small quantity drawn readable, the camera pulls back linearly until the large one fits, the small one shrinking to a dot) | D: replace the log10 BarChart by a linear ScaleZoom block; C: registry/validator reject log scales; spec 4.10 |
| 32 | Non-Latin scripts in type D (confirm1:registry) | **Glyph check only on strings that are actually drawn**; original quotes inside source screenshots are allowed | C + D |

Not asked (owner: no disk topics): the leftover Remotion bundles in `%TEMP%` from verification runs are the build's own garbage and are removed once no render runs.

Notes after the second round:
- #2 is moot: another session stopped Theo on the owner's behalf (`THEO_WORKER_DISABLED=1` since
  ~18:20 UTC on 2026-09-26, 24 batch rows paused, `afe7c26a` killed).
- #20 is met by plan A's C5 rule: the stored corrections log carries over server-side, so a republish of
  a corrected paper works; the studio sends `corrections: []` (A refuses a filled field).

## Open (new questions from the build go here)

| # | Found | Question | What the build does meanwhile |
|---|---|---|---|
| Q1 | 2026-09-26 (index) | Theo is stopped. Acceptance 8.4(b) (first dossier after the swap, written and published by Claude) needs one research-only run on the new image. May the orchestrator re-enable the worker after the deploy and requeue exactly one row the owner names, or does (b) wait until the owner restarts Theo? | Worker stays disabled; (b) and A26 Step 4 are reported as not run. |
| Q2 | 2026-09-26 (index) | Poster (#13) with three thumbnail candidates (#24): which candidate becomes the paper-page poster? | `register-youtube` requires `--poster 1\|2\|3` (the candidate set on YouTube, or the A/B winner). |
| Q3 | 2026-09-26 (index) | #20 was overtaken by A's server-side corrections carry-over. Keep A's rule? | Kept; the studio does not fill `result.corrections`. |
| Q4 | 2026-09-26 (index) | The local site export (`public/data/sites/`) is from 2026-03-26, before the sites remediation; the worktree has none. Download the current export read-only from production for captures and the #15 dots? | Download read-only into the worktree's gitignored `public/data/sites/`; `doctor` reports its age. |
| Q5 | 2026-09-26 (index) | Acceptance (a)'s dry run uploads the rewritten 95fa3798 paper's images to production `research-images/95fa3798…/` (content-hash names, unlinked, gitignored). Leave them? | Left in place (a later real rewrite reuses them). |
| Q6 | 2026-09-27 (converge) | #31 ScaleZoom: a strictly linear camera pull-back shrinks the small quantity to a dot within ~15 frames at 1:6,000. Alternative: a Powers-of-Ten pull at constant zoom speed (every frame still one linear scale, no log axis). | Strictly linear pull, as decided. |
| Q7 | 2026-09-27 (converge) | A founder publishing a Claude-written paper via the founder route: `writer.published='manual'`, `human_review=true`, so the disclosure says an editor reviewed and published it. Keep? | Kept. |
| Q8 | 2026-09-27 (converge) | Legacy rewrites via `--report-file`: only with an explicit `--rewrite` flag is the Claude writer stored, the disclosure shown and the notice sent; a small fix (Roswell) goes without it. | Explicit flag. |
| Q9 | 2026-09-27 (converge) | #16: may an evidence quote on the paper page come from a TDM-reserved source's live text (kept local)? | Yes (otherwise such paragraphs get no `#ev-NN` anchor). |
| Q10 | 2026-09-27 (converge) | A research-only run whose dossier was used to republish a legacy paper ends as `cancelled` ("dossier used by the republish of …"), leaving the list and the cap. Alternative: completed, not public. | Cancelled. |
| Q11 | 2026-09-27 (converge) | #15: distribution dots only from curated `ancient_nerds` sites, or any exported id (~1.9 M)? | Curated only. |
| Q12 | 2026-09-27 (converge) | #32: non-Latin source pages: the page title is recorded but not drawn; the credit shows only the ASCII hostname. | Hostname-only credit. |
| Q13 | 2026-09-27 (converge) | #25 layout: teaser top left on dark glass (1440x380 at y 72, green edge bar), upper-case Orbitron 104 px, max two lines; credit line bottom left. | This layout; the owner sees it in the final package review. |
| Q2+ | 2026-09-27 (converge) | `register-youtube` always requires `--poster K`, even without a linked paper. | Required for uniformity. |
| Q4+ | 2026-09-27 (converge) | After the merge the studio would resolve dots from the main checkout's stale export; the runbook refreshes it read-only (`curl -sfR … https://ancientnerds.com/data/sites/index.json`) before the first distribution capture. | Runbook refresh; `doctor` reports the age. |
| Q14 | 2026-09-27 (D Task 2 review) | The site's JetBrains Mono subset files lack the dot-below and breve-below letters of Hittite, Egyptian, Sanskrit and Semitic transliteration (`Ḫ Ḥ Ṣ Ṭ Ṛ Ṃ Ṇ Ḍ Ṯ Ḏ Ẓ`, `ʾ ʿ`), the hyphens U+2010-2012 and `‰`; Chrome would draw them in a Windows system font. Cormorant Garamond has most of the letters, JetBrains Mono and Orbitron do not. Load an extra JetBrains Mono build that has them (the site's CSS stays unchanged), or keep refusing them (scripts write `Hattusa`, `Hathor`, `Krishna`)? | Refused: the glyph rule is the files' cmap (`DRAWABLE`, plan D Task 2), and `episode check` names the character. |

Applied since the second round: #22 (host scripts retired, plan A Task 10/13b) and #23 (no disclosure in the Medium copy, plan B Task 3 assertion).
