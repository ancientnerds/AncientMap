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
write voids every earlier card_stats wave's ROLLBACK.sql, so card_stats comes last (map, "Type merge, then card_stats"). The tools and their commands: section 13.

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

## 13. Phase 8: the type merge, card_stats and its five dead columns, the owner list (2026-10-24)

The close-out order of the map (`plans/fields.md`, "Type merge, then card_stats (last)"), after the last wd5 wave and
the marker lanes of section 7: (1) the site_type merge, then the P31 table without the aliases (13.1), (2) a
card_stats wave and its `b` read-back, (3) the five dead columns - after the last identity and id-repair lane (13.3),
(4) a second card_stats wave after the description and image lanes, (5) the owner list. A type or period write
voids every earlier card_stats wave's `ROLLBACK.sql`, so nothing of (2)-(4) is undone from its file once a later type
or period write landed (`card_stats.py`'s docstring). Every write is a step of at most 100 sites (D8) with the apply
sequence of section 6; tests and the mutation family `d25-` (`mutation_sweep.py d25-`) cover every guard below.

### 13.1 The site_type merge (D25, `mechanical/site_type_merge.py`)

The map `scripts/remediation/mechanical/site_type_merge.json` (pinned by `MAP_SHA256`) merges 15 canonical aliases into
the curated compound type of **their own category group** (`api/cardgame/constants.py`): Settlement, Town, Urban ->
City/town/settlement; Villa -> Residence/villa/farmhouse; Fortress, Citadel -> Fortress/citadel; Gate ->
Gate/archway/bridge; Church -> Church/cathedral; Necropolis -> Necropolis/tombs complex; Megalithic -> Megalithic
structures; Cave -> Cave Structures; Road -> Road/avenue/trackway; Mine, Quarry -> Mine/quarry; Theater -> Theatre. A
pair across groups, a target that is not a fixed point of `normalize_site_type` or itself an alias is refused when the
map is read. `not_merged` names what was considered and kept (City 92, Village 32, Castle 9 - covered by a compound type
but not in the plan's proposal; Fort, Bridge, Aqueduct, Tomb, Temple; Museum and the natural types are scope
questions). `CANONICAL_TYPES` and the globe colours stay unchanged: only data moves.

**The map is a proposal** (`"decision": null`): `report` reads it, `wave` refuses it until `decision` names `by`, `at`
and `check` (fields.md item 8: Opus high decides, plus an adversarial check) and `MAP_SHA256` moves with the edit.

**The P31 table moves after the data, not before.** `fields/p31_site_types.json` keeps every alias (`TABLE_SHA256`
`38140ab2...`, unchanged) while any curated row holds one: `classify.identity` and `classify_site_type` read a stored
type no listed class names as an identity doubt or a CONFLICT, so a table without the aliases would raise false
questions for the unmerged rows of every classify run before the merge (the review of 2026-10-24 measured it on the
wd3/wd4/wd5 CLASSIFIED rows of the 130 alias sites: 27
site_type statuses CONFIRMED -> CONFLICT, 8 new identity doubts), and a table tied to an undecided map is wrong when the
decision drops a pair. After the last merge wave is accepted, `site_type_merge.py table --write` replaces each alias by
its target in the table - refused while the map is undecided or a curated row (shown or retired) still holds an alias,
read-only from production - and prints the new sha256: commit the table and `classify.TABLE_SHA256` together, before
the next field wave (fields.md item 8: otherwise a later wave proposes the old names again). Today's tests pin both
halves: the pinned table lists every alias of the undecided map, and the merged table lists none.

Measured read-only 2026-10-24 (`report`): **212 curated rows** (209 shown, 3 retired: Fortress 2, Settlement 1) -
Settlement 110, Fortress 20, Cave 14, Villa 12, Town 11, Necropolis 9, Gate 9, Church 7, Megalithic 5, Road 3,
Citadel 3, Quarry 3, Urban 3, Mine 2, Theater 1 - and 0 the plan would refuse. Retired rows are merged too.

**Decided 2026-10-24 (orchestrator decision X14, `MASTER_PLAN.md`; Opus decided, an independent Opus check refuted one
pair):** 16 merges - the 15 above minus Megalithic (the group's generic word, its rows split between Megalithic stones and
Megalithic structures: a per-site question), plus City (92) and Castle (9), which the proposal left in `not_merged`; 308
curated rows. Reasons per alias: `output/remediation/final-2026-10-08/X14_SITE_TYPE_MAP.md`. Page titles change for about
135 sites (City/Town/Urban -> "Settlement", Gate -> "Gate or bridge", Castle -> "Castle or palace", ...).

```bash
M=scripts/remediation/mechanical
$PY $M/site_type_merge.py report                       # read-only: map, counts, refusals
# after the decision is recorded in the map and MAP_SHA256 moved:
$PY $M/site_type_merge.py wave --wave W                # WAVE.json, 3 steps
# per step N: site_type_merge.py step --wave W --step N; apply.py --lane site-type-merge-W-sNNN
#   --emit --verify --rehearse --probe-guards --apply --verify --rehearse-rollback; site_type_merge.py accept --wave W --step N
# after the last accept: the table, then move classify.TABLE_SHA256 to the printed sha256 in the same commit
$PY $M/site_type_merge.py table            # read-only dry run: classes changed, the new sha256
$PY $M/site_type_merge.py table --write    # writes scripts/remediation/fields/p31_site_types.json (LF)
```

### 13.2 card_stats after the card waves (`mechanical/card_stats.py`)

The recompute still runs after lane WB's card writes: `card_description` is neither an input nor one of the twelve
columns, so `basis_pointer` reads past it. Measured 2026-10-24 (a probe wave planned into `C:/tmp`, nothing applied):
basis wave 2026-10-04f, counterfactual **0 of 59,724 cells differ** (5,113 journal rows put back); the wave would write
**7,138 cells over 1,751 cards** (mystery 1,382, rarity_score 1,593, rarity_tier 501, antiquity 763, empires 446,
category_group 17), 29 refused (no description).

New since 2026-10-24: a curated site **the D57 insert lane created after the basis's horizon** is left out of the
proof - its journalled insert (the `unified_sites.id` row from NULL to the site's own id, id above `basis.since`)
explains the addition, and `counterfactual_sites_added_since_basis` counts such sites; its `mystery` share moves the
cards of its pair, which the plan writes. An added site without such a journal row, or with one at or below the
horizon, still refuses the plan, and so does a site the basis names that is gone (the same guard as branch
`closeout/insert-lane`, commit 94c7d65; production held no such insert on 2026-10-24). A new site without a `card_stats` row is listed `no-card-stats-row` (the writer only updates; the
API boot's `backfill_placeholder_stats` fills a zeroed placeholder row, FIELD_CONTRACT 2.3).

```bash
$PY $M/card_stats.py --wave Z --export && $PY $M/card_stats.py --wave Z --write     # Z unused, e.g. 2026-10-26
# apply.py --lane card-stats-Z with the 7-step sequence, then --wave Zb --export --write must print "cells": 0
```

### 13.3 The five dead columns (`mechanical/card_stats_ext.py`)

`wikidata_qid` and `best_wiki_url` (`https://en.wikipedia.org/wiki/<title>`) from `site_external_ids`;
`commons_image` (P18, the first best-rank value), `heritage_designation` (the English labels of every best-rank P1435
in force, `; `-joined; an unlabelled value refuses the cell; a statement with an end time - a P582 qualifier other
than `novalue`, such as a tentative-list entry the inscription superseded - is never read, and an item whose every
best-rank designation ended refuses the cell as `designation-ended`) and `inception_year` from the item in a field harvest. A merged item
(`qid-redirects`) refuses the item cells: the id wave repairs the QID first. The lane only fills NULL cells, guards the
site's two external ids, its period and its point (guard 5) and never touches `civilization` or `source_language`.
The five columns are not cells of the recompute, so the two lanes never void each other's proof.

**`inception_year`** is P571 at year precision or finer, one distinct year, and only when that year passes every
refusal of fields.md trap 9 and the scope rule, in this order: before 1500 (`inception-modern`: the park, museum or
designation); not a (QID, year) `period_wave/structured_refused.json` refused (`inception-refused-by-period-wave`;
`wave --refused`, default the main checkout's copy, pinned by sha256 in WAVE.json); inside the site's E3 window -
500 AD in the Old World, 1500 AD in the Americas and Oceania (`inception-past-scope`: a medieval town charter, castle or
wall on an ancient site; `inception-region-unknown` without a longitude); and inside or before the **band** of the
site's stored period (`period_end or period_start`, its `categorize_period` bucket, because a `period_start` is often
the band's edge: `inception-after-period`; `inception-without-period` without one). The readback counts every card
whose inception breaks the E3 window or the band.

**Order: after the last identity and id-repair lane.** The lane only fills, so a `wikidata_qid` or `best_wiki_url` it
wrote is never corrected when a D13/D14 retarget, the scope window's retargets, the stale-id or external-id wave or a
qid repair moves the site's ids afterwards; the readback counts such cards (`_QID_DRIFT` and the best_wiki_url metric)
and the owner list names them (`card-id-drift`). Run its waves once those lanes are accepted.

Measured read-only 2026-10-24 over the wd5 harvest (labels fetched into `C:/tmp`, nothing written): 4,900 shown
cards, **14,619 cells** - wikidata_qid 4,539, best_wiki_url 4,518, commons_image 3,529, heritage_designation 1,873,
inception_year 160; inception refused: 172 coarser than a year, 63 modern, 7 conflicting, 7 past the E3 window
(Tarragona 1165, Nijmegen 1230, Chesterfield 1204, Neuchatel 1011, Llansteffan Castle 1192, Geghard 1215, the
Fortifications of Chania 1336), 17 after the band of the stored period; 3 unlabelled designations, 1 merged item; 361
sites have no QID and 382 no English article. 49 steps. 9 harvested items carry an ended best-rank P1435 beside one
in force (none carries only ended ones), so the heritage count is unchanged; their cards name only the one in force.

```bash
H=output/remediation/fields/wd5/harvest     # a field harvest; `fetch` adds the items it lacks
$PY $M/card_stats_ext.py fetch --wave W --harvest $H   # production read-only; Wikidata GETs; LABELS.json
#   (refused once the wave's WAVE.json exists: the wave pinned LABELS.json - fetch a new wave instead)
$PY $M/card_stats_ext.py wave  --wave W --harvest $H   # WAVE.json pins every item file, LABELS.json and the refused dates
# per step N: card_stats_ext.py step --wave W --step N; apply.py --lane card-stats-ext-W-sNNN
#   --emit --verify --rehearse --probe-guards --apply --verify --rehearse-rollback; card_stats_ext.py accept --wave W --step N
```

### 13.4 The dead card file

`public/data/card_descriptions.json` was deleted on 2026-10-24 (D25, `CARD_DESCRIPTIONS.md` 5.5): nothing in `api/`,
`pipeline/`, `ancient-nerds-map/src` or the deploy reads it. `scripts/import_card_descriptions.py` no longer copies
into it, and `scripts/merge_rewrites.py` no longer copies into it either (a merge writes only its local
`output/card_descriptions.json`; its sandbox tests check that no run, failed or not, creates the file).

### 13.5 The owner list (`scripts/remediation/owner_list_final.py`)

One list of everything that stays empty, unsourced or open: the field runs (each rebuilt with `owner_list.build`, the
**last** run that asked a `(site, field)` decides it), the identity lanes' `OWNER_LIST.jsonl` (retarget, scope
window), and production's own gaps (no description, no card, an old card kept under D5, no picture, a thumbnail
without any gallery row, a hero below 1600x900 that a larger live row could replace (D48) or one without the
credit its licence asks, no type, Undated, a rule-made or
unmarked period, an unsourced or unmarked point, no source URL, no Wikidata item, a pending scope, a card whose
Wikidata id or article link is no longer its site's). A lane row of a retired site or of a value a later write replaced
is set aside and counted; a site type the site_type merge renamed (production holds the merge target of the stored
alias) is no later write, so its question stays open. Every owner-facing artefact under `output/remediation` - a file (`.jsonl`, `.json`, `.md`) or
directory whose name holds `owner` or `human_only`, caches left out - is a source, a field run's own list, the
builder's output, or one of `OUT_OF_SCOPE` with its reason (HUMAN_ONLY.md, HUMAN_ONLY_DECISIONS_2026-09-26.md,
OWNER_DECISIONS_2026-10-08.md: decisions, no open site; `teaser/runs/owner-d47-2026-10-19`: the 6 cleared cards, listed
under `card-empty`); the report names the out-of-scope ones, and anything else is `unregistered` (0 on 2026-10-24).
`hero-small` is D48's population as the census of 2026-10-08 defined it (`state-2026-10-08/workflow_result.json`,
"Served hero size buckets"; `census_digest.md`): a hero - the first `is_hero`, non-excluded row - below 1600x900
whose site holds another non-excluded row of at least 1600x900; each row names the largest such row and how many
there are, because swapping is the owner's call. A small hero without a larger row has nothing to swap: the report
counts it, the list does not carry it (2026-10-24: 809 small, 433 with a larger row - the census's figure - 376
without). **Run it from the main checkout** (the waves name their run by the main checkout's path):

```bash
cd C:/PythonProjects/AncientMap
./.venv/Scripts/python.exe scripts/remediation/owner_list_final.py build           # rerunnable
./.venv/Scripts/python.exe scripts/remediation/owner_list_final.py build --final   # at the very end
```

The image lanes' lists are sources too since 2026-11-11 (`RUN_LISTS`, found by glob because every run writes its own
into its own run directory): each `candidate_search/*/D17_OWNER_LIST.jsonl` (`image_roles/d59.py research-outcomes`;
topic `image-research-none`, the reason of a site without a picture), each `candidate_search/*/D59_OWNER_LIST.jsonl`
(`image-hotlink-uncredited`) and the last `served_image/hero-moves-*/OWNER_LIST.jsonl` (`hero-problem-kept`); a row is
set aside once production shows the picture. Every shown site without any picture has to carry a research row; the
report names the ones without (`image_none_unresearched`) -
`docs/procedures/WD2_SERVED_IMAGE_AND_SCOPE.md` section 3.8.7.

It writes `output/remediation/final-2026-10-08/OWNER_LIST_FINAL.{jsonl,md}`. `--final` refuses while a source is
missing, a list is unregistered, an open field row is `pending` or a site without a picture carries no research row. A dry run of 2026-10-24 (before the identity lanes,
the marker lanes and the card waves) listed 18,044 rows over all 4,900 shown sites: image-none 952,
image-thumbnail-only 140, hero-small 433, hero-credit-missing 50, description-empty 28, card-empty 169, card-old-kept 4,672, Undated 619, site-type-empty 86, source-url-empty 47,
wikidata-id-none 361, scope-pending 5, both markers absent on 4,900, open field rows 682 (899 superseded by later
writes, 2 of a retired or deleted site; 3 open rows `pending`, so `--final` refuses).

## 14. D70: the dating extractor (lane wd5x, built 2026-11-05/06; gold round 1 measured 2026-11-06)

Owner decision D70 (2026-10-25): before any further model research, a **deterministic** extractor reads a site's start
from what its sources print, measured on a sealed gold set first. D71: written without a model check at >= 95 %
bucket precision, every cell a verbatim quote and its URL, 30 cells shown before the wave. D72: only the 615 undated
shown sites are filled; the dated ones give a conflict list, never written. D73: the rest stays `Undated` and goes to
the owner. The orchestrator's O1 (owner AFK, 2026-11-05): **only the start is written**, the earliest anchored start of
the highest tier present; the source range with all its quotes stays in the journal evidence; a start that would move
the site out of the D58 window (or make it a label borderline case) is listed (`OWNER_SCOPE.jsonl`), not written. O2:
the 105 adversarially rejected cells among the 615 enter like any other. O3: while the owner is away, the 30 shown cells
are checked by three independent adversarial agents (Claude stamps only, D6) and the wave goes with at most one wrong.
The design is `output/remediation/final-2026-10-08/D70_EXTRACTOR_DESIGN.md`.

### 14.1 The pieces

| piece | what |
|---|---|
| `fields/dating.py` | the extractor: readers, tiers, decision, the run's files, `verify`, `show`, `shown` |
| `fields/dating_gold.py` | the gold: `build` (pool, draw, seal), `freeze`, `measure` (once), `verdict`, `conflicts` (D72) |
| `fields/dates.py` | `located()` / `reading_text()`: each statement with its character span (`statements()` unchanged) |
| `fields/harvest.py` | `fetch-dating`: `wikitext/<lang>/<revid>.json` (50 revisions a request), `wikis/<lang>/<QID>.json` (one extract a request), `ITEM_LABELS.json` (P2348/P793 items); `cited_page_refs` + `page_text` (tier 4) |
| `fields/rule.py` | `EXTRACT = Rule("extract", "wd5x", 1, 1, FORBIDDEN_FAMILIES, clearable=False, fill_only=True)`; `MACHINE_RULES` (no agent, no brief; `handoff.py` export and import refuse such a run) |
| `fields/population.py` | `build --stage wd5x --sites UNDATED.jsonl`: each listed site asked `period_start` alone (`extract_fields`); a dated, retired or sourced listed site is refused (`check_listed`) |
| `fields/plan.py` | `wave` of an extract run: `_require_gold` and `_require_owner_shown` instead of wd5's calibration and adversarial gates |
| `mechanical/lane.py` | stage `wd5x`: lanes `fields-wd5x-<wave>-sNNN`, test id `WD5X/dating-extractor`, confidence `one_source`, wd5's cells (the rollback restores `Undated`) |
| `wd5_wave.sh W RUN [STAGE]` | the stage argument (`wd5` by default, `wd5x`); a run of another stage is refused |

### 14.2 The tiers and the readers

1. enwiki infobox (`Infobox ancient site`/`archaeological site`: built, founded, established, epochs, periods,
   cultures; `Infobox settlement`: established_date; `Infobox historic site`, `military structure`: built), read from
   the wikitext at the cached revision; the quote is the field as the wikitext prints it, the URL the `&action=raw`
   permalink;
2. enwiki prose: the lead and the sections `READ_SECTIONS` names (History, Archaeology, Description, Dating and their
   equivalents in the readable languages); never Tourism, Geography, References;
3. the item's other Wikipedias in `harvest.READ_LANGS` (the languages `dates.py` reads; the cache's own language is not
   fetched twice), the quote in its language, the URL the `oldid` permalink;
