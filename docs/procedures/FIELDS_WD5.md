# WD5: re-check every value no source stands behind (D10, D12, D19, D25 fields part)

Status: **built 2026-10-09 on `fix/db-final-p2-fields-adv` (base: the lane `wd5` foundation, `49ab4c6`); nothing
run on the lane, nothing written; the first calibrations of 2026-10-09 are in 3.0.** Read `FIELDS_WD1.md`, `FIELDS_WD3.md` (sections 4.1-4.7, the steps are the
same) and `FIELD_CONTRACT.md` first: this file states what lane wd5 adds. The map is
`output/remediation/final-2026-10-08/plans/fields.md`; the decisions are `OWNER_DECISIONS_2026-10-08.md`
(D6 roles, D10 MiniMax writes, D12 rule-made periods, D19 coordinates) and `MASTER_PLAN.md` (X3, X6).

## 1. What the lane is, and who answers

One question per site asks the fields that stand without a source: a period a rule made (1,254 sites), a field a
MiniMax model decided or wrote (its calibration failed at 64.71 %), a point nobody sourced. The rule is `recheck`
(`rule.py`): one quote from one source, WD4's answer kinds, the BP reader (`answers.states_bp`). The plan
replaces a stored value only where the journal says nobody sourced it, clears a rule-made start to the label
`Undated`, and restores from the journal what a MiniMax agent wrote when Claude can source nothing.

| role (`roles.ROLES`) | model, effort | does | calibrated on |
|---|---|---|---|
| `field_researcher` | **Sonnet 5.5 high** (Opus from the tier move of 2026-10-09, `fr-general-001` failed, to the owner move D36 of the same day, see 3.0b) | answers the questions; recorded `--role field_researcher` | `fr-general-001` (released under D36) and `fr-bp-001` (passed 0.92); the Opus runs `-002` stay as the comparison |
| `adversarial` | **Sonnet 5.5 high** (Opus until D36) | tries to break every cell the plan would write | `adv-truth-002` (the 50 cells of `adv-truth-001`, answered by Sonnet; `-001` was Opus and no longer binds) |
| `operator` | Haiku 5.5 low | runs the scripted steps (no judgement) | a scripted dry run (`scripted_dry_run`), not in this file |

**An answer is the role's or it is not imported.** `handoff.py import` refuses (by name, nothing written) an answer
of a wd5 run whose `answered_by` names no `field_researcher:` role or whose stamp is not the registry's model for the
role; `adversarial.py import` does the same for `adversarial`. A tier move after a failed calibration is an edit of
`roles.ROLES` **and its record** in `roles.APPLIED_ESCALATIONS` (the failed verdict's id and reason; the registry is
held to those records when `roles.py` is imported), sealed and calibrated again - the recording command of every brief
names the role, and the model of the wd5 brief, the pools' round and the dispute and enrichment briefs is read from the
registry, never written out again. The lane E description writer is **not** the field researcher: it is the role
`enrich_writer` (Sonnet 5.5 high, calibration set `enrich-writer`, sealed as `enrich-writer`), so the move did not
change it.

## 2. The pieces added to the foundation

| module | does |
|---|---|
| `fields/carry.py` | the 23 refused points (D19): their existing counted decisions are carried into the run, not asked again |
| `fields/wiki.py`, `handoff.py wiki-text` | the shared Wikipedia cache the agents read first (Wikimedia throttles the IP from four parallel agents on) |
| `handoff.py copy-hints` | copies WD4's `ORIGINAL_PERIODS.jsonl` (the 2025 import's claim, shown in the question as a claim to confirm or contradict) |
| `fields/adversarial.py` | the Opus re-check: select, export, brief, import, re-ask, apply |
| `fields/pools.py` | the calibration pools (`build-general`, `build-bp`, `build-adversarial-truth`), their comparisons, the quote audit |
| `calibrate_claude.py` | truth pools (`--truth`), a named comparison, the bound on undecided cells (`--max-undecided-excess`) |
| `population.read_history` | now also reads WD3's pilot (80 sites answered before the run was built without them) |
| `plan.py wave` | for a wd5 run reads only the DECISIONS.jsonl the re-check was applied to |
| `wd5_wave.sh` | the write loop of one wave (like `wd3_wave.sh`) |

## 3. The calibration (before the first answer of the lane)

