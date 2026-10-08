# Owner decisions of 2026-10-08 (Martin): the final DB repair and the shorts-teaser cards

Asked interactively on 2026-10-08 after the read-only state audit `wf_eb1f1425-c3e` (local record:
`output/remediation/state-2026-10-08/README.md` in the main checkout, gitignored). Each answer is
the option the owner selected; "(rec)" marks where it was the recommended option. These supersede
every earlier record they contradict - named where it matters.

Owner's request that started it (verbatim): "wir müssen alle kartentexte neu schreiben, sie sollen
ein teaser für die site sein, mysterious aber natürlich korrekt. ... dieser kartentext soll dann für
Youtube shorts genutzt werden ... highest retetion ... ich will dass die viewer mehr über die site
wissen wollen und dann in der description zu unserem link zu ancient nerds zu der site gelangen.
aber ich will das nicht im short sagen. sie sollen es von selbst wollen!"

Mid-session (verbatim): **"die shorts videos aber noch nicht herstellen!"** - no render, no upload,
no OAuth setup until the owner says so. The Shorts decisions below (D26-D34) are recorded for later.

## Card texts

| # | question | decision |
| --- | --- | --- |
| D1 | Site name in the card text | **Never** (rec): no name form, alias or country; the Short reveals "Name, Country." Supersedes CARD_DESCRIPTIONS.md 1.3/1.4 (name required) and the AUDIT_LOG note of 2026-10-07 "the cards stay plain factual prose". |
| D2 | Length | **160-190 characters as before** (rec), O4 stands. |
| D3 | Thin descriptions | **Enrich first** (rec): sourced sentences via WN mechanics; if still too thin, the card stays empty; never padding; such a site gets no Short. |
| D4 | Sourced hook material | **Yes, for the Shorts-pool sites** (rec, ~2,300 with enough images): one sourced open question per site with a verbatim quote, added to the description, so the page pays the hook off. |
| D5 | Old March cards (1,877 live) | **Leave them** until a new card replaces each (not cleared; O6 is not applied to them now). |

## Models and process

| # | question | decision |
| --- | --- | --- |
| D6 | Models | **Claude only, "balanced"** (rec, after the owner asked for an Opus/Sonnet/Haiku mix): orchestration Opus 5.5 high; card writer (3 variants) Opus high; hook rating Opus medium; fact checker Sonnet 5.5 high; web verifier Sonnet high; period/field research Sonnet high; adversarial re-check Opus high; image prefilter (photo/map/text) Haiku 5.5 low; image "shows this site" Sonnet medium; code building Sonnet high; code review Opus high; pilot verdict/audit Opus xhigh; operators Haiku low. Every role passes a calibration against already-judged cases with a threshold sealed before the run; a failing role moves up one tier (Haiku -> Sonnet -> Opus). The answer stamp always names the real model. Supersedes the 2026-10-03 MiniMax-Code rule for this work. |
| D7 | Orchestrator | **This Claude Code session** (rec), via workflows and scripts. |
| D8 | Autonomy | **Fully autonomous**: production writes and deploys without asking, each journalled, rehearsed, rollback rehearsed, accepted with 0 deviations; pilots judged by the Opus pilot judge; final report at the end. |
| D9 | Order | **Parallel** (rec): card contract and pilot on the verified-basis sites now, beside the DB repair. |
| D10 | MiniMax writes after a failed calibration (WD3/WD4 715 rows at 361 sites; the 167 cards of 2026-10-07) | **Re-check all with Claude** (rec); what fails is rolled back or corrected through the journal. |
| D11 | AI notice on the site page | **Leave it off** (the 2026-10-07 removal stands, also for the 2,080 AI-written descriptions; the owner carries the EU AI Act Art. 50 risk). The CC BY-SA attribution line and the Shorts description note are unaffected. |

## DB repair

