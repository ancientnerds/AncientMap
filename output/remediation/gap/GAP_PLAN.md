# The gap run: the 802 questions the mass run holds no readable verdict for (planned 2026-09-22)

Planned, measured offline, **not run**. Built by `output/remediation/tools/gap_plan.py` (its docstring
states the rules); every number below is re-derivable with it from `runs/mass`, a production export
and two read-only Wikidata lookups.

## What is asked

| class | fields | sites | where it is recorded in `runs/mass` |
| --- | --- | --- | --- |
| over the evidence bound (`MAX_EVIDENCE_CHARS = 64,000`) | 760 | 152 | `model.json` `skipped`: "the evidence is N characters, over the 64000-character bound" |
| empty model stream | 5 | 5 | `model.json` `failures` |
| no readable `VERDICT:` line (`discover_stage.parse_answer`) | 37 | 37 | `answers/` |
| **total** | **802** | **194** | 25,020 = 24,255 answered + 760 + 5; the 37 are among the 24,255 |

`PLAN.gap.jsonl` (`output/remediation/phase3_runner/`, not versioned by the `PLAN*.jsonl` rule):
13 batches `gap-0001` .. `gap-0013` (15 sites, the last 14), sha256
`34df97e2fec763a24b53394bbc0d098c0a64867204a32f450cc6895e7c97cd27` on 2026-09-22. The batch ids are
the gap lane's (`lanes.py`): no journal stamp and no `APPLIED.json` of the mass lane can match one.

Every record comes from a **fresh read-only export** (2026-09-22T21:46:19Z: 194 `unified_sites`, 194
`card_stats`, 4,618 curated `wikidata_qid` rows), not from the 2026-09-20 snapshot. Measured against the
snapshot: 2 asked fields moved since (Easter Island and Kutaisi `country`, the mechanical lane), and 7
fields that are *not* asked were written by phase 3 (e.g. Chalkotheke `period_start` -1500 -> -450).
Each record names the fields it asks (`rerun_fields`: all five for the 152, one or two for the 42), and
the writer refuses every other field of the site (`write_stage.RULE_NOT_RERUN`).

## The evidence routes

* **Wikidata, narrowed** (`wikidata_route: "narrow"`, `fetch_stage`): 178 sites. The full
  `wbgetentities` answer is replaced by one WDQS query (English label and description, best-rank P31,
  P17, P131, P2348, P625 with labels) and `wbgetclaims` for P571, P580, P582 and P1619 - dates never
  through WDQS, which rewrites them (`-2560` -> `-2559`, Julian -> Gregorian; measured). **This is a
  convention split**: the 4,852 sites judged in the mass run saw the full entity JSON, the 194 gap sites
  see the narrowed rendering.
* **Wikidata withheld**: 12 sites, each with its reason in the record (`withheld_wikidata_qid`):
  - 9 ids the reviewed repair replaces (`output/remediation/qid_repair/`), not applied yet: Argos
    Peloponnese, Clare Suffolk, Estipeon, Gog Magog Hills, Tlalpan (Q309 "history"), Calleva
    Atrebatum (Q23498 "archaeology"), Stabiae (a rock band), Tomb of Artaxerxes III (Persepolis),
    The Wolseong Belt (the World Heritage parent);
  - Tikal, unresolved in the repair (named Tikal, describes Mundo Perdido);
  - Knossos and Dilmun Burial Mounds - A'ali West, whose items are carried by two curated sites each
    (a shared item is treated as a parent or generic one). A link the repair replaces does not count
    as sharing, which keeps Persepolis' own Q129072.
* **no Wikidata id at all**: 4 sites (Finiq Archaeological Park, The Ancient Tower of Thimonia,
  Karabölücülü Harabeleri, Patara Antique Theatre).
* **English article through the item's sitelink** (W12): the 5 gap sites whose article by stored name
  was missing in the mass run and whose item is not shared - Andriake Ancient City -> *Andriake*,
  Orchomenus Boeotia -> *Orchomenus (Boeotia)*, Nymphaion Crimea -> *Nymphaion (Crimea)*, Templo de
  Bel -> *Temple of Bel*, Achilleion Thessaly -> *Achilleion (Thessaly)*.

If the repair is applied first, re-run `export`, `sitelinks` and `plan`: the 9 repaired sites then get
their new item through the narrow route (expected: narrow 187, withheld 3, no-qid 4).

## Measured offline, no model called

A scratch run (`output/remediation/gap/scratch/`, ignored): `run.py prepare` of the plan and
`run.py fetch --live` of all 13 batches with a scratch ledger and pacing dir - 1,152 requests, all
read-only (Wikipedia 212, Wikidata API 725, WDQS 215). Then the discover stage's own evidence
selection and bound (`gap_plan.py measure`: `model_stage.evidence_excerpts` + the 64,000 check):

| | before (mass run) | after (narrowed) |
| --- | --- | --- |
| the 152 over-bound sites | median 78,134, min 64,128, max 122,880 characters | **all 152 fit**: median 29,763, max 63,279 |
| the other 42 sites | fitted | fit, max 11,594 |
| narrowed Wikidata evidence per site | full entity, 92 of 152 cut at the page cap | median 1,277, max 1,971 characters |

**So no site of the gap is refused by the bound, and `MAX_EVIDENCE_CHARS` stays 64,000.** The margin
is thin: the largest site (Stonehenge) is 721 characters under the bound, and a live re-fetch reads the
pages as they are that day. A site that crosses it is refused whole again - the sensor stays as it is.