Thresholds are sealed **before** the run (`calibrate_claude.py seal`), per the map: at least 90 % agreement on the cells
both sides decide, 0 false sources (every disagreement's URL and quote spot-checked, O18), and - for the two researcher
pools - the fresh share of cells nobody decided not more than 10 points above the gold's. The adversarial pool is held
to 90 % **per class** instead (3.0). A failing role moves up one tier and is calibrated again; the record goes to
AUDIT_LOG.

**3.0 What the first round measured (2026-10-09, `output/remediation/calibration/verdicts/`) and what changed.**

| calibration | role | result | consequence |
|---|---|---|---|
| `fr-general-001` | `field_researcher`, Sonnet | agreement 0.8636 (76 of 88 units) < 0.9 sealed, 0 false sources, undecided excess 0.0331 | **failed**: tier move Sonnet to Opus (`roles.APPLIED_ESCALATIONS`); measured again as `fr-general-002` |
| `fr-bp-001` | `field_researcher`, Sonnet | 0.92, passed | sealed against the Sonnet entry; the entry changed, so the gate (`require_passed`) no longer accepts it: measured again as `fr-bp-002` |
| `adv-001` | `adversarial`, Opus | agreement 0.575 (23 of 40 units) < 0.9, 0 false sources | **failed, held** (no tier above Opus); its design is replaced, not the role |

**3.0b Owner decision D36 (2026-10-09): Sonnet instead of Opus, and what it does to the calibrations.** The weekly Claude
quota stood at 69 % after one day. The calibrations had measured no Opus advantage (field research 0.864 Sonnet against
0.871 Opus; BP 0.92 against 0.88; the card fact checker failed the same sets on both), so the owner moved
`field_researcher`, `fact_checker`, `web_verifier`, `card_writer`, `hook_rater` (at medium), `adversarial` and
`code_review` to Sonnet 5.5; `pilot_judge` stays on Opus xhigh (small spot checks and pilot verdicts), the image roles,
`enrich_writer` and `operator` did not move. The move is a record, not a silent edit: seven **owner moves**
(`"kind": "owner"`) in `roles.APPLIED_ESCALATIONS`, each with the decision, the models, the effort the role has
afterwards, the reason and the calibrations it rests on; `check_applied_escalations` holds the registry to the chain of
tier moves and owner moves in order, model and effort.

* A calibration that failed on Sonnet with a tier move is **released under the decision** while the registry holds
  Sonnet again: `calibrate_claude.py release ... --owner-decision D36` and `teaser/calibrate.py release ... --owner-decision D36`
  accept a failed verdict WITH a tier move only when the role's registry entry is the verdict's model and an owner move
  names that decision and lists the calibration among its evidence. Everything else of the release stays (verdict, seal
  and role digests, evidence files, refusals); the gates (`require_passed`, `standing`) re-check the decision every time
  and say `released (owner decision D36)`. `fr-bp-001` (Sonnet, passed) stands again by itself: the registry entry is the
  one it was sealed against. `fr-*-002`, `adv-truth-001` and the Opus calibrations of the card lane (`teaser-2026-10-09c`)
  no longer bind the roles they were sealed for.
* A **candidate-model trial** calibrates a role with another model without touching the registry
  (`calibrate_claude.py seal --candidate-model M`; `teaser/calibrate.py seal --candidate-role R --candidate-model M`, then
  `export`, `agents` and `evaluate` with the same `--candidate-model`). The seal binds the digest the role would have with
  M; the agents record with `opus_handoff.py answer --role R --model M --candidate-model M`; the verdict names the model
  that passed; a failed trial moves nobody; and no gate accepts the verdict for the registered role until an owner move
  has registered M.
* **Batch sizes** are an explicit, recorded export parameter and larger for new runs (every agent re-reads its brief and
  the repository instructions, a fixed cost per batch): fields questions per batch 8 to 12 (`handoff.py export --batch-size`),
  the adversarial check 8 to 12 (`adversarial.py export --batch-size`), the card lane's web stages 5 to 8 and its
  calibration web roles 5 to 8 (`--batch-size`; writers and checkers stay at 15), lane WC's check, verification and
  judge rounds 5 to 10 (`wc/cli.py ... --batch-size`). Each round records the size it used; a re-ask or a later round of a
  run exported before the change keeps that run's size (8, 5, 5, and `RUN.json` without `batch_sizes` for the cards).
  The calibration pools keep their shapes (8 per batch, 7 adversarial batches).

**3.0a The second round (2026-10-09) and the release.** `adv-truth-001` (adversarial, Opus) **passed** at 0.94 (47 of 50).
`fr-general-002` (0.871, 81 of 93) and `fr-bp-002` (0.88, 22 of 25) are Opus and **failed with 0 false sources, held**:
Opus has no tier above, and the code says "the owner decides". The owner is away and delegated full autonomy (D8), so the
orchestrator **released** both, because the O18 spot check found every disagreement sourced and equally valid
(`fr-general-002`: another `source_url` page or a defensible type) or a machine fetch failure while the quote stands on the
page (`fr-bp-002`: Cova Negra, Apidima, Kozarnika), and because every cell the wave writes also passes the calibrated Opus
adversarial check and the machine quote check first. A release is a record, never an edit of the verdict:

```
$PY scripts/remediation/calibrate_claude.py release --id fr-general-002 --decided-by TEXT --reason TEXT \
    --evidence verdicts/fr-general-002.json fr-general-002/COMPARISON.json <spot-check note>
```

It is refused for a verdict that passed, one with a tier move, one that is not held and a missing verdict, and it writes
`releases/<id>.json` once: the sha256 of the verdict, the seal, the role's registry entry and every evidence file. The
gate (`require_passed`) counts a release like a pass while all of that still hashes as released, refuses a release that
moved by name, and `plan.py wave` records in `WAVE.json` how each calibration stands (`passed` or `released`, with the
decider). The cards lane has the same pair in `teaser/calibrate.py release` and `standing`.

`adv-001` and `fr-general-001` stay recorded as failed; nothing of them is edited. **Why `adv-001`'s design was
replaced.** Its gold was the `opus_audit` keep and revert verdicts on the DeepSeek Phase-3 writes - a different
question, answered on different evidence (the finder's quote and the evidence files of the audit), asked of the
checker in the form of the wd5 check. Of its 17 disagreements, 12 carried no source on either side: the checker and
the audit disagreed about writes neither had a page for, and a `confirm` given because no counter-quote was found is
not "the value is right". So `adv-001` measured the drift between two judgements, not the role. The replacement,
`adv-truth-001`, asks cells whose truth is known:

* **known wrong** (25 cells, `reject` is right): the periods the 2026-10-08 sample audit confirmed wrong (Lake Mungo
  -500, Broadbury Castle -4000, Tappoch Broch -800, Hodson Stone Circle -4000) and the band-rule Palaeolithic caves at
  -500 (Le Moustier, Bruniquel Cave, Cro-Magnon Rock Shelter, Apidima Cave, Eartham Pit Boxgrove), each under a
  sentence of the site's own cached Wikipedia article that does not state the value (`pools.KNOWN_WRONG_PERIODS`, site
  ids read from production, read-only, on 2026-10-09); and 16 seeded perturbations of WD1 two-source keeps - a start in
  a bucket at least three of nine away, a wrong canonical type no quote holds a word of, a point moved 40-120 km - each
  under the original quotes, which state the true value;
* **known right** (25 cells, `confirm` is right): WD1 two-source keeps as decided, with their sources.

Every cell has the one form of a keep with a neutral reasoning, so nothing but the value and the quotes tells the
classes apart. The comparison `adv-known-truth` counts an `unclear` as a miss in its class (a known-wrong cell that is
not rejected is not caught) and holds the sealed 0.9 to the reject rate on the known-wrong cells **and** to the confirm
rate on the known-right ones, with 0 false sources. `unclear` therefore needs no separate bound. Tappoch Broch is the
one contestable known-wrong cell: the article calls it an iron-age broch (the fixed table's `iron age` is -800) while
the audit found it dated to the last centuries BC or the first AD; with 25 cells per class, one such miss is within
the 0.9.

```bash
PY=./.venv/Scripts/python.exe
F=scripts/remediation/fields
CAL=scripts/remediation/calibrate_claude.py
CR=output/remediation/calibration            # <id>/ is the copy the agents answer into, <id>-run/ its run
POOLS=$CR/pools
```

Run from the repository root of the checkout that holds the run tree. `<id>` is `fr-general-002`, `fr-bp-002`,
`adv-truth-001` (the `-001` calibrations of the first round are recorded and stay; a seal, a copy and a verdict are
written once, so each new one has an id and a directory of its own).

**3.1 Build and seal** (each build prints the exact `seal` command; run it as printed):

```bash
$PY $F/pools.py build-general     --out $POOLS/fr-general-002 --seed 20261010   # the same 60 sites of WD1 round 0 as -001, 8 batches
$PY $F/pools.py build-bp          --out $POOLS/fr-bp-002      --seed 20261010   # the same 25 sites as -001, 4 batches, truth file
$PY $F/pools.py build-adversarial-truth --out $POOLS/adv-truth-001 --seed 20261010   # 50 cells of known truth, 7 batches, truth file
# then the three printed `calibrate_claude.py seal ...` commands
```

A MiniMax agent's reasoning is no BP gold (D10): only the attempts of WD1 and of Claude agents count.
The BP set holds the six sites the 30-site audit confirmed in "< 4500 BC" (Le Moustier, Bruniquel, Cro-Magnon,
Apidima, Boxgrove, Lake Mungo), one bucket-edge case (a number whose tolerance reaches 6,450 BP) and a seeded fill of
sites whose earlier reasoning dated them in one bucket; `TRUTH.json` says on what each rests (`audit-confirmed`,
`earlier-reasoning`, `edge`). The seal pins the pool, the truth file, the role entry and `roles.py`.

**3.2 Prepare, answer, measure** (per pool; at most 3 agents at once):

```bash
$PY $F/pools.py prepare --id <id> --run $POOLS/<id>/run
```

Agents: one per batch B of `$CR/<id>/`, a fresh agent running as the role's model, with the text of

- `fr-general-002`, `fr-bp-002`: `$PY $F/handoff.py brief --run $CR/<id>-run --handoff $CR/<id> --batch-id B`. The
  general pool is WD1's own question, whose brief leaves the model open: the agent records with `--model
  claude-opus-5-5 --role field_researcher` (the BP brief says so itself, from the registry);
- `adv-truth-001`: `$PY $F/adversarial.py brief --adv $CR/adv-truth-001-run --handoff $CR/adv-truth-001 --batch-id B`
  (records with `--model claude-opus-5-5 --role adversarial`).

Then, with every question answered:

```bash
$PY scripts/remediation/opus_handoff.py validate --dir $CR/<id>
$PY $F/handoff.py import --run $CR/<id>-run          # fr-general-002 and fr-bp-002: fetches each quoted page, checks each quote
$PY $F/adversarial.py import --adv $CR/adv-truth-001-run   # adv-truth-001: parses, role-checks, finds the counter-quotes
$PY $F/pools.py compare --id <id>                    # writes COMPARISON.json
$PY $F/pools.py audit-quotes --id <id>               # the quotes not found, the sources of each disagreement
$PY $CAL verdict --id <id> --false-sources N         # N: your own count after reading audit-quotes
```

`compare` of `fr-bp-002` refuses until its calibration run was imported (the found-quote half of "resolves into the
right bucket with a found quote"). An `unresolved` answer is a miss in the BP pool and in `adv-truth-001` (an `unclear`
is a miss in its class); in `fr-general-002` it is an undecided cell, bounded by `--max-undecided-excess`. `verdict`
exits 1 on a fail and prints the `tier_move` or, at Opus (both roles now), `held`: the owner decides.

## 4. The population (files only; production is read, never written)

```bash
W5=output/remediation/fields/wd5
W5P=output/remediation/fields/wd5-pilot
H=output/remediation/handoff/fields-wd5
```

1. Refresh the harvest (as `FIELDS_WD3.md` 4.1; do not copy `wd3/pages`, check `du` first - the harvest copy is 205 MB):
   `mkdir -p $W5 && cp -r output/remediation/fields/harvest $W5/harvest`, then
   `$PY $F/harvest.py --root $W5/harvest export`, **straight after** `$PY $F/population.py --out $W5 export`
   (STORED, LINKS, POINTS and MADE.jsonl: who made each value, from the journal), then
   `$PY $F/harvest.py --root $W5/harvest fetch` until nothing is fetched, and
   `$PY $F/classify.py --root $W5/harvest unmapped` must print `[]`.
2. Pilot of 80 and the rest:
   ```bash
   mkdir -p $W5P && cp $W5/STORED.jsonl $W5/LINKS.jsonl $W5/POINTS.jsonl $W5/MADE.jsonl $W5/SEEDS.jsonl $W5P/
   $PY $F/population.py --out $W5P build --root $W5/harvest --stage wd5 --pilot 80 --seed 20261010
   $PY $F/population.py --out $W5  build --root $W5/harvest --stage wd5 --without $W5P
   ```
   `COUNTS.json` of each: `population.why` (rule-made, minimax-answered, unsourced-point), `skipped_sourced`.
3. Before the first export of **each** run: the hints, and - rest run only - the carried points:
   ```bash
   $PY $F/handoff.py copy-hints --run $W5P --from output/remediation/fields/wd4/ORIGINAL_PERIODS.jsonl
   $PY $F/handoff.py copy-hints --run $W5  --from output/remediation/fields/wd4/ORIGINAL_PERIODS.jsonl
   $PY $F/carry.py carry-points --run $W5
   ```
   `copy-hints` prints how many of the run's period questions have a hint (WD4's file covers 2,229 sites; a question
   without one is asked without it). `carry-points` writes `CARRIED.jsonl` and `CARRIED.json`: the points whose earlier
   decision is a counted, Claude-answered `replace`, made about the point the run holds, and which the country check
   (coast tolerance 2.5 km, Cyprus one island) agrees with now; `not_carried` says why for each other of the 23
   (a MiniMax answer is asked again; Kosovo, Narona, Heracleion, Flevum are asked, X3). Measured on the real
   records (2026-10-09, with the real boundary file): **16 of the 23 are carried**; asked again are Narona,
   Heracleion, Achladia (the point lies in Greece, the site says Germany), Flevum (Netherlands for Germany), and
   Clachtoll Broch, Stairhaven and Kaljaja, which a MiniMax model answered. A pilot that holds one of the 23 asks it.
   Both files are pinned: an edit is refused at the export. A WD1 decision carries no `model` key: the carried row
   gets the model the model census (`output/remediation/model_census/ANSWERS_TRUE_MODEL.jsonl`, `--census` to name
   another) found behind its answer file (not the Opus stamp), and a WD1 decision the census does not hold refuses the
   whole `carry-points`.

## 5. The rounds and the re-check

**5.1 Pilot** (80 sites, Sonnet high, `field_researcher`; at most 3 agents, 403 and 429 are a throttle, never a finding):

```bash
$PY $F/handoff.py export --run $W5P --handoff $H-pilot-r0
$PY $F/handoff.py brief  --run $W5P --handoff $H-pilot-r0 --batch-id B   # the instruction of batch B's agent
$PY scripts/remediation/opus_handoff.py validate --dir $H-pilot-r0
$PY $F/handoff.py import --run $W5P
# while REASK.json names fields: export-reask --handoff $H-pilot-r1, answer, validate, import; once more on -r2
$PY $F/handoff.py pilot-report --run $W5P        # PASS: at most 20 % held, at most 60 % hinted-unresolved
```

Spot-check a PASS (10 `unresolved` answers of sites with an article). The agent reads Wikipedia from the cache
(`handoff.py wiki-text --label <site id>`); a quote copied from it is checked against the **live** article at import
and must match it character for character.

**5.2 The rest**: the same with `--run $W5 --handoff $H-r0 ... -r1 -r2`, after the pilot's gate. Order of the
answers: the batches are by country; the order D12/D20 name (caves, geology, rock and Palaeolithic sites and the
Americas first) is a property of the writes, not of the answers.

**5.3 The Opus re-check** of every `replace` and a seeded tenth of the `keep`s, for each run once its last round is
imported (the pilot first). Opus 5.5 high, `adversarial`:

```bash
ADV=$W5P/adv                                     # and $W5/adv
$PY $F/adversarial.py select --run $W5P --seed 20261011 [--keep-share 0.1] [--wiki-cache DIR]
$PY $F/adversarial.py export --adv $ADV --handoff $H-pilot-adv-r0
$PY $F/adversarial.py brief  --adv $ADV --handoff $H-pilot-adv-r0 --batch-id B
$PY scripts/remediation/opus_handoff.py validate --dir $H-pilot-adv-r0
$PY $F/adversarial.py import --adv $ADV          # prints states; waiting_for_reask names the undecided cells
$PY $F/adversarial.py export-reask --adv $ADV --handoff $H-pilot-adv-r1    # only if some wait; answer, validate, import
$PY $F/adversarial.py apply  --run $W5P          # DECISIONS.jsonl rewritten, adv/APPLIED.json pins it
```

`select` freezes each cell with the passage of the page its quote was found in (nothing is fetched at export or
import except a counter-quote), so a page that changes later cannot change a question. Once the cells are selected,
`handoff.py import` refuses to write DECISIONS.jsonl again from the handoffs - it would drop the verdicts: delete
`adv/` and select again after any re-import.

What `apply` does: **confirm** - the decision stands, the verdict in its `adversarial` key and so in the journal's
evidence; **reject** - `unresolved` (the researcher's decision kept whole in `adversarial.original`), so the plan clears
a rule's start to `Undated`, restores a MiniMax value from the journal, or leaves anything else listed; **unclear** after
the one re-ask - `held`: nothing written, nothing cleared, listed. `adv/OWNER.jsonl` lists every rejected and held cell
with the researcher's quotes and the checker's reason; the owner list (`owner_list.py`) shows them as `unresolved` and
`held`.

## 6. Write (journalled, steps of at most 100 sites; `FIELDS_WD3.md` 4.5 is the same loop)

Waves are labelled by date and one letter; the pilot first. The lane is `fields-wd5-<wave>-sNNN`, the run stamp
`<wave>_fields-wd5-sNNN`, `confidence one_source`, `test_id WD5/structured-fields`.

```bash
bash scripts/remediation/wd5_wave.sh 2026-10-12a $W5P     # plan.py wave refuses a run whose re-check is not applied
bash scripts/remediation/wd5_wave.sh 2026-10-12b $W5
```

`plan.py wave` also refuses until the three calibrations have a passing verdict (`fields-decided` and `bp-bucket` of
`field_researcher`, `adv-known-truth` of `adversarial`), each sealed against the role's registry entry as it is now: the
calibration runs use the export and the import themselves, so the check stands at the one path into production.
The script stops at the first refusal. By hand, per step N: `plan.py step --stage wd5 --wave W --step N`, then
`apply.py --lane fields-wd5-W-sNNN` with `--emit`, `--verify`, `--rehearse`, `--probe-guards`, `--apply`, `--verify`,
`--rehearse-rollback`, then `plan.py accept --stage wd5 --wave W --step N` (0 deviations). A step with nothing to write
is accepted too. Exit codes of `--apply` as in `FIELDS_WD3.md` 4.5; never apply twice.

## 7. After the last wave

```bash
$PY $F/plan.py handoff --stage wd5 --wave W      # each wave: sites written, source_urls, starts (feeds the D20 scope review)
$PY $F/owner_list.py build --runs $W5P $W5 --final
```

The marker lanes (`raw_data._period_provenance` and `_coord_provenance`), over all sites, after the **last** wd5 wave:

```bash
M=scripts/remediation/mechanical
D=output/remediation/fields
LANES="$D/wd1-pilot/DECISIONS.jsonl $D/wd1/DECISIONS.jsonl $D/wd1-rest-pilot/DECISIONS.jsonl $D/wd1-rest/DECISIONS.jsonl \
       $D/wd3-pilot/DECISIONS.jsonl $D/wd3/DECISIONS.jsonl $D/wd4/DECISIONS.jsonl $D/wd5-pilot/DECISIONS.jsonl $D/wd5/DECISIONS.jsonl"
for KIND in period coord; do
  $PY $M/field_prov.py wave --kind $KIND --wave W --decisions $LANES
  # per step N: field_prov.py step --kind $KIND --wave W --step N; apply.py --lane <period|coord>-prov-W-sNNN
  #   --emit --rehearse --probe-guards --apply --verify --rehearse-rollback; field_prov.py accept --kind $KIND --wave W --step N
done
```

Then, in this order, the work of other packages that depends on this one: the stale-id wave (`qid_repair.py`
wave 5), the site-type merge lane, the card_stats waves and the five dead columns, the static export. A type or period
write voids every earlier card_stats wave's ROLLBACK.sql, so card_stats comes last (map, "Type merge, then card_stats").

## 8. Undo

Every step's `ROLLBACK.sql` restores each old value under `<run stamp>-rollback`, conditioned on the value the step
wrote; rehearsed before the apply, run only deliberately. The rows a wave restored from the journal are ordinary cells of
the same step. `adv/DECISIONS.pre-adversarial.jsonl` is DECISIONS.jsonl as the researchers left it.

## 9. Gates built and tested

`tests/remediation/test_fields_carry.py`, `test_fields_wd5_ops.py`, `test_fields_adversarial.py`,
`test_fields_pools.py`, `test_calibrate_claude.py` (truth pools) and the wd5 module `test_fields_wd5.py`. The mutation
sweep has the family `wd5-adv:` (`python scripts/remediation/mechanical/mutation_sweep.py wd5-adv:`) beside `wd5:`.

## 10. Known limits (decided or open)

- A quote taken from the cache text must match the live article at import; footnote markers and tables are where the
  two can differ. A quote that fails there is asked again like any other.
- **Periods cleared although a source states the value (the reader-gap run, 2026-10-18).** A rule-made start that
  the researcher answered `unresolved` is cleared to `Undated` (D12). Where the answer itself names a dated value
  and says a machine reader is why it gave up ("none states it in a form the check reads", "the checker cannot read
  ..."), the clear was a reader gap, not a finding: the pilot of 2026-10-09 cleared Olympe, Chitinamit and
  Shypyntsi that way (section 11). The earlier note of this section - 92 sites with a BP age in an earlier answer
  that wd5 would never ask - did not hold on the files: the 92 are the sites whose latest pre-wd5 decision is a
  Claude `unresolved` with a BP word in an answer, and every one of them was a rule-made start that wd5 **did**
  ask (checked 2026-10-18 on the files: 57 ended in a `keep` or `replace`, 30 in an `unresolved`, 5 in a `held`), so no BP reason is needed. What is
  left is the empty periods of the paragraph above, built as a run of their own (section 12).
- The priority order of the writes (caves and the Americas first) needs a site cut at `plan.py wave`; it has none: a
  run is one wave. Cut by running the answers in that order and writing wave by wave from the same run only after
  adding the cut.
- Kosovo, Narona, Heracleion, Achladia and Flevum are asked again, not carried (X3); the 73 collective entities are
  listed, not touched (X8).

## 11. The readers of a quote in another language (2026-10-09, pilot spot check)

The Opus spot check of the pilot (written wave `2026-10-09a`) found 5 of its 10 sampled `unresolved` fields where a
source plainly stated the value and only a machine reader failed: a Hungarian sentence (Olympe, "már az i. e. 7.
században is lakták a várost"), a period name the table did not hold (Chitinamit, "dates from the Early Classic"), a
table with the longitude first (Said Qala Tepe, `Long. Lat.` / `K001 Said Qala Tepe 65.5795897 31.5520628 mound`) and
a Russian hemisphere (Gruta do Gentio, `16°15′30″ ю. ш. 46°44′27″ з. д.`). For a rule-made start `unresolved` clears
the value to `Undated` (D12), so a reader gap deletes a roughly right value although a source exists. The readers,
all in `scripts/remediation/fields/`, tests `tests/remediation/test_fields_dates.py`, `test_fields_points.py` and
`tests/pipeline/test_periods.py`, mutation family `wd5l:`:

| reader | reads | refuses |
|---|---|---|
| `pipeline/periods.py` (`PERIODS`, 99 names before, 166 now) | 67 regional period names with the start their comment's source gives: Mesoamerica (Preclassic to Late Postclassic), the Andes (Initial Period to Late Horizon, Chavin, Wari, Moche), eastern North America (Woodland, Mississippian), Egypt (Predynastic, the Intermediate Periods, Middle Kingdom, Ptolemaic), the Aegean (Early/Middle/Late Minoan, Early/Late Helladic, Cycladic), the Near East (Uruk to Neo-Babylonian, Hittite, Seleucid, Parthian, Sasanian), South and East Asia (Mauryan, Kushan, Gupta, Zhou, Jomon, Yayoi, Kofun, Korea's three kingdoms), Roman Republic, Augustan, Flavian. `classic` and `initial period` count only capitalised (`_PROPER`). | `archaic`, `early dynastic`, `late period`, `formative`, `preceramic`, `islamic`, the lithic industries, `dilmun`, `hohokam` (named in `test_periods.REFUSED`: two regions share the word or no start was sourced) |
| `dates.py` (`answers.states_year`, `answers.dated`) | a year, century or millennium **with its era marker**, in some twenty-five languages (`dates.py` lists them); a range or run; a decade ("the 50s BCE", "600-talet f.Kr."); years before the present in German, French, Spanish, Italian, Portuguese, Dutch, Polish, Russian (`answers.bp_dates`) | a number with no marker for a BC value (it is AD: a year in a sentence about a modern event never states an ancient year), a BC marker for an AD value, a bare number below 100, an abbreviated unit without a marker ("the 4th c."), a fraction ("the first half of the 5th century" is not the 1st), Hungarian `i. e.` outside a Hungarian date, `ad`/`ce` in lower case |
| `points.py` (`answers.quote_point_km`) | what `parse_coordinates` read, unchanged; Cyrillic, Czech/Slovak and Hungarian hemisphere abbreviations; `O` by the page's language (a Wikipedia edition or a country domain); a decimal comma before the degree sign; two bare decimals whose axes the quote labels (`Long. Lat.` heading the numbers, `lon 65.58, lat 31.55`, `65.58 (lon), 31.55 (lat)`), with a table row's words around them | a pair with words around it and no labels, one label, a third decimal, a hemisphere letter on a labelled pair, a grid reference, an `O` whose language is unknown |

`states_year` used to look at no era marker at all ("AD 449" stated -449) and to match the year's digits anywhere in
the quote. Measured on the 3,375 period answers of wd1, wd1-rest, wd3, wd4 and the wd5 pilot that carry a year and a
quote: the new reader refuses 14 of the answers the old one accepted (0.4 %), every one of them with a quote that
carries no era marker, is cut off mid-word, or states the other sign ("the 4th c.", "(883-859)", "the 6th millennium
BC" for -5000, "the 1st century AD" for -100); it accepts none the old one refused. The agents' wd5 prompt
(`handoff.FIELD_RULES_WD5`) says quotes may stay in their language and that a BC date needs its marker.

Known limits: a period name is read only in English (a French "Néolithique final" is not a name of the table);
spelled-out ordinals ("cinquième siècle", "fünftes Jahrhundert") are read in English only; the Aurignacian,
Mousterian and Magdalenian are not names (their starts differ by region and dating method: quote the BP date).

Fix round after the review of `ad6d77e` (2026-10-09): a "before" word (przed, před, pred, prije, pre, пре, пред, преди,
до, antes, avant, prima, vor, voor) and an AD abbreviation after it is a BC marker ("450 przed n. e.", "450. godine prije
n. l."); a modern year takes the era of an ancient date after it only across a range word or a dash, never across a
determiner, a comma, a semicolon, a bracket or a full stop ("In 1998 the 3rd century BC walls" states the 3rd century
only); Czech and Slovak `věk` (age) is a century only against a number and an era marker; `woodland` counts only
capitalised, and a sentence-initial `Classic`, `Initial Period` or `Woodland` needs its next word capitalised as well.
Re-measured on the 3,557 period answers of wd1, wd1-rest, wd3, wd4 and the wd5 pilot that carry a year and a quote: the
old reader accepted 3,472, the reviewed commit 3,454, this one 3,454; 18 old accepts refused (0.5 %), none gained, and
this round changes none of the 3,557.

## 12. The reader-gap run (`--reask-cleared`, `--sites`)

`population.py build --stage wd5 --reask-cleared [--sites FILE]` builds a wd5 run that asks `period_start` and nothing
else, with the open reason `reader-gap` (`population.WHY_READER_GAP`; `handoff.OPEN_TEXT` says it to the agent and
`open[period_start]["made"]` carries the previous answer: the run, the first 400 characters of its reasoning and the
value the readers now read). It is a normal wd5 run otherwise: the same rule (`RUN.json` pins `recheck`, and records
`reask`: `detect`, `listed`, the runs it read), export, import, adversarial re-check and wave path, built into a fresh
directory, one run (no `--pilot`, no `--without`). An `unresolved` answer writes nothing (the field is empty already;
the plan lists it); a `replace` fills the empty start and its label; a period another lane wrote since is refused at
the write (`moved-since-classification`).

A site is asked when its period is **empty now** and

* `--reask-cleared`: its latest period decision (WD1, WD3 pilot, WD3, WD4, wd5 pilot, wd5 - `read_answers` over
  `REASK_HISTORY_RUNS`) is a **counted** `unresolved` of a **Claude** agent (not `adversarial`: a source was read and a
  checker refused it; not MiniMax; not `exhausted`), its reasoning **blames a machine reader** (`READER_BLAME`) and
  names a value the readers of today read (`readable_date`: an age BP, a year, century or millennium with its era
  marker not later than 1500 AD, or a period of `pipeline.periods`); the kind is recorded (`bp-age`,
  `dated-statement`, `period-name`);
* `--sites FILE`: it is named in FILE, one JSON object per line `{"site_id": ..., "reason": ...}` (the reason is shown to
  the agent). The build refuses, naming every offender and writing nothing, a listed site that is no curated site of
  the export, is retired, holds a period now, or whose period's newest journal row is another lane's sourced write;
  a detected site in that state is skipped and counted (`reader_gap.skipped`). A site the reader-gap run itself decided
  (`output/remediation/fields/wd5-reask/DECISIONS.jsonl`) is never asked a second time.

`COUNTS.json` has `reader_gap` (`asked` by kind, `skipped` by reason, `detect`, `listed`, `already_decided_sites`) and
`population.why`.

```bash
R=output/remediation/fields/wd5-reask
mkdir -p $R && cp $W5/STORED.jsonl $W5/LINKS.jsonl $W5/POINTS.jsonl $W5/MADE.jsonl $W5/SEEDS.jsonl $R/   # refreshed by
# `population.py --out $R export` instead when the export of $W5 is older than its last wave
$PY $F/population.py --out $R build --root $W5/harvest --stage wd5 --reask-cleared [--sites FILE]
$PY $F/handoff.py copy-hints --run $R --from output/remediation/fields/wd4/ORIGINAL_PERIODS.jsonl
```

The export must be refreshed (`population.py --out $R export`, production read-only, then `harvest.py ... export` as in
section 4) after the last wd5 wave: the build reads the emptiness of each period from it. Measured 2026-10-18 on the
main checkout's files (the export of 2026-10-09 with the waves' `PLAN.jsonl` period writes applied, read-only):
**89 sites** - 60 `dated-statement`, 28 `period-name`, 1 `bp-age`; 5 from the wd5 pilot (Olympe, Chitinamit, Shypyntsi,
Tremeca, Chongbang Fortress) and 84 from the rest run. Some of the 84 give up for a reason the readers still do not
cover (a Spanish period name, a date of the fortification and not of the start): the fresh agent decides, and an
`unresolved` costs nothing but its question. Tests: `tests/remediation/test_fields_wd5_reask.py`; mutation family
`wd5r:`.
