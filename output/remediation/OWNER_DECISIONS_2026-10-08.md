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

## Follow-up decisions of 2026-10-09 (weekly Claude quota at 69 % after the first day)

| # | question | decision |
| --- | --- | --- |
| D36 | Model mix after the quota warning | **Sonnet instead of Opus, and test Haiku**: field research, fact checker, web verifier and card writer on Sonnet 5.5 (the calibrations measured no Opus advantage: field research 0.864 Sonnet vs 0.871 Opus, BP 0.92 vs 0.88, fact checker 9/30 and 30/30 for both); Opus only for small spot checks and pilot verdicts; Haiku stays on mechanical steps and is calibrated for the fact checker. Supersedes the D6 tier moves of 2026-10-09 to Opus. |
| D37 | Scope after the quota warning | **Everything as decided** (D1-D35), no prioritising cut. |
| D38 | The running Opus calibration of the card checkers | Stop it (the WD5 pilot runs to its end; the fact-checker gold diagnosis finishes). |
| D39 | The rest of the weekly quota | **Work until about 90 %, then pause cleanly** until the reset. |
| D40 | Quality control of the new card texts after calibration teaser-2026-10-10 (no Sonnet role passed; the Haiku trial was weaker than Sonnet) | **Opus for the checkers**: fact_checker and web_verifier on Opus 5.5, the card writer stays Sonnet. |
| D41 | Weekly quota at 95 % on 2026-10-09 (about 22:30 Berlin) | **Pause everything** until the reset. |


## Follow-up decisions of 2026-10-17 (asked in a Claude Code session, Opus 5.5)

The 2026-10-17 MiniMax session recorded D40 as "superseded by D36". The order is the reverse: D36
(Sonnet instead of Opus) was decided first on 2026-10-09; D40 followed after the calibration
teaser-2026-10-10, in which no Sonnet checker passed. D40 was never registered in `roles.py`.