4. the non-Wikipedia pages the field runs' answers cited (`PAGES.jsonl` and `pages/`, status 200), never a forbidden
   family (`rule.FORBIDDEN_FAMILIES`), never Wikipedia, Wikidata or Commons; HTML as visible text, PDF via pdftotext;
5. Wikidata P571/P580/P1249 (precision millennium or finer; P571 vetoed when a P31 class is a park, museum, reserve or
   the like), P2348 through `pipeline.periods`, P793 with P585 when the event is a construction or founding;
6. Pleiades through P1584 only: the description's prose (anchored: it is about the place), then `minDate` with
   `timePeriodsKeys` (attestation: never written alone, `CONFIG["solo"]["pleiades"] = False`).

A prose sentence yields a start only when (`sentence_candidates`): it holds no hedge (`HEDGES`: abstained, not
lowered); it is **anchored** (names the site - a Wikidata label or alias in any language, the article title, the stored
name - or carries a deictic in a paragraph that named it) and no other capitalised proper name stands before the
anchor (the sub-site trap; not read in German, which capitalises every noun); the statement carries an era marker, is a
century or millennium, or is an unmarked three- or four-digit year right after a date preposition; no unit follows it
(`UNITS`: "263 m", "1,200 ewes", "100 stadia"); and the cue that governs it - the nearest of its own clause - is a
**start cue** (built, founded, settled, dates to, ... in the readable languages), not an event cue (excavated,
destroyed, refounded, mentioned, ruled, ...). Two statements joined by a range word or a dash are one start (its low
end). A period word needs no cue but is vetoed after a prefix or a negation ("pre-Inca", "not Roman"), inside a
compound ("Roman Catholic"), inside the site's own name ("Inca Uyo"), before a find ("Roman coins"), and when it is too
broad to bucket (`BROAD_PERIODS`: prehistoric, Middle Ages, classical antiquity, ...). Starts after 1500 AD are dropped.
The sentence splitter does not stop after `_NO_STOP` abbreviations ("(r. 486-465 BC).", "pr. Kr.", "c.") or after a
one- or two-digit ordinal ("5. Jahrhundert"), but does after an era marker ("300 B.C. The city").