| # | question | decision |
| --- | --- | --- |
| D12 | Rule-made periods (1,260) | **Re-research** (rec): the quote checker learns BP / "years ago"; all rule sites re-researched (caves and the Americas first); unsourced -> "Undated"; the origin of every period marked in raw_data. |
| D13 | Records that describe a modern town/village | **Re-target to the ancient site** (rec): name, Wikidata/Wikipedia ids, description and gallery per site; the old name stays a searchable alias. |
| D14 | Duplicates (~27 pairs) | **Merge** (rec): judged survivor, loser retired (journalled), images and links moved. |
| D15 | 47 heroes judged other_site | **Re-check, then swap** (rec): a Claude checker looks at each; confirmed other_site -> excluded, the best depicts row becomes hero. |
| D16 | Vision check of galleries | **Only at render time** (deferred with the Shorts; the site galleries stay as they are). |
| D17 | 952 sites without any image | **Research all 952.** |
| D18 | Image credit rule | **Author + licence URL suffice** (rec, no author_url needed); backfill the author for the 419 rows without one from Commons. |
| D19 | Coordinates | **Relax the guard + research** (rec): a point within ~2 km off its country's coast counts as in the country; write the 23 refused points; re-research the 430 unsourced; unsourced keeps its point and goes to the owner list; such a site gets no Short. |
| D20 | Scope (116 after the window, 5 pending, Hadrian's Wall Path) | **Check and retire autonomously** (rec): a wrong period is corrected (sourced), a truly out-of-window site is retired (journalled); rule periods re-researched first. |
| D21 | Disputed sites (Pantelleria monolith, Baltic Sea Anomaly, ...) | **Show the dispute** (rec): the description names both positions with sources; the card asserts neither. |
| D22 | 28 sites without a description | **WN again, else stays empty** (rec): no card, no Short. |
| D23 | Reveal name | **Both** (rec): broken/foreign names cleaned to the English name (journalled, old name kept as alias) and a separate short spoken name for the Short. |
| D24 | Backups A4/A5 | **Cross-copy suffices** (rec): workstation <-> VPS copies with sha256 on both sides, set up as a routine; A4/A5 dropped. |
| D25 | Smaller items | **All by recommendation, autonomously** (rec): repair the 141 web-contradicted description sentences; finish WC on the 1,121 unverified texts; automate the static export; render the card file from the DB instead of the boot import; recompute card_stats; fill the dead card_stats columns from the Wikidata ids; repair the 82 stale Wikipedia ids; merge the site_type vocabulary; parent_site_id for component sites; archive the 16 old renders; the final error-rate measurement (WF); update the docs. |

## Shorts (recorded for later - not produced now)

| # | question | decision |
| --- | --- | --- |
| D26 | Route to the site page (Shorts links are not clickable since 2023-08-31) | **Search + Search Console** (rec): the revealed name leads to the SSR page; measure per site in Search Console; no name in the pinned comment's first line. |
| D27 | Order of Shorts | **By fame** (rec): Wikipedia pageviews, tier-3 icons included. |
| D28 | Image licences | **All with full credit** (rec); a still whose licence needs an author and has none is refused. |
| D29 | Upload | **Automatic with a schedule** (rec) via the YouTube Data API (OAuth, token outside the repo); pinning stays manual. |
| D30 | Cadence | **1 per day** (rec). |
| D31 | Title | **Own nameless title teaser** (rec), ~40 visible characters, sourced, checked like the card, not identical to sentence 1. |
| D32 | First uploads | **The owner releases every Short himself** (uploaded private, released by him). |
| D33 | YouTube API | **Channel exists; set the API up together with the owner** (rec); he clicks the consent once. |
| D34 | Music licence (Audiio "GlassKeys") | **Cleared** for monetised YouTube. |
| D35 | Retention experiments | **All three**: opener types (rec), TTS speed 0.92 vs 1.0, sentence-1 length 55-70 vs 70-85. |