**The enwiki-at-cap remainder, decided from these figures:** 14 sites carry an English extract cut at
the 61,440-byte cap (Ajanta Caves, Baalbek, Barcelona, Bilbao, Earl Shilton, Easter Island, El Perú,
Louisville, Seville, Stonehenge, The Great Pyramid of Giza, Valencia, Varna Bulgaria, Western Wall).
All 14 fit with the narrowed Wikidata evidence, so route (a) is taken **without raising the bound**:
the capped extract is judged with the explicit `TRUNCATION_MARKER` after its last byte ("[truncated:
this page was cut at the fetch stage's 61,440-byte page cap ...]"), which the prompt and the citation
check both see. Route (b), a lead-section (`exintro`) route, would refuse no fewer sites and read less,
so it was not built.

**WDQS is the fragile host.** The first query form (one pattern over a variable predicate) drew seven
`429` answers with `Retry-After: 120` and six read timeouts; the fetch stage recorded each as a failed
target, as designed. The query now names each property's predicates (Q99151: 20.0 s -> 0.3 s) and
WDQS is paced at one query per second (`HOST_MIN_INTERVAL_OVERRIDES`). One re-fetch of the six
affected batches filled all seven: 0 failed targets.

## What the run needs from code this lane does not own

`discover_stage.plan_site` asks all five fields of every site; it does not read `rerun_fields`. Until it
does, the 42 partly-asked sites buy 5 calls each instead of their 1-2: 970 finder calls instead of 802
(about $0.2 more at the measured $0.00096 a call). The extra answers can never be written - the writer
refuses them (`field-not-asked-in-this-run`) - but the reviewer would review their `WRONG` findings too.

## The sequence (orchestrator; production is only read until step 8)

```bash
cd /c/PythonProjects/AncientMap && export PYTHONIOENCODING=utf-8
T=output/remediation/tools; PY=./.venv/Scripts/python.exe
# 0. (recommended first) the external-id repair - output/remediation/qid_repair/PLAN.md
# 1. the plan, from a fresh export
$PY $T/gap_plan.py census       # 802 questions over 194 sites: empty-stream 5, no-verdict 37, over-bound 760
$PY $T/gap_plan.py export       # unified_sites 194, card_stats 194, site_external_ids 4618 (read-only)
$PY $T/gap_plan.py sitelinks    # read-only Wikidata; 5 resolved today
$PY $T/gap_plan.py plan         # 13 batches, 194 sites, 802 questions
# 2. evidence first, and once more for any failed target (WDQS 429s), before a single call is bought
$PY scripts/remediation/phase3/run.py prepare --plan output/remediation/phase3_runner/PLAN.gap.jsonl \
    --run-dir output/remediation/phase3_runner/runs/gap
for b in $(seq -f 'gap-%04g' 1 13); do $PY scripts/remediation/phase3/run.py fetch --live \
    --run-dir output/remediation/phase3_runner/runs/gap --batch-id $b \
    --pacing-dir output/remediation/logs/pacing; done      # run this loop twice
$PY $T/gap_plan.py measure --run-dir output/remediation/phase3_runner/runs/gap \
    --out output/remediation/logs/gap_measure.json          # expect: 194 fit, 0 over
# 3. the finder: dry, then live; read DRIVER_EXIT from the log, not the wrapper's exit code
$PY scripts/remediation/phase3/mass_run.py --plan output/remediation/phase3_runner/PLAN.gap.jsonl \
    --run-dir output/remediation/phase3_runner/runs/gap --log-dir output/remediation/logs/gap
$PY scripts/remediation/phase3/mass_run.py --plan output/remediation/phase3_runner/PLAN.gap.jsonl \
    --run-dir output/remediation/phase3_runner/runs/gap --log-dir output/remediation/logs/gap \
    --live --jobs 4 --max-calls 1000 --max-usd 5
# 4. the reviewer (ceiling = this pass's own spend)
$PY $T/review_all.py --lane gap --cap-usd 2
# 5. the dry plan, the hand-read, the holds (the plan is refused once the lane has written a batch)
$PY $T/write_dry_all.py --lane gap            # -> logs/_write_dry_gap/ALL_ROWS.jsonl
$PY $T/show_rows.py --lane gap --count 200; $PY $T/scan_rows.py --lane gap
#    a held row goes into logs/_write_apply_gap/HOLDS.jsonl: {"change_key": ..., "hold_reason": ...}
#    - copy the change key from ALL_ROWS.jsonl: a key that names no planned row is refused
# 6. the gate, dry: prints "plan checked: N open batches ..." and "dry run, nothing is written"
$PY $T/write_gate.py --lane gap --step 100
# 7. read the dry-run numbers; then (production write, owner's rule: steps of 100, a check after each)
$PY $T/write_gate.py --lane gap --apply --step 100
#    a writer call that wrote less than it was handed, or a read-back deviation, STOPs the wave;
#    the batch gets STOPPED.json (never APPLIED.json) and a resume refuses it until a person decides
# 8. the acceptance, both lanes
$PY $T/verify_writes.py --lane gap            # RESULT: 0 deviation(s)
$PY $T/verify_writes.py                       # mass lane: 994 carried, 80 withheld unchanged, 0
#    after the UK lane has written: add --allow-stamp 2026-09-22_mechanical-uk-parts to both;
#    its re-spelled rows then read "superseded by <stamp>: 5", any other later stamp is a deviation
```

A question that ends as a named failure is asked once more - not by `mass_run.py`, which counts a
batch with named failures as done, but by `run.py judge --run-dir output/remediation/phase3_runner/runs/gap
--batch-id <gap-NNNN> --stage finder --live`, which reuses every answer on disk and buys only the
missing one. After a second failure on the same (site, field) it is reported, not retried (HUMAN_ONLY
section C).