### 14.3 The decision (`decide`)

Abstain (`REST.jsonl`, D73, with the reason): a collective entity (P31 village, reserve, region, park, ... with no
ancient-site class; or `--collectives FILE`, the X8 list); no source; no candidate; only hedged sentences; two starts in
two buckets in one sentence of a tier at or above the deciding one; a decision resting on a period word alone while
`CONFIG["solo"]["period"]` is off, or on Pleiades' `minDate` alone. Otherwise the start is the earliest candidate of the
highest tier; `single` when every candidate lies in one bucket, `range` when not (both ends quoted in the evidence;
only the start is written, O1); `scope-hold` when `passes_date_cutoff` fails or `label_borderline` holds for it (O1).
`CONFIG` (tiers, solo switches, the 1500 AD cap) is code: its sha256 is pinned with the modules.

The DECISIONS.jsonl row has the shape of a DERIVED row with real quotes (design section 8): `decision` `replace`
(value the start) or `unresolved`, `via: extracted`, `answered_by: extractor:dating@<stamp>`, `model: null`, every
candidate a quote (`source` the permalink, `quote` verbatim, `outcome` `unverified` until `verify`, `detail` tier,
reader, cue), and `extract` (`kind`, `lo`, `hi`, `tier`, `reason`, the notes of what was seen and not taken).

