# State of the 5,004 curated sites, and the shorts-teaser card proposal (2026-10-08)

Read-only ultracode run `wf_eb1f1425-c3e` (18 agents): six census dimensions over production, a
30-site drawn sample checked against Wikipedia/Wikidata with an adversarial re-check of every
finding, and a card-text design track (renderer timing + Shorts retention research, three
independent designs with samples for 11 pilot sites, a claim-by-claim fact check, a judge).
Nothing was written to production or to tracked files. Raw return values: `workflow_result.json`;
digests: `census_digest.md`, `sample_audit_digest.md`, `teaser_design_digest.md`; pilot data:
`pilot_sites.json`. Agent scratch (queries, exports) was under `C:/tmp/wf_*` and is not durable.

Spot-checked by the orchestrator after the run: the period errors (Le Moustier, Bruniquel Cave,
Cro-Magnon Rock Shelter, Apidima Cave, Eartham Pit Boxgrove, Lake Mungo all at -500 /
"500 BC - 1 AD"; 61 cave sites at -500), the owner note of 2026-10-07 (AUDIT_LOG on origin/main
line 13967: AiFootnote removed for cards, "cards stay plain factual prose"), the failed WD3
calibration (AUDIT_LOG 13478: 64.71 %), and YouTube's non-clickable links in Shorts descriptions and
comments (support.google.com/youtube/answer/13748639, since 2023-08-31).

## Headline numbers (shown = 4,900 non-retired)

| area | measured |
| --- | --- |
| description basis accepted by the card contract | 3,751 (P4 W/S 2,782, WC 949+3, WN 17); 1,121 lane-L-only or none (WC chunks mass-2026-09-27-03/-04/-05 answered, never built or written); 28 empty |
| descriptions with a web-contradicted claim, unrepaired | 141 (DESCRIPTION_DEFECTS.jsonl, 8 files) |
| thin accepted descriptions (< 300 chars) | 431 |
| cards: lane WB teaser (verified) | 2,828, all fresh, 160-190 chars; 2,577 contain the site name, 1,353 open with a place preposition; mean Shorts-hook score 1.98/5 (60 drawn) |
| cards: old March / extractive, unverified | 1,877 (+32 extractive); 163 sites without a card |
| period_start written by rule, unmarked | 1,260 (band rule 512, site-type rule 696, item 45); demonstrably false values (Palaeolithic caves at 500 BC - 1 AD, Inca temples at 43 AD) |
| coordinates sourced | 4,470 / 4,900 (430 unsourced) |
| images | 952 shown sites serve nothing; 2,317 have >= 6 usable rows (short side >= 900, not panorama); 72 % of live rows never vision-checked; 47 heroes judged other_site re-enabled by import-hero |
| duplicates | 43 QIDs shared by 98 shown sites (~27 real duplicate pairs) |
| MiniMax-answered writes after failed calibration | WD3 581 rows / 293 sites + WD4 134 rows / 68 sites, no recorded owner release; the 167 gap-run cards of 2026-10-07 had no WB calibration entry |
| static export index.json | stale since 2026-10-06 09:19 UTC (983 shown sites differ); API/SSR/sitemap/Qdrant are current |
| site_shorts | 0 rows; no upload/publish code |

## Drawn sample (30 sites: 15 WB cards, 15 old cards; seed 'draw-2026-10-08')

- WB cards: 0 of 15 with a confirmed factual problem, but weak hooks (name or location first).
- Old cards: 11 of 15 with a confirmed problem, 7 clearly wrong (Alba Fucens date, Ake date range,
  Chania "quince first cultivated here", Orange "most complete stage wall anywhere", Lukyanus
  "died in service", Amyntas "King", Bayston Hill "over 2,000 years").
- Periods: 4 wrong buckets from the WD3 rules (Lake Mungo -500 vs ~48,000 BC, Broadbury Castle
  Neolithic for a Roman/Iron Age camp, Tappoch Broch, Hodson Stone Circle), 3 band floors.
- Identity: 4 records point at the modern town/village (Alba Fucens amphitheatre, Chania/Kydonia,
  Ravenglass - 19 of 20 gallery images off topic, Bayston Hill), so a Short would show the wrong place.
- Pantelleria Vecchia Bank: point 78 km off; description states a 2015 reading a 2024 study rejects.

## Card proposal (judge's synthesis, design A + C machinery + B precision rules)

Contract `shorts-v1` (full list C1-C20 in `teaser_design_digest.md`, section JUDGE): basis gate as
today; never the site name, an alias, a name token or the country (the Short reveals "Name,
Country." with the flag); exactly 2 sentences, 160-190 chars, sentence 1 40-85 chars (plays over the
6 s globe flight, ends on a photographable noun), no location/administrative opener, the most
surprising sourced concrete detail in words 1-5; sentence 2 carries 1-2 photographable anchors from
char ~95 (cut-on-word window starts ~8.4 s); no '?', '!', 'you', CTA, 'guess'; mystery and
superlative words only where the description has the stem; <= 2 numerals / 8 digits (each digit
~0.32 s of narration); caption-safe words; a reserve description sentence that pays the open thread
off on the site page; sentence 1 must read naturally after "Name, Country." (loop); thin sites may
be declined (enrichment first, never padding, never a Short). Provenance v3, the Shorts AI note
built from `_card_provenance.ai_system` (TEASER_NOTE is a constant today).

Plan: owner decisions -> code (contract, prompts, provenance v3, export, mcode 'wb' lane) ->
sealed O18 calibration of MiniMax M3.1 Flash -> 40-site pilot (owner reads old/new side by side,
listens to 10 narrations) -> wave 1 (~221 Shorts-eligible) + 20-40 measured uploads -> rest of the
3,751 by fame -> thin sites after enrichment -> the 1,121 lane-L sites after WC. Retention: YouTube
Analytics (viewed vs swiped away, APV, retention at end of sentence 1 / 5.98 s / reveal), opener
types randomised in waves of 20 (>= 30 per arm); conversion via Search Console for the revealed
names, because Shorts links are not clickable.