| # | question | decision |
| --- | --- | --- |
| D42 | D36 or D40 for the card checkers | **D40 stands** (rec): the card checks on Opus 5.5; `card_writer` stays Sonnet. How far it reaches: D45. The 2026-10-17 notes calling D40 obsolete are wrong. |
| D43 | Run Phase C now (WD5 main run, card pilot, re-asks, further lanes in MASTER_PLAN order) | **Yes, until about 90 % of the weekly Claude quota** (rec), autonomous under D8/D39, then a clean pause with a resume point. |
| D44 | Open D6 for MiniMax answers | **No, D6 stays** (rec): new answers of the DB repair come only from Claude models; the DB lanes run only in Claude Code sessions. |
| D45 | Scope of D40 (`web_verifier` also serves identity, lane E and image identity, ~14,000 web checks) | **Card lane only** (rec): the card lane gets roles of its own on Opus; `web_verifier` (and every other lane's role) stays on Sonnet and is calibrated per lane. |

## Follow-up decisions of 2026-10-19 (asked in a Claude Code session, Opus 5.5)

Owner: "viel Quote übrig, wir könnten für alles Opus nehmen falls das hilft". An adversarial check
against D1-D45/X1-X11 found eight candidate questions already decided; these six were open.

| # | question | decision |
| --- | --- | --- |
| D46 | `card_writer` after the pilot (checker PASS at attempt 1: 23/39 = 59 %, gate 70 %) | **Opus writes** (rec): `card_writer` moves to Opus 5.5 (supersedes the Sonnet part of D36/D42); tune the prompt with the pilot findings, calibrate, then a second 40-site pilot. The checkers are never lowered. |
| D47 | The 6 cards adjudicated wrong on 2026-10-09 (Astale, North Bersted Man, Roman Ruins of São Cucufate, Caesar's Camp, Teotihuacan – Pyramid of the Moon, Nysa Bridge) | **Clear them now** (rec), journalled and reversible; a checked rewrite replaces them later. D5 does not cover cards proven wrong. |
| D48 | Strip, broken and small heroes (19 strips, 22 broken/hotlinked thumbs, 20 lead rows without hero flag, 433 small) | **Swap strips and broken ones** (rec) in the D15 pass where a checked larger row of the same site exists, incl. the 20 unflagged; the 433 small heroes only go on the owner list. |
| D49 | ~300 attribution-licensed images without any author (48 heroes) | **Swap the heroes, show the rest** (rec): a hero moves to a fully attributed row where one exists; the rest stay in the gallery and stay barred from Shorts (D28). |
| D50 | Retired "mystery" sites (Baltic Sea Anomaly, the Bosnian pyramids, Yonaguni, Richat) vs D21 | **All return as disputed sites** (owner, not the rec): un-retire them through the scope lane, journalled; each description states the scholarly position and the claim, both sourced; no card or page asserts the claim. Supersedes X2 and HUMAN_ONLY B2-B for these sites. |
| D51 | Move further roles to Opus because quota is spare | **Only where a gate fails** (rec): roles that passed on Sonnet stay; a role that fails its calibration or gate moves to Opus (the D6 tier rule). |

Start: the owner asked to continue Phase C in this session now (D43 pause at ~90 % weekly quota stands).
| D52 | Pilot 2 (Opus writer) failed only "0 contradicted": 1 of 29 cards wrong (Black Pyramid "is ... in a limestone casing", the description's Wikipedia present tense; the card_web_verifier restated the claim in the past and verified it), all other criteria met (checker PASS at attempt 1 78 %, unproven 2.6 %) | **Sharpen the verifier, then pilot 3** (rec): a claim's tense and present-state wording are part of the claim and are never restated; recalibrate `card_web_verifier`; a third 40-site pilot under the unchanged gate (0 contradicted). |
| D53 | Pilot 3 (Opus writer, D52 verifier): 0 contradicted, 0 unproven, but 3 of 142 claims DISPUTED (the code's gate wants 0); the Opus xhigh judge found what the verifier passed | **The judge checks every card** (rec): the waves start, and the pilot_judge (Opus xhigh) judges every accepted card as the last gate before the write; a card with a contradicted, disputed or unproven claim is not written (it keeps its card, D5). About 3,750 more Opus answers. |

## Follow-up decisions of 2026-10-24 (asked in a Claude Code session, Opus 5.5, ultracode close-out)

Owner: "ich will dieses projekt mit ultracode abschliessen. stell mir alle offenen fragen interaktiv und schliesse
dann autonom ab!" A read-only scout workflow (`wf_06def1d9-46f`, 7 area agents + 1 adversarial verifier) measured
every area against production and checked 24 candidate questions against D1-D53/X1-X11 and memory: 12 were already
decided or orchestrator calls, these were open.

| # | question | decision |
| --- | --- | --- |
| D54 | What "abschliessen" covers | **Everything** (rec): DB repair through phase 8 (card waves, D10, WC/defects, identity, descriptions, images D17, the 38 sites), the paper-audit leftovers, the stories, the beta label, docs, housekeeping, the final report. |
| D55 | Weekly Claude quota pause (D39/D43: ~90 %) | **No pause; run until the plan limit stops the agents** (owner, not the rec), then resume from the run ids and the resume point. Supersedes the 90 % pause of D39/D43. |
| D56 | AI disclosure of an all-Opus chain (D46 writer, D45 checkers, D53 judge) | **Exact, and correct the 43 live cards** (rec): `ai_system_for` returns the Opus-only string when every stamp is Opus; the 43 version-3 cards of pilots 2 and 3 get one journalled correction step before wave A. |
| D57 | The 38 high-demand sites without a page (+ Chaco Canyon) | **Originals through a new journalled insert lane** (rec): rehearsed, undone by retiring (never DELETE), matching `site_proposals` closed as approved with `promoted_site_id`, then description, fields, images and card per ENRICHMENT_AUDIT. |
| D58 | Scope rule for sites outside Europe dated 500-1500 AD | **The label rule, and the retired ones come back** (rec): only the medieval Old World of Europe, Byzantium and the Vikings is out; non-European sites of 500-1500 stay in; the sites retired under the numeric cut come back through the scope lane, journalled. L'Anse aux Meadows stays out (Viking subject). D20 uses this window. |
| D59 | 140 shown sites with only a hotlinked thumbnail and no stored credit | **Replace the third-party ones, credit the Commons ones** (rec): the 9 third-party hotlinks join the D17 research (a checked Commons picture with credit, else the thumbnail goes NULL); the 131 Commons thumbnails get a credited gallery row of the same file through the INSERT lane after a Sonnet depicts check. Lifts the 2026-10-05 thumbnail-only rule for these sites. |
| D60 | The paper-audit leftovers (11 critical findings live, 11 heroes, summaries, 25 anchor-blocked findings, mogollon) | **Extend `theo_publish --correct`** (rec): small, journalled kinds for `probative_images` (flip or drop within the stored set), `hero_image` (only a picture already in the paper), `card_description`/summary and evidence re-anchoring with retirement entries naming the old ids; the gates re-run; mogollon through a deterministic recompute of `undefined_title_terms`. Claude writes and checks; no MiniMax, no Theo run. All confirmed findings. |
| D61 | The story backlog (beta-exit condition 3) | **Restart the backbone now, alt-history first** (rec): the beta label waits only for the 1,828 alt-history stories; the mainstream rest continues afterwards; retry 7196 and 8443. MiniMax, inside the quota. |
| D62 | Beta-exit wording | **Variant B** (rec): both BETA badges removed; SitePopup keeps its warning icon with "Images matched automatically – some may not show this site"; ConnectorStatusModal: "Content is aggregated from museums, libraries, and archives worldwide. Coverage and accuracy vary by source, and some connectors may be temporarily unavailable."; the dead `.beta-badge` CSS goes. |
| D63 | Side items (30-day stats review, Bing Webmaster panel, YouTube watch time, mypy gate A7) | **Not part of the close-out** (rec); separate sessions. |
| D64 | Untracked reports in a public repo | **Commit the two reports only** (rec): `docs/reports/2026-10-08-seo-geo-audit.md`, `docs/reports/2026-10-19-stats-seo-auswertung.md`; `docs/ideas.md` moves to a gitignored place. |
| D65 | Restart after a plan-limit stop | **Heartbeat about every 3 h** (rec): a durable cron job in the Claude Code session resumes the run from the resume point (renewed after its 7-day expiry). |
| D66 | Owner-only actions during the run | The owner runs the **sudo logrotate install now** (visitor classes push 2a, then 2b >= 48 h later); the GSC checklist stays for later (final report). |

## Follow-up decision of 2026-10-25 (Claude Code session, Opus 5.5)

| # | question | decision |
| --- | --- | --- |
| D67 | The token cost of the full close-out (D54: about 25,000-30,000 more model answers, weeks) | **Stop now** (rec): the close-out run ends after the beta-exit work; the DB rest (card waves, WC finish, identity, images D17, the 38 sites, phase 8) waits at a written resume point for a later session. Only the story backbone keeps running on the VPS (MiniMax, no Claude tokens); a short session pushes the beta label once the alt-history stories are done. Supersedes D54's scope and D55/D65 (no heartbeat). |
| D68 | (2026-10-25) Shypyntsi shows "Undated" although its Wikipedia article dates the Cucuteni-Trypillian settlement to the 5th to early 4th millennium BC (the wd5 re-check held the cell as unclear: Ukrainian sources say 4th-3rd millennium) | **Write the Wikipedia date** (owner, 2026-10-25: "warum ist die scheisse bei uns undated"): the researcher's value -5000 with its found quote goes in through `adversarial.py owner-accept` and a journalled wd5 wave; the re-check's unclear note stays in the evidence. |
| D69 | (2026-10-25) The other 48 cells the wd5 re-check held as unclear (45 in wd5, 3 in wd5-reask) whose researcher found a quote for the value | **Write them the same way as D68** (rec): `owner-accept` + one journalled wave per run; the 128 rejected cells (a contradicting reputable source) stay unwritten and listed. |
| D70 | (2026-10-25) 615 of 4,909 shown curated sites still have no period start; the owner's spot check found a dating at once | **Stop now; the next step is a proper dating extractor** (owner): before any further model research, build a deterministic extractor that finds a site's dating whenever a source states one - not only English Wikipedia but the other sources too (other Wikipedia languages, Wikidata date properties, heritage registers, Pleiades and the other connected sources) - and measure its coverage on the 615 undated sites and a gold set first. The close-out run is stopped and counted by the owner as a failure. |

## Owner questionnaire of 2026-11-05 (Claude Code session, Opus 5.5; 43 open questions, answered interactively)

| # | question | decision |
| --- | --- | --- |
| D71 | D70 extractor write gate | **Write without a model check** (rec) when the extractor's precision on a sealed gold set is >= 95 % and every cell carries a verbatim quote + source URL; 30 cells shown to the owner before the wave; journalled through the wd5 lane. |
| D72 | D70 extractor scope | **Fill the 615 undated only** (rec); the comparison against the ~4,294 dated sites is measured and shown as a conflict list, never written. |
| D73 | Sites the extractor finds nothing for | **Decide after the measurement** (rec); they stay "Undated", the rest list goes to the owner. |
| D74 | Beta label vs. alt-history stories that never finish | **The label goes once at most ~10 permanently failing alt-history stories remain** (rec); their ids go to the owner, they stay online. |
| D75 | MiniMax weekly quota priority | **Story backbone first from the reset Mon 2026-11-09** until the 346 alt-history stories are done (rec); afterwards the backbone runs Mon-Wed only, Thu-Sun stays reserve for studio and Lyra. |
| D76 | Google cliff of 2026-10-20 | **The owner checks GSC "Security & manual actions" and the ancientnerdsdao@gmail.com inbox** and sends the wording (rec). |
| D77 | Visitor classes push 2b (hidden /index-all/ link, 8773db9) | **Hold until the GSC manual-action check is done** (rec); supersedes D66 for 2b. |
| D78 | Resume of the DB close-out (D67) | **In stages, owner release per lane with a cost estimate** (rec): first the cheap steps (D14 part A, D48, D49, D57), then card wave A, then the rest. |
| D79 | Card wave A (1,189 sites) | **Stages, a1 first** (rec): measure the cost per card, spot-check, then the owner decides on a2-a4. |
| D80 | Lane WC calibrations that failed at the top tier | **Adjudicate the disagreements, release wc-wv-1o; sharpen and re-seal the briefings of fc-2o, wv-2o and the pilot judge** (rec). |
| D81 | New contradicted description sentences found by card waves (est. 450-750 sites beyond D25's 160) | **Repair them per wave through the D25b mechanism, then rewrite the card** (rec). |
| D82 | D17 image sources | **Commons only** (rec); sites without a usable Commons image stay imageless and go on the owner list; the D48/D49 rest lists (433 small heroes, 6 strips, 11 without author, Qasr Qaroun) stay live and are searched within D17. |
| D83 | D13 re-target when the ancient site has no Wikidata item and no enwiki article | **Re-target without ids** (rec): name and text move to the ancient site, source_url = the best scholarly source, no Short. |
| D84 | D50 country of the Baltic Sea Anomaly | **Empty / international waters, no country page** (rec). |
| D85 | Theo worker (Q1) | **Off until after the beta label** (rec); then the 14 campaign topics with 1 slot, /theo-write after the first dossier; the 12 old UI requests of 2026-07-05 go to cancelled. |
| D86 | Paper quality badges from the old M3 score | **Remove the M3 badge** (rec); show "Claim-checked" only where the studio check ran (code + journalled correction). |
| D87 | YouTube as a whole (Shorts production, Baalbek slice Q2, first full episode, comment agent) | **Deferred** (owner: "youtube zurückstellen", Shorts "weiter warten"); OAuth is set up together with the Shorts release; **no "altered or synthetic content" label**, the AI voice is named in the description only. |
| D88 | SerpApi November quota | **Use ~50 searches for the cliff diagnosis** (head + brand terms), keep the rest (rec). |
| D89 | Reaction if Google confirms a scaled/thin-content action | **Wait for the finding**, then decide from Google's example URLs (rec). |
| D90 | SEO audit 2026-10-08 E1b, E6, E12, E13 | **All four recommendations confirmed** (rec). |
| D91 | GSC checklist of 2026-10-20 | **Only the exports now** (owner, ~10 min); Soft-404 validation and indexing requests after the cliff is resolved. |
| D92 | 30-day stats review | **Postponed** (owner); the creator flywheel panel and the mobile globe layout follow after the review (rec); TTFB/CDN stays as is (rec). |
| D93 | God's-Eye-View layer | **Keep waiting for issue #1005; commit scripts/export_gods_eye_view_layer.py** (rec). |
| D94 | Trademark "Ancient Nerds" | **First settle the owner with Matt** (owner). |
| D95 | Matt Cavana's seed DB licence | **Not needed** (owner): the internal release of 2026-10-11 suffices. |
| D96 | Wikidata item "Ancient Nerds" | **Wait for an independent source** (rec). Training-data policy: rest (rec). |
| D97 | Prospector queue (1,944 new, 361 needs_decision) | **Plan as its own lane after D70/D57** (rec); the owner rejects L'Anse aux Meadows (01e29c6e) in the Radar now. |
| D98 | Housekeeping | Offsite sync task (D24) **registered Sun 08:00 + run once**; VPS leftovers **deleted except .env.bak-*** (owner handles those); merged branches deleted, the four unmerged ones (develop, feature/new-ingesters, worktree-phosphor-tinting, chore/2026-10-04-corrections-reversal) **archived as tags, then deleted**; studio Q3-Q17 confirmed; video/src/lyra-haiku/ stays local; NERV redesign rests. |

## Orchestrator decisions under the owner's AFK mandate of 2026-11-05 ("soweit wie möglich autonom, Empfehlungen umsetzen")

These were raised by the wave-1 scouts (output/remediation/final-2026-10-08/D70_EXTRACTOR_DESIGN.md, LANES_PLAN_2026-11-05.md) and decided by the orchestrator (Claude Opus 5.5), not by the owner; the owner may overturn any of them.

| # | question | decision |
| --- | --- | --- |
| O1 | D70 range representation: period_end is NULL on all 5,004 curated rows, the page renders "start – end", and the D58 window tests period_end first | **Write only the start** (the earliest anchored start of the highest tier present); the source range with both quotes stays in the journal evidence. Reason: a disagreement about when a site began is not an end of occupation; writing max-start into period_end would tell visitors a wrong end. A cell whose start would move a site outside the D58 scope window is not written; it goes to the owner list. |
| O2 | D69 vs D70 for the 105 adversarially rejected cells among the 615 | **D70 wins**: the extractor may write them under O1 with every conflicting quote in the evidence. |
| O3 | D71 "30 cells shown to the owner before the wave" while the owner is AFK | The 30 cells (ranges and period words over-represented) are checked by three independent adversarial agents against the live sources instead, and saved to OWNER_SHOWN.json marked "owner AFK, autonomous mandate 2026-11-05"; the wave goes only if the sealed gold precision is >= 95 % and the spot check finds <= 1 wrong cell of 30. |
| O4 | D57 insert while a thin-content action is suspected (D76/D89) | **Research and plan now, no insert write** until descriptions (WN) and images exist for the new sites. |
| O5 | D14 part A scope | The model-free move of the 23 already-retired duplicate losers' images and links, **excluding Tarxien and Dodona** (part B may swap their survivors). |
| O6 | D80 extent | Release wc-wv-1o; adjudicate the 6 pilot-judge disagreements first; sharpen CHECK/VERIFY/JUDGE briefs and re-seal all WC roles under new ids (~86 Opus answers). |
| O7 | D81 timing for a1 | After D80 gives wc_web_verifier standing: the a1 defect sites are repaired through D25b, and their a1 cards are held from the first write step and rewritten after the repair. |
| O8 | Image-role recalibration (image-roles-v1 failed; ~950 answers) | **Not started**: not covered by any release; blocks D15/D17/D59. Cost goes to the owner. |
| O9 | Weekly backbone restart after the alt-history stories (D75) | A guarded weekly Monday 00:20 UTC cron start is added on the VPS. |
| O10 | VPS leftovers beyond the listed ones (node_modules-bak-*, sites_dump.dump, 4 untracked scripts, tts_test/, pfps/) | **Left in place** (deletion outside the listed scope); listed for the owner. |

## Owner questionnaire of 2026-11-06 (Claude Code session, Opus 5.5; questions raised by wave 2)

| # | question | decision |
| --- | --- | --- |
| D99 | D70 after the deterministic extractor failed (sealed gold 0.7034, spot check 26/30 wrong) | **A Claude agent reads per site** (rec): Sonnet field_researcher proposes a quoted start per undated site, an independent adversarial check verifies; ~1,200-1,500 Sonnet answers. **Pilot of 50 sites first, result shown to the owner** before the rest. O1 (start only, range in the evidence) and the D58 window precheck stay. |
| D100 | pilot_judge failed its re-seal at Opus (wc-pj-1o2 0.913 with the known error missed; wc-pj-2o2 0.8966 with 2 extra WRONG judged plausibly right) | **Release** (rec): strict rather than lax is the safe side for cards; released on wc-pj-1o2. |
| D101 | The period word "Neolithic" (and other period words) mapped to one fixed year (-4000) | **A year stated by the same source wins** (rec); a bare period word is used only without a number, and then with a regional start (Near East earlier than Europe). Applies to D57 and the D99 lane. |
| D102 | GSC manual-action check (D76) | Still open: **the owner checks and sends the wording.** |
| D103 | Image-role recalibration (image-roles-v1 failed; O8) | **Start the re-test one tier up** (rec), ~950 answers mostly Opus; the cost of the D17/D15/D59 image search itself (~1,500-3,000) is reported separately before it runs. |
| D104 | D57: 6 vetoed fields (Merv, Mesa Verde, Palmyra, Nan Madol, Pantheon start; Thermopylae coordinates) | **Second research round for the 6 (code + ~15 answers), new plan + Opus review; insert still waits** for text and image (O4). |
| D105 | Card waves a2-a4 | **Stop after a1 and show the owner cost and quality per card** (rec). |
| D106 | Disk C: ~96 % full | **Keep only 1 local offsite copy** (VPS keeps 4). |
| D107 | VPS leftovers (node_modules-bak-*, sites_dump.dump, 4 untracked scripts, tts_test/, pfps/, the two 2026-11-05 d14a backups) | **Delete all except .env.bak-*** (rec); supersedes O10. |
| D108 | "Claim-checked" badge on SSR paper pages / library cards | **No** (rec), no new design element. |
| D109 | The 5 novel briefings | **noindex stays** (rec). |
| D110 | Small items | Cancel Theo request afe7c26a (paused); archive as tags and delete the local branches fix/2026-10-20-reference-linkifier-parens and integrate/wave1, keep feat/visitor-classes-push2 (held by D77); O1-O10 stay in force. |

## Owner answers of 2026-11-06 evening (questions of AFK_REPORT_2026-11-06.md)

| # | question | decision |
| --- | --- | --- |
| D111 | D99 pilot failed (7/50 dated, 5 right) | **Improve, then a second pilot of 50 new sites (~80 answers)**: coarse period words (Stone Age, Palaeolithic, Bronze Age without a sub-phase where the table needs one) give no year, a precise epoch is required, a weak single source (unreferenced stub, travel page) does not count, missing epochs (Chimú, Late Roman, ...) get cited starts. Stop after the pilot and show the owner. |
| D112 | The 5 checked right pilot years (Brean Down, Mawk'allaqta, Karabel, Çimdin Kalesi, Moel y Gest) | **Write them** through the journalled wd5 lane together with the next step; Port Way and Čertova pec are not written. |
| D113 | D101 detail questions 1-5 | All as recommended: Italy 'Roman' alone gives no year ('Roman imperial' from -27); Germany/Netherlands/Switzerland 'Roman' alone gives no year; fill missing countries and epochs with Wikipedia citations; a read-only list of already written years the old fixed rule may have got wrong; Wikipedia suffices as a citation and the old British middle/late Neolithic and Iron Age values stay. |
| D114 | Nan Madol start (research 900 AD vs reviewer 1 AD) | **A small third round for this field only** (2 answers), then a new plan and review; insert still waits (O4). |
| D115 | pfps/ and tts_test/ on the VPS | **Leave them.** |
| D116 | An image of a genuine part of the site now in a museum (e.g. the Ishtar Gate in Berlin) | **Counts as "shows the site".** |
| D117 | The image gold of 2026-09-19 has ~40 wrong entries | **A clean re-measurement** with a new, checked gold set (550-950 answers, mostly Opus). |
| D118 | Image prefilter failed at Sonnet | **Test it at Opus** (~5 answers first). |
| D119 | Tolerance for "wrong site" in image_depicts | **At most ~2 %**, because the adversarial check views every image afterwards. |
| D120 | (unchanged) | The image search itself (D17/D15/D59, ~2,500-3,200 answers) starts only after a separate owner release. |

## Owner answers of 2026-11-07 (questions of AFK_REPORT_2026-11-05.md section 3 and AFK_REPORT_2026-11-07.md section 7)

| # | question | decision |
| --- | --- | --- |
| D121 | The 166 period-word years of D113_CONFLICT_LIST | **Correct them** (rec): 69 get the regional year, 97 become undated; recomputation only, journalled wave. |
| D122 | The 301 rule-made years without a source (old site_type rule, D12) | **Reset to undated** (rec), in the same journalled run as D121. |
| D123 | Bare "Bronze Age" where the table has sub-phases | **Stays without a year** (rec). Countries without a clear Wikipedia start stay without one too. |
| D124 | Dating of the remaining ~430 sites | **Stop here** (rec); only Eddisbury Hill Fort gets its cited radiocarbon start (12th c. BC) through a 1-2 answer re-ask. |
| D125 | image_depicts at Opus (false depicts 1.6 % <= 2 %, recall 0.79 < 0.90) | **Release** (rec). |
| D126 | image prefilter at Opus (0.95 vs 0.98) | **Release** (rec). |
| D127 | Loose museum finds whose provenance is only on the file page | **Count only when the image itself shows the provenance** (label/inscription); architectural parts always count (D116). Correct the ~10-11 gold cases accordingly. |
| D128 | image adversarial after D127 | **Release if <= 4 real errors per 100** (rec). |
| D129 | Image search D17/D15/D59 | **In stages** (rec): first ~150 sites, spot check, cost per image reported; the owner decides the rest. |
| D130 | D57: Miletus, Panathenaic Stadium, Pella | **A small 4th round** for these 3 fields (rec); insert still waits (O4). |
| D131 | Card waves a2-a4 (a1: 18.2 answers per written card) | **First make it cheaper, then run a2** and report cost and quality (rec); a3/a4 wait for the owner. |
| D132 | a1 rest | **Rewrite the 4 weak spot-check cards** (Banwolseong, Rudna Glava, Nakhchivan, Seahenge); the 9 cards blocked by the web.archive.org network block stay, retried later without a new access path. |
| D133 | VPS backups 2026-11-07_a1-* (3 x ~885 MB) | **Delete after Sunday's offsite copy is verified** (rec). |
| D134 | WC adversarial role + D18 author backfill (44 heroes) | **Both** (rec): calibrate the adversarial role for lane WC (~30-50 Opus answers) and run the D18 author backfill with a journalled write. |
| D135 | Disk C: (22 GB free) | The owner declined archiving the old handoff dirs; **he cleans up himself**. Runs must stop and report below 10 GB free. |

## Owner correction of 2026-11-07 (after 988 visible sites showed "Undated")

| # | question | decision |
| --- | --- | --- |
| D136 | Sites whose only dating is an epoch word (incl. the coarse words of D111/D123 and the type-rule years reset by D122) | **Use the predefined period bands** (owner: "Ich will die vorgefertigten periods. wir haben doch älter als 4500bc. da kann doch vieles rein."): every epoch maps to the band in which it begins (in the site's country where REGIONAL_STARTS has a value), per the table output/remediation/fields/epoch_bands/EPOCH_BANDS.md; the stored year is the band's edge (`bucket_edge`, as for the 511 band rows of 2026-10-04 and the owner's rule "Neolithic is < 4500 BC"). Coarse words (Stone Age, Palaeolithic, prehistoric, Mesolithic) go to "< 4500 BC"; a bare Bronze Age goes to the band of its regional start. Supersedes D111's/D123's "no year" for epoch words and D122 where the site's own sources, Wikidata P2348 or its own type/name name an epoch. A site with no year and no epoch anywhere stays "Undated". |
| D137 | (2026-11-07) D136 details after the spot checks (19/50 judged wrong, largely by the band rule itself) | **Write all bands now** (owner: "Egal, schreiben"). A century/year the site's own source states for the site wins over the epoch start (rec). A coarse word ("prehistoric", "stone age") is read together with the site's own monument type to pick the band where the type names its epoch (owner: "Wenn es 4000 bis 1500 ist haben wir doch auch eine periode dafür"): stone circle/henge/dolmen/long barrow/passage tomb -> Neolithic, round barrow/cairn -> Bronze Age, hillfort -> Iron Age, each with the site's regional start; only without such a type does the coarse word give "< 4500 BC". Obvious reading errors (a period word inside a name of a site its source calls older, finds in the surroundings, a later renewal) are fixed before the write. The owner cleans disk C: himself. |
| D138 | (2026-11-07) The 60 year-stated-only sites of the D137 refine (year from the site's own source, mostly the stored description) and the 2 scope-hold sites | **Write the 60** as the band of their stated year (owner: "die 60 sites ja"); **retire Caus Castle and Ayazini Kaya Church** as medieval / out of scope (owner: "die 2 mittelalter deaktivieren"), through the journalled scope-retire lane. |

## Owner questionnaire of 2026-11-10 (Claude Code session, Fable 5.2; 12 open questions, answered interactively)

Owner: "wir haben noch nicht alles abgeschlossen. stell mir alle offenen fragen." State measured read-only before
the questions (production, 2026-11-10): 4,907 shown curated sites; 544 without a period start; 955 without a
thumbnail; 40 without a description; 269 without a card text. Story backbone 2026-11-10 09:36 UTC: 662 stories open,
4 alt-history stories open, stopped by the quota guard at 29 %. Google referrals 13-30 a day (350-550 before
2026-10-20). Interrupted on 2026-11-07 by D136 and still released: card wave a2 (verify 200/292 answered), the D132
redo (write answered, chain open), the D57 plan after round 4 (Opus review open), image stage 1 of D129 (not
started), the D133 backup deletion.

| # | question | decision |
| --- | --- | --- |
| D139 | Beta label (D74: at most ~10 alt-history stories left; 4 open) | **Remove it now** (rec): `closeout/beta-label` (D62 wording B) onto the current main, gates, push. |
| D140 | GSC manual-action check (D76/D102) | **The owner checked: nothing is reported.** The cliff of 2026-10-20 is therefore an algorithmic site-wide demotion; D89's "decide from Google's example URLs" has no examples to go on. |
| D141 | Reaction to the algorithmic demotion | **Measure first, then a proposal** (rec): count per page type the thin or automatically produced pages Google knows (sites without text or picture, short stories, list pages) and show the owner the numbers with a proposal; no model answers, nothing changes live. |
| D142 | Visitor classes push 2b (hidden /index-all/ link, 8773db9; D77) | **Hold until Google has recovered** (rec), also without a reported manual action; supersedes D77's release condition. |
| D143 | D57: the 37 high-demand sites without a page | **Finish them completely and insert** (rec): description, picture and card per site, then the insert; about 600-950 answers plus the card_stats insert step. No site goes live without text and picture (O4 stays). |
| D144 | D14 part B (90 duplicate groups, Tarxien, Dodona, Caparra) | **Run it** (rec), about 180 answers. |
| D145 | Descriptions: what belongs to the close-out | **All four** (the rec was the first two): WC finish and the 141 defects (~1,200-1,400 answers), WN for the 40 shown sites without a description (~200), D21 disputes (~360), enrichment of the thin texts (~5,250). |
| D146 | Identity: what belongs to the close-out | **D20 scope review with the 5 pending rows (~230), D13 modern-town re-targets (pilot of 20, then 60-150; ~800), D23 clean names with D25 parents (~500)** (the rec was D20 only). **Spoken names (D23) are deferred** while YouTube rests (D87). |
| D147 | New cards beyond wave A | **Stop after wave A** (rec): the other ~3,700 sites keep their card (D5), the 269 shown sites without a card text stay without one; reopened when the Shorts start. |
| D148 | `wc_adversarial` failed at Opus (wc-adv-1o: 0.8311 < 0.90; 30 of 37 disagreements keep a sentence the record drops; 1 of 3 known errors missed; held, no higher tier than Opus) | **Test one tier up on Fable 5.2** (owner; the rec was no release): ~220 answers plus the code for a truthful Fable stamp and disclosure. Extends D6 by `claude-fable-5-2` for this role only. |
| D149 | Baltic Sea Anomaly without a country (D84) has no /sites/ page at all | **Globe only** (rec): no route without a country. |
| D150 | The three unreviewed single-commit branches (S12) | **Only `fix/2026-10-10-google-no-average` is reviewed and goes live** (rec); `feat/2026-10-07-lyra-haiku-5-5` and `feat/studio` are archived as tags and deleted with their worktrees. |
| D151 | How the released work runs | **In one go, in this order** (rec): beta label; the runs interrupted on 2026-11-07; D57; D14 B; D20; WC finish; WN; D21; D23/D25; D13; enrichment last. A short report per block; stop only when a block costs more than 25 % above its estimate or a spot check is bad. Enrichment starts with a 100-site pilot and then waits for the owner. D129 (image rest after stage 1) and D131 (card waves a3/a4 after a2's report) keep their owner gates. |
| D152 | Weekly cap | **2,500 model answers a week** (rec), counted by the orchestrator (Monday to Sunday); then a clean pause until Monday and a status report. |

### The same evening: only Fable 5.2

| # | question | decision |
| --- | --- | --- |
| D153 | The model of every answer (D6: Opus/Sonnet/Haiku 5.5 by role, each calibrated) | **Fable 5.2 only** (owner: "wir müssen mal alles auf fable 5.2 umstellen, da kann ich das kontingent zurücksetzen"; "Ich will mit Fable das projekt abschließen! nur mit fable!"). Every role answers on `claude-fable-5-2` from now on; the three Opus verify agents still running were stopped. Supersedes D6's model mix and D36/D40/D45; answers recorded earlier keep their stamp and stay valid. |
| D154 | Calibration of the roles on Fable (asked: measure each role on its sealed gold first, ~2,000-2,500 answers) | **No calibration runs** (owner: "ich will keinen stempel. verdammt nochmal ich will das projekt endlich abschließen. die datenbankprüfung geht schon seit wochen."). A role stands on Fable by this decision, with no verdict of its own; D148's Fable test of `wc_adversarial` is dropped with it. Orchestrator's reading, not the owner's words: the answer files keep naming the model that really answered (`claude-fable-5-2`), because an import refuses any other name and the record would otherwise be false; that is a code change without a model answer. The journalled write path (backup, rehearsal, read-back, acceptance) stays. |
| D155 | Weekly cap (D152: 2,500 answers) | **Lifted for Fable** (rec): the owner resets the quota himself; a count per block is still reported, and the stop rule of D151 stays. |

| D156 | How the rest runs (asked: the three stops that remained - after card wave a2, after the first 150 images, after the 100-site enrichment pilot - "say 'ohne Halt' and I run through") | **Everything, with ultracode, and deployed** (owner: "Mit ultracode alle oben genannten punkte abarbeiten und deployen."). Orchestrator's reading: the owner gates of D129 (image rest), D131 (card waves a3/a4) and the enrichment pilot stop of D151 are released; the pilots stay as the orchestrator's own quality checkpoints (a bad spot check or a block more than 25 % above its estimate still stops that block and is reported). Multi-agent workflows drive the lanes. |

### Orchestrator decisions under the owner's AFK mandate of 2026-11-10 ("empfehlungen umsetzen, issues fixen, autonom mit ultracode abschließen. ich bin afk.")

Raised by the lane scouts and their checkers (playbooks under `output/remediation/final-2026-10-08/drivers/<lane>/PLAYBOOK.md`, workflow `wf_21f9aa96-71d`) and decided by the orchestrator (Claude Fable 5.2), not by the owner; the owner may overturn any of them. Each takes the path that finishes the database with the least new scope inside D1-D156.

| # | question | decision |
| --- | --- | --- |
| O11 | Cards a2-a4: weak cards of a spot check; descriptions a D81 repair clears completely; run a1's 9 cards blocked only by web.archive.org | Weak cards are reported, not rewritten (D132 named a1's four); a contradicted card is cleared. A site whose description a repair clears joins lane WN, with no new card (D147). The 9 a1 cards get one small card run at the end of wave A (D132: "retried later"; the archive answers again from the workstation). |
| O12 | D57: every lane that writes text or pictures needs the row to exist, but O4 forbids a thin live page | **Staged insert**: the 37 rows are inserted hidden (retired with a reason beginning `D57 staged:`), get description and pictures while hidden, and are un-retired only with a description and a confirmed picture; the card follows after go-live. A site that ends without text or picture stays hidden and is listed. If review 5 vetoes Pella's start again, Pella is left out of the insert and listed; no sixth round. |
| O13 | Images: 43 of the 131 hotlinked Commons thumbnails are below the 800x300 floor; the rest lists of D82 need code that does not exist | The 43 are credited as they are shown (the page shows them already) if the floor is a parameter of the run, else listed; they stay on the small-hero list. Order: D15, D59, D17 in stages of 150; the rest lists (433 small heroes, sites that already serve pictures) come last, once their code is built. |
| O14 | D14 B: survivors of Tarxien and Dodona; merges more than 2,000 m apart; a loser's stories, paper links, proposals, likes | No survivor swap: the pictures move to the present survivors. A pair beyond 2,000 m is merged only when verdict and re-check both call it the same site with quoted evidence, else held and listed. Rows no lane moves stay on the retired loser (its page answers 301 to the survivor) and are counted in the final report. |
| O15 | D20: five retired label-borderline sites and Pilares do Lena | They stay as they are and are listed. X13 (Islamic and Byzantine Europe outside the window) is built into the lane before its first round. |
| O16 | WC finish: a failed sampled judge bars a whole chunk; the five defect sites whose lines were lost; stale cards of repaired sites | The command that drops the judged-wrong sentences and rebuilds is built only if a judge fails. The five sites are named in the defects run if the tool allows, else listed. Stale cards stay shown (D147) and are counted. |
| O17 | D21: the dispute screen flags about 223 candidates (about 580 answers against the 360 of D145); D50 sites the adjudication rules "not a dispute"; the six retired D50 sites hold a card | The estimate of this block is revised to about 580 before it runs (no narrowing of the screen). A D50 site ruled not a dispute stays retired and is listed. The six cards are cleared the D47 way, so the un-retire needs no new card. |
| O18 | Lane E: the lane as built enriches texts under 300 characters (558 shown today, about 900 after WC finish, about 1,850 answers), not the plan's 2,100 sites; the question allows one sourced open question per text; enrichment makes a site's card stale | Run it as built: every shown text under 300 characters. No second pass at a higher threshold, the frozen question stays, stale cards stay shown (D147). |
| O19 | D23: 438 names whose only defect is a comma qualifier ("Brough, Cumbria") | Not asked: neither broken nor foreign in D23's sense. |
| O20 | D13: the follow-up of a re-target (new description, pictures, period, card) is in no decision and needs code that does not exist | The verdict stages run when the web pool is free. A re-targeted record gets its links, name and aliases, its town card is cleared (D147: no new card), and description, period and pictures follow through the lanes once their code is built; D13 runs last for that reason. D83's mixed case (an item without an English article) keeps the item and gets no Short. |
| O21 | Phase 8: the final error-rate measurement X7 (about 1,500 answers and a day of code); D133's five further pre-wave dumps of 2026-11-07; Theo (D85 names 14 campaign topics, 13 of whose rows are cancelled); four expired Windows tasks of the MiniMax run | X7 is dropped (D154: no measurement runs); the spot checks of each wave stand in its place and the final report says so. All eight pre-wave dumps of 2026-11-07 are deleted once the offsite copy is verified. Theo is not started: which topics run is the owner's call (final report). The Windows tasks are listed, not deleted. |
| O22 | Google (D141), proposal `output/seo-audit-2026-11-10/PROPOSAL_D141.md` after its refutation pass | Implemented in one deploy: stage A of measure 1 (new stories noindex for Google only, no search-result excerpts under the sources), measure 3 (the 40 site pages without a text noindex for Google until lane WN has written it) and measure 5 (the legacy sitemap goes; the 18 country pages with at most four sites noindex for Google). Left to the owner: stage B (all stories, decided after the core update, early December), measure 2 (site-page layout: a design change, a draft first) and measure 4 (the "about and method" page: its text is the owner's voice, a draft is prepared). |

### 2026-11-11

| # | question | decision |
| --- | --- | --- |
| D157 | The Fable 5.2 quota is used up (the usage limit stopped every agent on 2026-11-11) | **Go on with Opus 5.5** (owner: "bitte weiter mit opus 5.5. Fable ist aufgebraucht."). Every role answers on `claude-opus-5-5` from now on, by an owner move like D153, with no calibration (D154 stands); answers recorded on Fable stay valid. No weekly cap (D155 stands). |
| D158 | Remaining scope (asked after the owner saw ~90-95 % of the planned effort still open: "WTF??? DAS IST DOCH VIEL ZU VIEL WAS NOCH OFFEN IST!") | **Lean close-out: errors only** (rec). Finish and write card wave a2 (with its D81 repair); finish lane WC (mass-03/04/05 and the 141 defect sites); D14 part B duplicates; D20 scope review; lane WN for the 40 shown sites without a description; then phase 8 (card_stats wave, export, owner list, final report, docs, merge). **Dropped** (superseding D143-D146, D129, D131, D156 for these): card waves a3/a4 and the O11 run, the image search (D17/D15/D59 and rest lists), lane E enrichment, D21 disputes and the D50 un-retire, D23/D25 names and parents, D13 re-targets, the 37 D57 sites (they stay uninserted; their research and plan are kept). Code already built for dropped lanes stays merged and unused. |

Orchestrator decisions under D158 (2026-11-12, owner away; the owner may overturn them):

| # | question | decision |
| --- | --- | --- |
| O23 | Lane WC: the sampled judge of mass-2026-09-27-05 failed (55 of 148 sites: 23 kept sentences WRONG at 21 sites, 6.3 % UNSUPPORTED, 5 incoherent texts). The gate bars the whole chunk, so the March texts stay live with every one of those errors, although a WC write only removes sentences | **Write what is strictly better than the live text** (O16's tool is built now): the judge's WRONG and UNSUPPORTED kept sentences are dropped as well, a site the judge called incoherent is not written (listed), the rest of the chunk is written. The same rule holds for mass-03, mass-04 and defects-2026-10-02. Unsampled sites can still carry a wrong sentence the chain missed; the final report gives the judge's measured rate per chunk instead of claiming them clean. |
| O24 | D14 part B is stopped by its own guard probe (G4: the probe takes a foreign row from the plan's first table, and production has no site_content_links row of a non-curated site) | Build G4 (the probe takes the foreign row from a table of the plan that has one), then go on with the wave. |
| O25 | Order of the rest | D14 B, then WC finish, then WN (WN after WC, because WC clears texts). |
| O26 | WC plans hold sites that D14 B will retire as duplicate losers (mass-05: f5df832e Twin Gates of Pula; mass-04: 4, mass-03: 6, defects-2026-10-02: 1); no tool leaves one site out of a built plan | **WC may write them**: D14 B's retire writes only scope_status/scope_reason and its move only names, images and links, so there is no cell conflict; a retired loser's description is not shown (its page answers 301). No new exclusion code. |
| O27 | D14 B's move rehearsal times out (three move invariants compare `CAST(s.id AS text) = q.new_value`, one full scan of 1.76 M rows per site_id cell; 151 cells exceed the 120 s statement timeout) | Fix the cause (an indexed uuid comparison), not the timeout and not a split of the wave. |

Still the owner's own: reject the L'Anse aux Meadows proposal 01e29c6e in the Radar (D97; status `new` on 2026-11-10),
the trademark ownership with Matt (D94), the GSC exports (D91), disk C: (23 GB free on 2026-11-10; D135).