### 14.4 The gold (D71)

Pool: shown dated sites whose live start equals the latest Claude keep/replace decision of the field runs with a found
quote (`GOLD_RUNS`); never a rule row, a MiniMax answer, a model-less WD1 row or an adversarial `unclear`/`reject`.
Hard stratum: first `unresolved`, later dated (reader-gap re-asks, D68/D69 owner-accepts), measured apart, never gated.
Draw: 400 gold and a disjoint DEV of 300, seeded, allocated over (region, article size) in the shape of the undated
sites; era band and type group are reported in SEAL.json. The extractor is developed on DEV only. `freeze` pins the code
(`dating.code_hashes`: `dating.py`, `dates.py`, `answers.py`, `pipeline/periods.py`, `CONFIG`); `measure` refuses other
code and runs once (a gold's own cited pages are not read as tier 4 for its site); `verdict` passes at precision
>= 0.95 with >= 200 gold and >= 100 emitted, and every deciding tier and the period-word-only decisions judged on their
own (>= 20 cells, >= 0.95). A tier that fails is switched off in `CONFIG`, which is a new freeze and a **new round**
(`build` again: the failed round's gold and hard become DEV). A passing verdict is the gate only for exactly its code.

### 14.4a Gold round 1 and DEV round 1 (2026-11-06)

- **The census** (`dating_gold.py build --census`, default `model_census/ANSWERS_TRUE_MODEL.jsonl` through
  `carry.read_census`): WD1's rows name no model; every settled WD1 answer is in the census (all Claude), so they
  enter the pool. Pool 3,219 (was 791 without it), hard 824 (WD3 `unresolved` later dated by WD5: 765; wd5-pilot 31;
  wd5-reask 28). Round 1 (seed 20261106): 400 gold, 300 DEV, and the hard stratum halved (`split_hard`): 412 sealed
  beside the gold (`HARD.jsonl`), 412 DEV (`dev-hard`).
- **DEV round 1** (DEV only; `gold/round-01/DEV_TUNING_RESULTS.jsonl`): period words in English only; a sentence or
  infobox field naming periods in two buckets is no start (`several-periods`); a period word governed by an event cue
  (peak, invasion, ...) is none; a period word inside a given name ("known as the Inca Gallows") is none; "the city of
  Rhodes" is no deictic; a start cue in a clause about another named place is not the site's (`cue_owner`; the builder
  after "by" is exempt); "about 100 images" is a count; a round year on a bucket edge ("c. 3000 BC") decides no bucket
  (`bucket-edge`); a cached page that is a period's article is skipped; more hedges and event cues.
  `CONFIG` v2: **tiers 1 and 2 only** (tiers 3-6 decided 11/15, 20/28, 6/9, 1/3 on DEV; a disabled tier is not read)
  and **`write_ranges: False`** (ranges 24/40 on DEV; a range goes to REST.jsonl as `sources-disagree`).
  The withheld decisions (ranges, solo kinds) are reported per kind in MEASURE.json (`withheld`), never gated.
- DEV with the shipped switches: dev 82/104 (0.789), dev-hard 164/181 (0.906) - below 0.95 before the seal.

- **Gold round 1, measured once (2026-11-06, stamp `23397a6a1f72`, commit 292c2b8): FAIL.** Bucket precision
  102/145 = **0.7034** (Wilson 95 % 0.625-0.772), coverage 0.3625. Tier 1 29/31 (0.936), tier 2 73/114 (0.640);
  explicit dates 53/58 (year 30/34, century 21/22, bp 1/1, millennium 1/1), period word alone 44/81 (0.543).
  Hard half: 158/182 (0.868). Withheld ranges would have scored 20/37. A re-seal (round 2) is not drawn: with period
  words off the explicit dates emit about 58 of 400 gold, below `MIN_EMITTED` 100, so it cannot pass by
  construction. Nothing is written (D71). The 615 (`wd5x/report-615/`, a measurement without RUN.json): 83 cells
  (13.5 %), 5 scope holds, 527 abstentions; 83 of the 615 are refused by `population.check_listed` (period written by
  another lane's sourced write) and the fresh harvest has 2 P31 classes the classify table lacks (Q184368, Q79007),
  so a wd5x write population cannot be built as it stands. D72: 433 of the 4,294 dated sites read in another bucket
  (`wd5x/CONFLICTS.jsonl`, never written).

### 14.5 The run

```bash
PY=./.venv/Scripts/python.exe; F=scripts/remediation/fields; X=output/remediation/fields/wd5x
# 1. population and harvest (production read-only), then the extractor's sources (serial, pace >= 1 s)
$PY $F/population.py --out $X export
$PY $F/harvest.py --root $X/harvest export && $PY $F/harvest.py --root $X/harvest fetch
$PY $F/harvest.py --root $X/harvest fetch-dating --sites $X/UNDATED.jsonl          # and GOLD/DEV/HARD.jsonl
$PY $F/population.py --out $X build --root $X/harvest --stage wd5x --sites $X/UNDATED.jsonl
# 2. the gold: build, develop on DEV, freeze, measure once, judge
$PY $F/dating_gold.py build --stored $X/STORED.jsonl --harvest $X/harvest --undated $X/UNDATED.jsonl --seed S
$PY $F/dating_gold.py freeze && $PY $F/dating_gold.py measure --harvest $X/harvest && $PY $F/dating_gold.py verdict
$PY $F/dating_gold.py conflicts --stored $X/STORED.jsonl --harvest $X/harvest --out $X/CONFLICTS.jsonl   # D72
# 3. the run, the quote check, the shown cells (O3)
$PY $F/dating.py run --run $X --harvest $X/harvest [--collectives X8.jsonl]
$PY $F/dating.py verify --run $X            # serial, >= 1 s apart; VERIFIED.json
$PY $F/dating.py show --run $X --n 30 --seed S
$PY $F/dating.py shown --run $X --checks CHECKS.jsonl --by "owner AFK, autonomous mandate 2026-11-05"
# 4. the wave (gate: a passing verdict of the current code, VERIFIED.json, OWNER_SHOWN.json), then as section 7
bash scripts/remediation/wd5_wave.sh W $X wd5x
```

`UNDATED.jsonl` is `{"site_id", "reason"}` per line. `harvest.py fetch` in a fresh root refreshes the entities (its
cache is empty), so the Wikidata permalinks name the revision read. Known limits: other-language **period words** are
not read (the vocabulary is English); German prose has no subject veto; a tier-4 page has no sections and anchors by
name only; the scope hold uses the stored point and country. Tests: `tests/remediation/test_fields_dating.py`,
`tests/remediation/test_fields_dating_gold.py`; mutation family `wd5x:` (`mutation_sweep.py wd5x:`, 16 cases, all
fired 2026-11-06).

## 15. D99: the undated sites, dated by a Claude researcher (pilot built 2026-11-06)

Owner decision D99 (2026-11-06) replaces the failed extractor of section 14 with agents: a Sonnet
`field_researcher` proposes a quoted start per undated site, the calibrated `adversarial` role checks
it; D101 (regional period starts, a stated year beats a period word) is in force; O1 (start only) and
the D58 window stay. **Pilot of 50 first; nothing is written until the owner has seen it.** The lane
is a wd5 run, not a new system:

| piece | what |
|---|---|
| `population.py build --stage wd5 --sites FILE --d99` | a reader-gap-shaped run whose listed sites are asked under the reason `d99-undated` (`WHY_D99`); no detection, no `already-reasked` skip; RUN.json `reask.why` records it |
| `handoff.D99_OPEN_TEXT` | the question's "Open because": the start of the site itself, not discovery/excavation/mention/neighbour/sub-site/modern town/upper bound, and the six mistakes the three wd5x spot checkers found |
| `handoff.brief` of a D99 run | the re-check's "the cached article is never your confirmation" gives way to `D99_EVIDENCE` (the start is empty; read `d99.py sources` first) |
| `fields/d99.py draw` | the seeded, stratified pilot (10 each: earlier adversarial conflicts, Peru, England, Greece/Türkiye, others) |
| `fields/d99.py sources --label ID` | what is on disk for a site: the Wikipedia cache, the other-language articles and Wikidata claims of the wd5x harvest, Pleiades (P1584), the pages earlier field runs cited (now also a rejected cell's original quotes) |
| `p31_site_types.json` | cirque (Q184368) and street (Q79007), both `container`, added so the wd5x harvest classifies (775 classes) |

```bash
F=scripts/remediation/fields; X=output/remediation/fields/wd5x; P=output/remediation/fields/wd5r/pilot
$PY $F/d99.py draw --undated $X/UNDATED_ASKABLE.jsonl --seed 20261106 --out output/remediation/fields/wd5r/PILOT_SITES.jsonl
cp $X/STORED.jsonl $X/LINKS.jsonl $X/POINTS.jsonl $X/MADE.jsonl $X/SEEDS.jsonl $P/
$PY $F/population.py --out $P build --root $X/harvest --stage wd5 --sites output/remediation/fields/wd5r/PILOT_SITES.jsonl --d99
$PY $F/handoff.py copy-hints --run $P --from output/remediation/fields/wd4/ORIGINAL_PERIODS.jsonl
$PY $F/handoff.py export --run $P --handoff output/remediation/handoff/fields-d99-pilot-r0 --batch-size 10
# answer (5 batches, Sonnet high), validate, import, re-asks, then adversarial.py select/export/import/apply (5.3)
```

Known limits: the 83 undated sites whose period's newest journal row is another lane's sourced write
(`wd5x/UNDATED_REFUSED_SOURCED_WRITE.jsonl`) are refused by `check_listed` and are not in the pilot;
the adversarial calibration `adv-truth-002` stands for the role, but its cells were framed before
D101 (no regional period wording). Tests: `tests/remediation/test_fields_d99.py`.

### 15.1 D112 and D111 (2026-11-06)

**D112** wrote 5 of the pilot's 7 confirmed starts (Brean Down, Mawk'allaqta, Karabel/Belören,
Çimdin Kalesi, Moel y Gest) as wave `2026-11-06a` of `wd5r/pilot`. Port Way and Čertova pec were
taken out first with `adversarial.py owner-reject --run $P --cell <site>.period_start --decision D112
--reason ...`: a confirmed `replace` becomes `held` with `via: owner` (nothing written, nothing
cleared, listed in the wave's HELD.jsonl), the file before is kept as `DECISIONS.pre-owner-<n>.jsonl`,
`adv/OWNER_REJECTED.jsonl` lists the cells and APPLIED.json pins the new file - the mirror of
`owner-accept`.

**D111** tightens the question for every round and cell exported from then on: `period_rule` is
`D111` (`handoff._D111_SENTENCE` after the D101 sentence; `adversarial._D111_CLAUSE` after the D101
clause): a coarse period word gives no year (`pipeline.periods.COARSE`, and a bare Bronze Age where
`SUBPHASE_REQUIRED` divides it), the most precise epoch the source gives is the answer, a weak single
source (a stub citing no publication, a travel/tourism/community/personal/blog page) does not count,
and the start is the site's own beginning (not the territory around it, not a first mention, not a
sentence that only classifies it). A D101 round keeps the text it was asked. The second pilot draws
50 new sites: `d99.py draw ... --exclude wd5r/PILOT_SITES.jsonl --pilot "D111 pilot 2"`.
Tests: `tests/remediation/test_fields_d111.py`, `test_fields_adversarial.py::TestTheOwnersVeto`.
