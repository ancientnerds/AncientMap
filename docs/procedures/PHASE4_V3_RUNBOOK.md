# Phase 4, scope version 3: the runbook (lane WA, 2026-09-26)

The descriptions of the curated sites Phase 4 never saw: every curated, non-retired site that still
carries 2026-03 text (a lane-L-marked description, or a card no Phase-5 write put there) and that no
earlier Phase-4 plan carried. They go through the unchanged Phase-4 pipeline (S0-S7, the selector
pin `a0b422e7...` and the reviewer pin `097c4589...`, lanes W and S; T and R stay closed) and are
written by P4 alone. Contract: `PHASE4_CONTRACTS.md` section 12; evidence: AUDIT_LOG, "Lane WA".

Binding: the owner's decisions of 2026-09-26 (`output/remediation/FINISH_PLAN_2026-09-26.md`,
O1-O11) over the design `output/remediation/REPAIR_TEXTS_2026-09-26.md`:

- **No Phase 5.** Lane WB rewrites every card (O2, O3). Every batch of a v3 plan carries `pass:
  phase4-descriptions-only` (`scope4.DESCRIPTIONS_ONLY_MARK`): P4 writes the description with
  `provenance.card: null`, P5 refuses every site of such a batch (`descriptions-only-plan`), so the
  P5 group of a v3 run is never run, nothing waits for it, and no extractive card is planned.
- **No clearing group C.** The held descriptions go to lane WC (sentence check and trim), the cards
  to lane WB.
- **No acceptance exclusion** (O1). `plan4.py build --exclude FILE` stays a general tool.
- **The mass run's 19 `revision-too-fresh` sites** are planned in version 3 by a follow-up plan
  (`v3d`, section 8) once the last of them is due (2026-09-26T21:40:06Z); the main v3 plan does not
  wait for them.
- **16 agents in parallel** (O11): one Opus agent per batch and stage, many batches at once.

## The numbers (measured 2026-09-26 00:12-01:20 UTC, read-only; journal high-water mark 73911)

| what | value | how |
|---|---|---|
| March descriptions (lane L live) / March cards / union | **3,923 / 3,822 / 4,063** | `plan4.py read-march` (one SELECT); `MARCH4_ROWS.jsonl` `5a2949fb...`, read twice, byte-identical |
| scope version 3 | **4,954 sites**, `SCOPE4.v3.json` `fb775d0e5563d9d441c7b7a33bd6e96016a5ac2f9db9524c566f10aeb84ad0ef` | `plan4.py scope --version 3`; versions 1 and 2 rebuild byte for byte from the same inputs |
| listed sites an earlier plan carries | 825 (mass + D9 721, pilot 4 104) | they stay with those runs (held there) |
| **the v3 plan** | **3,238 sites in 216 batches, p4-2001 .. p4-2216** | a fresh `plan4.py read` (5,004 rows, `55b2ece1...`) through `plan4.py build`, `--after` the mass and D9 plans, pilot 4 as `--pilot`; plan `4276f5d0...` for that read |
| **the v3d plan** (after 21:40:06Z) | **19 sites in 2 batches, p4-2501 .. p4-2502** | `--take-deferred runs/mass-2026-09-25`, simulated at 21:41Z |
| the v3 sites' lanes in the census run (2026-09-24, S0 ids, searches off) | W 2,477, S 246, none 515 (search-stopped 442, revision-too-fresh 49, scope-pending 24) | `runs/census-2026-09-24/*/lanes.jsonl`, `HOLDS4.jsonl` |
| **selector questions expected** | **2,605 - 2,654** (v3d: 10 - 18) | every census-W site and the 128 S sites whose article offers a sentence naming them (S3's own `site_pool` over the census's pinned texts; 118 S sites get no question, `no-source`), up to the 49 held too fresh on 09-24 |
| **review questions expected** | **~1,877 - 1,912** (v3d: 7 - 13) | the mass run's measured 1,003 reviews per 1,392 selector questions (0.72) |
| descriptions expected written | ~1,810 - 1,850 | the mass run's rates: W 70.5 %, S 27 % |
| agent batches | 216 select + <= 216 review; v3d 2 + 2; v3's re-queue a few | every v3 batch holds 9-15 census W/S sites |

