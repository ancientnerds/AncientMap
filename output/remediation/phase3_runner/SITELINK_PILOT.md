# The sitelink lane's pilot: thresholds fixed before the first model call

Written 2026-09-23, before any model call of this pilot; committed before one is bought. The sha256
of this file is recorded in `output/remediation/AUDIT_LOG.md` together with the results, so the
thresholds cannot be moved after the numbers are known.

**Re-sealed the same day, still before any model call** (no `slk`/`slkg` row in
`phase3_runner/LEDGER.jsonl`, no `runs/sitelink-gold`): an independent check found that the plan
gave a site the articles of an item the owner-case classifier had found is the place that holds the
site, not the site - among the pilot's sites Hebbariyeh Roman Temple, whose item is the village of
Hebbariye (`bcases/names.jsonl`, N7 `anchor-is-locality`) - and that threshold 4 below was not the
search pilot's sentence. The plan was rebuilt under the corrected item rule and this document
rewritten; the first version (commit 2fe862b, sha256 `47f9adc4...8dac6`, plan `593501ab...b522`)
does not apply any more.

## What is measured

The plan `output/remediation/sitelink/pilot/PLAN.sitelink-gold.jsonl` (sha256
`d8a78e58f02255570bd6a7c94dd42b0a04fdbddadca440b9bc12e39dabc28b81`; built with
`sitelink_plan.py --pilot` from the fresh read-only export of 2026-09-23T11:01:49Z, its sitelinks
resolved again at 14:18 - every pin the same revision as the first build's, Hebbariyeh Roman Temple
withheld) reruns, with **up to three Wikipedia articles in other languages than English of the
site's own Wikidata item** added to the evidence - each pinned to a revision and cited by its
permalink - and **no search**, the **39 fields the mass run's finder called UNVERIFIABLE on the 18
gold-standard sites that have such a field and a usable non-English article**: period_start 15,
description 10, card_description 8, site_type 5, country 1. Two batches (`slkg-0001`,
`slkg-0002`), 49 articles (dewiki 12, eswiki 11, frwiki 7, itwiki 5, ruwiki 3, arwiki 2, hywiki 2,
and one each of brwiki, cawiki, cywiki, fawiki, nlwiki, plwiki, skwiki); 14 sites get three
articles, 3 two, 1 one. For every one of the 39 fields a human verdict exists in
`output/remediation/gold_standard/` (CORRECT 23, WRONG 10, UNVERIFIABLE 6).

Of the 59 UNVERIFIABLE answers on the 26 gold-standard sites that have one (the search pilot's 59),
20 are not in the plan and are not scored: 14 at 5 sites have no item the lane may use (one site
carries none, two share theirs with another curated row, one is a duplicate candidate of the
external-id repair's wave 3, one carries the village its temple stands in), 6 at 3 sites have no
usable non-English article. The finder and the reviewer are the mass run's
(`opencode-go/deepseek-v4.1-flash`, the discover prompt frozen at round 5); nothing is asked of
MiniMax.

The evidence was fetched dry before this was written (fetch only, no model call, its own scratch
ledger, `runs/sitelink-gold-dry3`): 181 requests, 180 answered; the other, the narrowed Wikidata
query of The Merry Maidens, drew a WDQS 429 asking for 120 s and was recorded as that target's
failure, as the fetch stage records every such answer. 49 of 49 articles stored, 0 cut at the page
cap, 0 refused; all 18 sites under the 64,000-character bound (largest 29,925); 0 articles
unaccounted for.

## Pass thresholds (all must hold)

The four thresholds of `SEARCH_PILOT.md`, copied verbatim:

1. **No fabricated citation.** 0 finder answers whose quoted source text is not in the evidence
   the finder was shown (`discover_stage.source_problems`, the writer's RULE_CITATION check).
2. **No harmful decision.** 0 fields decided WRONG by the finder, *not* refuted by the reviewer,
   where the human verdict is CORRECT. (A WRONG the reviewer refutes is not written.)
3. **Agreement.** Of the fields the pipeline decides (finder CORRECT, or finder WRONG that the
   reviewer does not refute), at least 90 % agree with the human verdict.
4. **Transport.** Every search ends in a stored result or a recorded failure; 0 slots unaccounted
   for; the run is not stopped by an auth or contract error.

**How this lane reads threshold 4** (a stated definition, not a change of its text): the lane buys
no search - what it buys in a search's place is the fetch of a pinned article. So a *search* is one
sitelink article of the plan, its *stored result* is the article's evidence file, a *recorded
failure* is a failure the fetch stage records for it in `fetch.json` (a fetch that failed, or an
answer refused as no longer the pinned article), and a *slot* is an article: 0 articles
unaccounted for. The scorer counts exactly that (`score_search_pilot.py --lane sitelink`,
`TRANSPORTS["sitelink"]`). Thresholds 1-3 need no reading: their objects are the finder's answers
and the fields, the same in both lanes.

The first version of this document (commit 2fe862b, sha256 `47f9adc4...8dac6`) rewrote threshold
4's sentence with the articles in it and still called the four thresholds "word for word"; an
independent check found the difference before any model call, and this version restores the text
and states the reading instead.

Scored by `output/remediation/tools/score_search_pilot.py --lane sitelink` (the search pilot's
scorer, generalised, not copied): the sealed block is what the pilot is passed or failed on; the
writer's own decision and each writer rule's cost are printed beside it, not gated.

## Reported, not gated

- The share of the 39 fields that move from UNVERIFIABLE to a decision (the lever itself).
- What the writer would write (`write_stage.load_plan`): only `period_start`, `site_type` and
  `country` are writable; `description` and `card_description` are measured, never written.
- The model cost per call from the ledger's provider-reported `cost_usd`.
- Articles refused at fetch time (edited since the pin, deleted, redirected) and articles cut at
  the page cap.

## How it runs (orchestrator)

```bash
cd /c/PythonProjects/AncientMap && export PYTHONIOENCODING=utf-8
T=output/remediation/tools; PY=./.venv/Scripts/python.exe
P=output/remediation/sitelink/pilot/PLAN.sitelink-gold.jsonl
R=output/remediation/phase3_runner/runs/sitelink-gold
sha256sum $P    # must print d8a78e58...8b81, or this document does not apply
$PY scripts/remediation/phase3/mass_run.py --plan $P --run-dir $R \
    --log-dir output/remediation/logs/sitelink_gold                     # dry: lists the calls
$PY scripts/remediation/phase3/mass_run.py --plan $P --run-dir $R \
    --log-dir output/remediation/logs/sitelink_gold --live --jobs 2 --max-calls 60 --max-usd 1
$PY $T/review_all.py --lane sitelink --run-dir $R \
    --log-dir output/remediation/logs/review_sitelink_gold --cap-usd 1
$PY $T/score_search_pilot.py --lane sitelink
```

## If a threshold fails

The lane's run does not start. The failure is recorded here and in `AUDIT_LOG.md` with the cases,
and the cause is fixed (the article order, the evidence shape, or the route itself) before a new
pilot with a new run directory.
