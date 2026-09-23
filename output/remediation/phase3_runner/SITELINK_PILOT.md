# The sitelink lane's pilot: thresholds fixed before the first model call

Written 2026-09-23, before any model call of this pilot; committed before one is bought. The sha256
of this file is recorded in `output/remediation/AUDIT_LOG.md` together with the results, so the
thresholds cannot be moved after the numbers are known.

## What is measured

The plan `output/remediation/sitelink/pilot/PLAN.sitelink-gold.jsonl` (sha256
`593501abbfc21ec6e3e9cc6f09dc9a968ac5f1bdc9f0b7e194165a1d7851b522`; built with
`sitelink_plan.py --pilot` from a fresh read-only export, 2026-09-23T11:01:49Z, byte-identical to
the first build of 10:32 from the export of that time) reruns, with **up to three Wikipedia articles
in other languages than English of the site's own Wikidata item** added to the evidence - each
pinned to a revision and cited by its permalink - and **no search**, the **41 fields the mass run's
finder called UNVERIFIABLE on the 19 gold-standard sites that have such a field and a usable
non-English article**: period_start 16, description 10, card_description 9, site_type 5, country 1.
Two batches (`slkg-0001`, `slkg-0002`), 52 articles (dewiki 12, eswiki 11, frwiki 7, itwiki 6,
arwiki 3, ruwiki 3, hywiki 2, fawiki 2, and one each of brwiki, cawiki, cywiki, nlwiki, plwiki,
skwiki); 15 sites get three articles, 3 two, 1 one. For every one of the 41 fields a human verdict
exists in `output/remediation/gold_standard/` (CORRECT 25, WRONG 10, UNVERIFIABLE 6).

Of the 59 UNVERIFIABLE answers on the 26 gold-standard sites that have one (the search pilot's 59),
18 are not in the plan and are not scored: 12 at 4 sites have no item the lane may use (one site
carries none, two share theirs with another curated row, one is a duplicate candidate of the
external-id repair's wave 3), 6 at 3 sites have no usable non-English article. The finder and the reviewer are the mass run's (`opencode-go/deepseek-v4.1-flash`,
the discover prompt frozen at round 5); nothing is asked of MiniMax.

The evidence was fetched dry before this was written (fetch only, no model call, its own scratch
ledger): 191 requests, all answered; 52 of 52 articles stored, 0 cut at the page cap, 0 refused;
all 19 sites under the 64,000-character bound (largest 29,925); 0 articles unaccounted for.

## Pass thresholds (all must hold)

The four thresholds of `SEARCH_PILOT.md`, word for word; only threshold 4's object is the lane's
own, because this lane buys articles, not searches (the scorer's `--lane sitelink` transport).

1. **No fabricated citation.** 0 finder answers whose quoted source text is not in the evidence
   the finder was shown (`discover_stage.source_problems`, the writer's RULE_CITATION check).
2. **No harmful decision.** 0 fields decided WRONG by the finder, *not* refuted by the reviewer,
   where the human verdict is CORRECT. (A WRONG the reviewer refutes is not written.)
3. **Agreement.** Of the fields the pipeline decides (finder CORRECT, or finder WRONG that the
   reviewer does not refute), at least 90 % agree with the human verdict.
4. **Transport.** Every sitelink article ends in a stored evidence file or a recorded failure (a
   fetch failure, or an answer refused as no longer the pinned article); 0 articles unaccounted
   for; the run is not stopped by an auth or contract error.

Scored by `output/remediation/tools/score_search_pilot.py --lane sitelink` (the search pilot's
scorer, generalised, not copied): the sealed block is what the pilot is passed or failed on; the
writer's own decision and each writer rule's cost are printed beside it, not gated.

## Reported, not gated

- The share of the 41 fields that move from UNVERIFIABLE to a decision (the lever itself).
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
sha256sum $P    # must print 593501ab...b522, or this document does not apply
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