The census predates the 2026-09-23 id repairs for its rows (S0 of 2026-09-20), so a few lane-0 sites
may reach W in the fresh run; the 48 h rule defers about 2 % of the fetched articles again (v3's
own re-queue, p4-2217 on, section 9).

## 0. Preconditions and the shell

1. `wip/wa` is merged into `integrate/wave1`, and the worktree that holds the Phase-4 data is
   fast-forwarded to it (it is an ancestor today):

       git -C /c/PythonProjects/AncientMap/.claude/worktrees/p4-pilot merge --ff-only integrate/wave1

   `mass4` hashes `scripts/remediation/phase4/` before every batch of a round: never move that
   worktree while a round runs. Merge the other lanes that change `phase4/` (WC changes
   `write4.py`) before the export if they are ready, else only between rounds.
2. Nobody drives `runs/mass-2026-09-25` live again: every live `mass4` round of a run re-queues
   that run's ready deferred sites, and the mass run's 19 are v3d's (section 8). Code holds this
   too: a plan without a pass (the mass run's) re-queues no site a descriptions-only list names
   (`mass4.descriptions_only_claims`), so from 2026-09-26T21:30:14Z on a live round of the mass run
   is refused before `REQUEUE4.jsonl` is written, and its dry run prints `hand over  N ready
   site(s) ...`.
3. **The link and name pass L5 is applied and accepted before step 2's `plan4.py read`**
   (`HUMAN_ONLY_DECISIONS_2026-09-26.md`, B1-L and B1-N: up to 120 sites whose Wikidata item or
   enwiki title is generic, a container or a namesake), and no link or name lane writes while v3
   runs. S1 fetches the article by the stored `enwiki_title` and checks only that title and stored
   QID agree, so a wrong link gives a sourced description of the wrong subject, and no lane
   revisits the description after L5 corrects the link. Measured offline on 2026-09-26 against the
   plan of section 3 (the fresh read of 00:12 UTC): **43 of the 72 `link_suspect` sites** of
   `bcases/names.jsonl` and 34 of its 46 N7 names are v3 sites - e.g. "The Temple of Artemis"
   (Thasos) on Q43018 (Ephesus), "Ancient Theatre of Megalopolis" on the town's article, "Asklepion,
   Kos" on the generic "Asclepieion". Step 1's pin check stays valid: L5 writes
   `site_external_ids`, `name` and `name_normalized`, none of the March read's columns. **If WA
   must start first**: step 3 takes `--exclude <L5's candidate list>` (the 47 + 72 + Tikal ids,
   one per line; a list plan plans every listed site no `--after` plan carries, so every later
   list plan built before L5 - v3d too - takes the same `--exclude`). The first list plan built
   from a fresh read after L5 has been accepted plans them: v3d without `--exclude` (its summary
   then counts them beside the 19), or, if v3d was built before, a plan of its own like section
   8's without `--take-deferred`, `--after` every plan before it (mass, D9, v3, v3d) and its own
   `--first-batch` past all of them (e.g. 2601).
4. **The E3 rule the plan is built with is the merged tree's.** `plan4.py build` fixes the
   `scope-pending` flag (S1 holds such a site) from `pipeline.normalizers.dates.passes_date_cutoff`
   at build time. Merge WD2 (owner decision O7: Oceania to 1500 AD like the Americas) into
   `integrate/wave1` before step 3 if it is ready. Measured 2026-09-26 with `wip/wd2`'s
   `dates.py` over the same plan: its rule changes **0** of the plan's 20 `scope-pending` flags -
   the v3 sites in Oceania dated after 500 AD are Easter Island's, which already lie inside the
   Americas' longitude window - so the order matters only for a later read. Record in AUDIT_LOG
   the commit whose `dates.py` built the plan.

Every command below runs from the p4-pilot worktree:

    cd /c/PythonProjects/AncientMap/.claude/worktrees/p4-pilot
    export PYTHONIOENCODING=utf-8
    PY=C:/PythonProjects/AncientMap/.venv/Scripts/python.exe
    M=output/remediation; R4=$M/phase4_runner; P4=scripts/remediation/phase4
    OH=scripts/remediation/opus_handoff.py; HF=$P4/handoff4.py
    RUNNAME=v3-2026-09-26                  # the run's name: the date of its export (S1)
    RUN=$R4/runs/$RUNNAME; L=$M/logs/p4_v3; mkdir -p $L
    H=$M/handoff/p4-v3                     # $H-select, $H-translate, $H-review: one per stage
    ROUNDS="--plan $R4/PLAN4.v3.jsonl --run-dir $RUN --log-dir $L --searches-off"
    RUNS="--run $R4/runs/pilot4-2026-09-24 --run $R4/runs/mass-2026-09-25 --run $R4/runs/d9-2026-09-25 --run $RUN"
    ALLOW="--allow-stamp phase4l:%"        # + each later lane that wrote a P4 site (section 10)

Every tool prints its own exit line (`STAGE_EXIT=`, `WRITE_EXIT=`, `ACCEPT_EXIT=`): read that line,
never a wrapper's status (HANDOVER section 7).

## 1. The pin still describes production (read-only)

    mkdir -p /c/tmp/v3check
    $PY $P4/plan4.py read-march --out /c/tmp/v3check/MARCH4_ROWS.jsonl

Gate: the printed `sha256` is `5a2949fb826fabb920ac3b8976afe21fcc8d13cf3e98c7a5197c274b03a6774b`
(the committed `MARCH4_ROWS.jsonl`), `rows 5004`, `STAGE_EXIT=0`. The scope is a pure function of
S0, Phase 3's refusals, the D1 listing and this read, so the same bytes prove the pinned scope still
names production's March population; to see it, `$PY $P4/plan4.py scope --version 3 --march
/c/tmp/v3check/MARCH4_ROWS.jsonl --out /c/tmp/v3check/SCOPE4.v3.json` prints `fb775d0e...` (keep the
file name `MARCH4_ROWS.jsonl`: the input's name is part of the scope's `inputs`). A different digest:
a description, card, provenance or retirement moved since - stop and read the difference; a new
population is a new scope version and a new pin, never an edit of the file.

## 2. The fresh read and the item names

    $PY $P4/plan4.py read  --out $R4/V3_ROWS.jsonl                              # one SELECT, 5,004 rows
    $PY $P4/plan4.py names --rows $R4/V3_ROWS.jsonl --out $R4/V3_ITEM_NAMES.json # Wikidata labels of the shared items

`read` gives the plan's old values: today's `raw_data` with lane L's provenance, so P4 replaces the L
marking inside the same cell and **no L row is reverted** (unlike the D9 run, whose plan named S0's
values). `names` asks Wikidata for the shared items' labels (`build` refuses a shared QID without
them; on 2026-09-26 the 76 shared QIDs of the fresh read were exactly `S0_ITEM_NAMES.json`'s).
`V3_ROWS.jsonl` is production bulk and stays ignored (`.gitignore`, its sha256 goes into AUDIT_LOG);
`V3_ITEM_NAMES.json` is the small public read the plan was built from and is **committed** with the
AUDIT_LOG entry of step 3, as `S0_ITEM_NAMES.json` is, so the plan rebuilds from a kept read.

## 3. The plan

    $PY $P4/plan4.py build --rows $R4/V3_ROWS.jsonl --names $R4/V3_ITEM_NAMES.json \
      --pilot $R4/PILOT4.jsonl --scope-list march-description --scope-list march-card \
      --after $R4/PLAN4.scope.jsonl --after $R4/PLAN4.d9.jsonl \
      --first-batch 2001 --out $R4/PLAN4.v3.jsonl

What it checks: the current scope file at its pin; every listed site is the pilot's, an earlier
plan's, excluded or planned; the block p4-2001 .. lies past every `--after` ordinal (901) and outside
lane L's block (p4-1001 .. p4-1334). Expected summary: `sites 3238`, `batches 216`, `first_batch
p4-2001`, `last_batch p4-2216`, `pass phase4-descriptions-only`, `listed 4063`, `excluded null`,
`taken_over {}`, `lane_l_block [1001, 1334]`, `STAGE_EXIT=0` (a later read may differ by the sites
that moved since; with L5's list as `--exclude`, `excluded` names its count and digest). Record in
AUDIT_LOG, in one commit with `V3_ITEM_NAMES.json`: the plan's `sha256`, the sha256 of
`V3_ROWS.jsonl` and `V3_ITEM_NAMES.json`, the commit whose `dates.py` fixed the flags (0.4), and
whether L5 was applied before the read (0.3).

## 4. The export (all batches, one round)

    $PY $P4/mass4.py $ROUNDS --live --stages prepare,sources,routes,select --handoff-export $H-select > $L/export.out 2>&1

Gates in `export.out`: `defect scope SCOPE4.v3.json v3 fb775d0e5563d9d4: 0 site(s) of the open
batches outside it`, `searches off: every routes stage is told 0 and builds no MiniMax client`,
`STAGE_EXIT=0`. About 25 minutes (the mass run's 106 batches took 11). Afterwards each
`$H-select/p4-2NNN/MANIFEST.jsonl` lists the batch's selector questions (stage `finder`).

## 5. The selector cycle (agents in parallel, imports one round at a time)

**Answering.** Up to 16 Opus agents at once, one per batch of `$H-select`, any batches. Each agent
gets exactly this instruction (the orchestrator substitutes the batch, absolute paths):

    Run `C:/PythonProjects/AncientMap/.venv/Scripts/python.exe <p4-pilot>/scripts/remediation/phase4/handoff4.py brief --run-dir <p4-pilot>/output/remediation/phase4_runner/runs/v3-2026-09-26 --handoff <p4-pilot>/output/remediation/handoff/p4-v3-select --batch-id <B>`
    and follow what it prints to the letter.

`brief` prints the whole instruction: read only the batch's manifest and prompt files, no web (each
prompt holds its evidence), one draft per question in `$H-select-scratch/<B>/<site id>.txt` (its own
folder: no two agents share a file), check it with `handoff4.py check-answer` (the selector's own
parser `select_stage.parse_selection` over the batch's own candidate pool, after proving the batch
still builds the exported prompt), then record it with `opus_handoff.py answer ... --stage finder
--answered-by opus-p4-v3-select-<B>` (write-once, carries the prompt's sha256 and the model). When
an agent reports, the orchestrator starts the next batch in its place. The check matters here:
the selector also names the card sentences, and a malformed CARD line refuses the whole selection
(`selection-refused`: the site is held, its description lost) although v3 writes no card - the
mass run lost 4 sites that way, all 4 of which `check-answer` names (AUDIT_LOG, "Lane WA").

**Importing** - by the orchestrator, one `mass4` round at a time, for a set G of batches whose
answers are complete (6-10 batches is one write step's worth):

    $PY $HF ready --run-dir $RUN --handoff $H-select --batch p4-2001 --batch p4-2002 ...   # "ok": true, else wait
    G=p4-2001,p4-2002,...
    $PY $P4/mass4.py $ROUNDS --live --only $G --stages select --handoff-import $H-select
    $PY $P4/mass4.py $ROUNDS --live --only $G --stages translate --handoff-export $H-translate
    #   lanes T and R are closed: no question and no $H-translate/<batch>; if one appears, stop
    $PY $P4/mass4.py $ROUNDS --live --only $G --stages translate,assemble,verify --handoff-import $H-translate
    $PY $P4/mass4.py $ROUNDS --live --only $G --stages review --handoff-export $H-review

`ready` is `opus_handoff.validate` per batch: every question of the named batches answered in shape,
and nowhere in the directory a stale or malformed answer or an answer file no question asks for.
Name every batch of G, also those without a folder in the directory: such a batch asked no
question (every site of it was held before the stage), `ready` lists it under
`named_without_questions` and does not wait for it, and it is imported with the rest of G - its
import asks nothing (had its export not run at all, its import stops at its first question, no
answer file, and writes nothing). A name that is no batch of `$RUN` is refused (`REFUSED`, exit 2),
so a typo never passes as such a batch.
Every round must print `STAGE_EXIT=0`; a non-zero line stops the run (`mass4`'s `stop_reason`).
`opus_handoff.py validate --dir $H-select` shows the whole directory.

## 6. The review cycle

The same with `$H-review` (stage `reviewer`, agent `opus-p4-v3-review-<B>`, the brief's command with
`--handoff .../p4-v3-review`). `check-answer` runs `review4.parse_review` over the batch's own
assembly and asks one line for every shown sentence and one CARD line when a card is shown: the
card is shown and judged (the pinned reviewer question is unchanged) but never written. Then, per
ready set G:

    $PY $HF ready --run-dir $RUN --handoff $H-review --batch ...
    $PY $P4/mass4.py $ROUNDS --live --only $G --stages review --handoff-import $H-review
    $PY $P4/run4.py holds --run-dir $RUN

A batch of G whose every site was held before S6 has no folder in `$H-review`: `ready` lists it
under `named_without_questions` and `ok` does not wait for it; import it with the others - its
review import asks nothing and writes its `review4.json`.

## 7. The write steps (at most 100 sites, each accepted before the next)

The batches the gate may plan are the done ones (review imported):

    $PY $P4/mass4.py $ROUNDS | grep '^done '          # dry: "done          p4-2001,p4-2003,..."
    B=$($PY $P4/mass4.py $ROUNDS | sed -n 's/^done *//p' | sed 's/,/ --batch /g; s/^/--batch /')
    G4="$PY $M/tools/write_gate4.py --group P4 --run $RUNNAME --open-lanes W,S"
    $G4 $B                       # dry
    $G4 $B --rehearse
    $G4 $B --apply --step 100
    $PY $M/tools/verify_writes4.py --lane p4 --plan $M/logs/_write_apply_p4/LANE_PLAN.jsonl $RUNS $ALLOW > $L/accept-step-NN.log
    $G4 --accept $L/accept-step-NN.log          # only on ACCEPT_EXIT=0 and "RESULT: 0 deviation(s)"

What each gate checks:

- **dry**: `defect scope: SCOPE4.v3.json v3 fb775d0e5563d9d4, 4954 sites ...: n of the run's n
  sites`; `descriptions-only batches (phase4-descriptions-only): k of k - P4 writes their
  descriptions with card: null`; `rows planned`, `refused by rule` (`site-held`, `verify4-holds`,
  ...), `WRITE_EXIT=0`. Nothing is sent but the read-only questions.
- **`--rehearse`**: every open batch's exact write ending in `ROLLBACK`; every row proven still at
  its old value and the stamp journalling nothing; `every open batch rehearsed`, `WRITE_EXIT=0`.
- **`--apply --step 100`**: open batches in plan order while the next still fits into 100 written
  sites; per batch the pinned statements, the read-only preflight (every row still holds the old
  value of the fresh read, the stamp journals nothing), the write through
  `apply_remediation_change()` (one journal row per cell, stamp `phase4:p4-2NNN:chunk-0001`), the
  read-back in both directions, the two sha256 invariants, the inverse proof (`ROLLBACK.sql` run
  as-is, rolled back). `STEP COMPLETE: k site(s) written`, `WRITE_EXIT=0`. A disagreement leaves
  `STOPPED.json` and stops every later run until a person has read it.
- **`verify_writes4 --lane p4`** (read-only): every `phase4:%` journal row is a planned row's with
  the planned values and the last link of a chain ending in the live value (or superseded by an
  allowed later stamp); the not-yet-written rows hold their old value; every written site
  re-verified with V1-V15 against its run's pinned texts and the journal's quotes (card `null`:
  none to verify); the desc_sha256 invariant; T08; `RESULT: 0 deviation(s)`, `ACCEPT_EXIT=0`. It
  names every run that wrote under `phase4:` - pilot 4, mass, D9, v3 (and v3d once it wrote).
- **`--accept`**: one whole run of the acceptance whose lane and stamps cover the step, run after
  the step and never used before - `ACCEPTED step N`.

**Audits** (design MASS RUN GATES): after every 500 written v3 sites, 10 of them drawn and judged by
an independent Opus auditor (not a batch agent of the run) before the next step:

    $PY -c "import glob, json, os; ids = sorted({json.loads(l)['site_id'] for p in glob.glob('$M/logs/_write_apply_p4/p4-2*/PLAN.jsonl') if os.path.exists(os.path.join(os.path.dirname(p), 'APPLIED.json')) for l in open(p, encoding='utf-8')}); print(*ids, sep=chr(10))" > $L/written.txt
    $PY $P4/audit4.py draw  --run-dir $RUN --seed <20260927+k> --count 10 --written $L/written.txt --exclude <earlier samples> > $L/draw-<k>.out
    grep -q '^STAGE_EXIT=0' $L/draw-<k>.out && grep -v '^STAGE_EXIT=' $L/draw-<k>.out > $L/drawn-<k>.txt
    $PY $P4/audit4.py sheet --run-dir $RUN --site-ids $L/drawn-<k>.txt --out $L/AUDIT_<k>_SHEETS.md

The verdict file is the shape `audit4.py hold` reads (per site `site_id`, `name`, every sentence's
`n`, `verdict` `SUPPORTED | UNSUPPORTED | WRONG_SITE` and `note`; the card line is informational -
v3 writes no card). A WRONG_SITE or UNSUPPORTED sentence stops the writes: `audit4.py hold --run-dir
$RUN --site <id> --audit <verdicts.json>`, `revert4.py --stamp-like 'phase4:p4-2NNN:chunk-0001'
--site <id>` (render, `--rehearse`, `--apply`), the gate's dry run over the batch (its re-plan
proof), the acceptance again, and the class re-checked over every written v3 site (contracts
section 10).

## 8. The mass run's 19 deferred sites: the v3d plan (after 2026-09-26T21:40:06Z)

The mass run held 19 sites `revision-too-fresh` in their latest batch (p4-0017 .. p4-0113), due
2026-09-26T21:30:14Z .. 21:40:06Z, and never re-queued one. They were held and never written, so
they are not "new" - the v3 plan leaves them to `PLAN4.scope.jsonl`, which carries them - and they
are taken over by a plan of the same two lists (descriptions only, fresh old values, no L revert):

    RUNNAME_D=v3d-2026-09-27; RUN_D=$R4/runs/$RUNNAME_D; LD=$M/logs/p4_v3d; mkdir -p $LD; HD=$M/handoff/p4-v3d
    ROUNDS_D="--plan $R4/PLAN4.v3d.jsonl --run-dir $RUN_D --log-dir $LD --searches-off"
    $PY $P4/plan4.py read  --out $R4/V3D_ROWS.jsonl
    $PY $P4/plan4.py names --rows $R4/V3D_ROWS.jsonl --out $R4/V3D_ITEM_NAMES.json
    $PY $P4/plan4.py build --rows $R4/V3D_ROWS.jsonl --names $R4/V3D_ITEM_NAMES.json \
      --pilot $R4/PILOT4.jsonl --scope-list march-description --scope-list march-card \
      --after $R4/PLAN4.scope.jsonl --after $R4/PLAN4.d9.jsonl --after $R4/PLAN4.v3.jsonl \
      --take-deferred $R4/runs/mass-2026-09-25 --first-batch 2501 --out $R4/PLAN4.v3d.jsonl

Expected: `sites 19`, `batches 2`, `p4-2501 .. p4-2502`, `taken_over {runs/mass-2026-09-25:
{deferred 19, planned 19}}`, `STAGE_EXIT=0`. Commit `V3D_ITEM_NAMES.json` with the AUDIT_LOG entry
that records the plan's sha256 (as in step 3). What `--take-deferred` checks
(`mass4.ready_to_hand_over`, `plan4._list_summary`): the sites the run held `revision-too-fresh` in
their latest prepared batch; refused while one still waits for its 48 h (it names the time), once the
run re-queued one itself (`REQUEUE4.jsonl`), when a list of the plan does not name one, or when no
`--after` plan carries one (the deferring run's plan must be named, or its other sites would be
planned twice). Block p4-2501: past v3's p4-2216 with room for v3's own re-queue (p4-2217 on). The
mass run cannot take them back: `mass4` refuses its live rounds once one of them is ready (0.2), so
neither a re-queue p4-0116 nor a second assembly of a v3d site can arise.

Then sections 4-7 with `$ROUNDS_D`, `$HD-select`/`$HD-review` (agents `opus-p4-v3d-select-<B>`,
`opus-p4-v3d-review-<B>`), `--run $RUNNAME_D` in the gate, and from the first v3d write on
`RUNS="$RUNS --run $RUN_D"` in every p4 acceptance. `verify_writes4.index_runs` reads such a site
from the run that assembled it (`RunSite.deferred`): the mass run's batch only deferred it.

If the v3 plan is built after 21:40:06Z anyway, `--take-deferred $R4/runs/mass-2026-09-25` may go
into its build directly (one plan of 3,257 sites, 218 batches) and this section falls away.

## 9. After the last step

1. **v3's own re-queue.** Sites v3 held `revision-too-fresh` are due 48 h after the answer that held
   them (`run4.py holds`, reason `revision-too-fresh`). The first live `mass4` round after that
   appends them to `$RUN/REQUEUE4.jsonl` as new batches (p4-2217 on, **with the plan's pass**) and
   prints `re-queue ... re-queued now`; export their questions with `$PY $P4/mass4.py $ROUNDS --live
   --only <the new batches> --stages prepare,sources,routes,select --handoff-export $H-select` and
   run sections 5-7 for them. Sites not due yet wait for a later round (the dry run prints how many
   wait and until when). The same holds for v3d.
2. **Lane L** (read-only): `$PY $M/tools/verify_writes4.py --lane p4l --plan
   $M/logs/_write_apply_p4l/LANE_PLAN.jsonl --allow-stamp '2026-09-25_mechanical-orphan-citations'
   --allow-stamp 'phase4:%' --allow-stamp '2026-09-25_mechanical-dangling-markers' >
   $L/accept-p4l-after-v3.log` - every L row P4 replaced is `superseded by phase4:%`, 0 deviations.
   Never `--complete`: it names a superseded L row `NOT WRITTEN` by design (contracts section 11).
3. **The held sites** go to lane WC (descriptions) and WB (cards): the runs' `HOLDS4.jsonl` (`run4.py
   holds`) with the closed-list reasons. A site is final when its latest batch held it for any
   reason but `revision-too-fresh` (that one comes back through the re-queue), or when it was
   written.
4. `$PY $M/tools/write_gate4.py --group P5 --run $RUNNAME` is never needed; run dry it plans 0 rows
   and refuses every site `descriptions-only-plan`.
5. Record in AUDIT_LOG: the plans' sha256, per step the acceptance's lane line and `output_sha256`,
   the audits, the holds by reason and lane, the question counts from the runs' `LEDGER.jsonl`.

## 10. The lanes after WA

- **Later writers of a P4 site.** Every p4 acceptance is cumulative: it re-reads every row P4 ever
  planned. A lane that writes a cell of a P4-written site afterwards must be named with
  `--allow-stamp`, or its rows are deviations (CHANGED LATER / MOVED, and V12 would see a new
  `raw_data` key): lane L `phase4l:%` (already in `$ALLOW`), lane WB's provenance lane
  `wb-teaser-prov-%` (it adds `_card_provenance` and nulls `_description_provenance.card`), lane
  WC `phase4wc:%`. A superseded row is not re-verified as P4's.
- **WC and WB take only final sites** (9.3): a site of a v3 or v3d batch not yet written, or held
  `revision-too-fresh`, is still WA's - a write of its description or `raw_data` by another lane
  would stop its P4 batch at the preflight (the old value moved).
- **`phase4/` is hashed by `mass4`** (0.1): merging a lane that changes `phase4/` moves the digest;
  do it between rounds.

## Undo

- One site: `audit4.py hold` (so no gate plans it again), then `revert4.py --stamp-like
  'phase4:p4-2NNN:chunk-0001' --site <id>` (render, `--rehearse`, `--apply`); its old values are the
  fresh read's, so the reversal restores the March text **and** lane L's marking in one cell.
- One step before its acceptance: `revert4.py --stamp-like '<each stamp of STEP.json>'`, then
  `write_gate4.py ... --close-reverted`.
- The whole of v3 and v3d (and an L5 follow-up plan, 0.3): `revert4.py --stamp-like
  'phase4:p4-2%'` (matches only these plans' blocks, v3's re-queue included; `phase4wc:` stamps do
  not match), `--rehearse` first, then `--apply`; afterwards `verify_writes4 --lane p4 ...` shows
  every v3 row reverted and `--lane p4l` carries the L rows again. A site whose card WB wrote
  since: WB's lanes are undone first (WB's runbook), because the reverted description would no
  longer be the one its teaser was checked against. The card file is not involved in WA: v3 writes
  no card.
- Nothing is deleted: every reversal is a journalled write of the old value (`-rollback` stamps).

## The handoff directories

All under `/c/PythonProjects/AncientMap/.claude/worktrees/p4-pilot/output/remediation/handoff/`:
`p4-v3-select` (216 batch folders after the export), `p4-v3-review` (one folder per batch with at
least one review question), `p4-v3-translate` (expected never to exist), their agents' drafts in
`p4-v3-select-scratch/<batch>/` and `p4-v3-review-scratch/<batch>/`; for the 19: `p4-v3d-select`,
`p4-v3d-review` and their `-scratch` folders. The mass run's were `p4-mass-select` and
`p4-mass-review` (106 + 106 agents `opus-p4m-select-p4-NNNN` / `opus-p4m-review-p4-NNNN`, one per
batch, answered one at a time on 2026-09-24/25; AUDIT_LOG, the mass-run entry).
