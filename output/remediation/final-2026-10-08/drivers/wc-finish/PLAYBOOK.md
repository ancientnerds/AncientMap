# Lane WC finish: playbook

Scope: the sentence check of the March descriptions that are still unverified (runs `mass-2026-09-27-03`,
`-04`, `-05` and one rest chunk for the texts no run asks), the repair of the web-contradicted description
sentences (`defects-2026-10-02` and the sites found since), the re-check of the texts a MiniMax answer shaped
(D10), and the adversarial second check of the defect claims a check left standing. Decisions: D10, D25, D58,
D81, D135, D145, D147, D151, D153-D156
(`output/remediation/OWNER_DECISIONS_2026-10-08.md`). Runbook of the tools:
`docs/procedures/SENTENCE_CHECK.md` sections 4, 11.3 and 15; where that runbook names a calibration, a seal, a
verdict, a release or an Opus or Sonnet agent, D153 and D154 replace it: every answer is Fable's, no role is
measured. State measured read-only on 2026-11-10 between 19:30 and 20:30 UTC.

Done means, for each run below: answered, imported, built, written to production through the gate with 0
deviations, journal recounted, static export rebuilt and checked, five written sites read live.

## 1. Rules that never bend

1. Work from the main checkout `C:/PythonProjects/AncientMap` (branch `run/2026-10-09-db-final`) in Git Bash.
   Never from a worktree: every run records its handoffs relative to this tree.
2. Every answer is a fresh agent's on `claude-fable-5-2` (D153), recorded with the command its brief prints
   (`opus_handoff.py answer --role ... --model claude-fable-5-2`). One agent answers one batch and no other
   batch of lane WC, ever. No calibration, seal, compare, verdict or release command is run (D154).
3. A round is written once. Never edit, delete or re-create `ROUNDS.jsonl`, `round-N/ANSWERS.jsonl`,
   `verify/round-N/ROUND.json`, `verify/round-N/VERIFIED.jsonl`, `judge/ROUND.json`, a `MANIFEST.jsonl` or a
   prompt file. The only way to take a recorded verification round back is `verify-void` (step A*.1).
4. Never run `build` on a run whose write batches are in the apply root (section 2, `state.py`:
   the line `write batches of <run>` shows anything but `not-in-apply-root`), and never export a judge for a written run: the
   gate checks `plan_sha256` and a failed or missing result of a named plan stops every WC write of every lane.
5. Never name a plan in the gate before its judge (where it has one) passed. Never name a plan whose judge
   failed - unless decision O23 is recorded for that run and the run was built again on it (A1.7a); the gate
   accepts such a plan by the record (`judge/O23.json`), never on its own.
6. Never widen `--allow-stamp` to make an acceptance pass, never remove a `STOPPED.json`, never re-run an
   `--apply` whose outcome is unknown, never write the acceptance log with stderr in it.
7. Web research is at most 3 agents wide over all lanes together (the orchestrator holds the count: ask it
   for slots before a round starts); an `import`, `verify-import` or `judge-import` fetches pages too and
   counts as one of the three while it runs.
8. Stop and report when: free space on C: is below 10 GB (D135); the lane has recorded more than 1,750 Fable
   answers, or one phase more than its stop figure in section 11 (D151); a sampled judge fails (D156: a bad
   spot check stops the block; O23 of 2026-11-12 is that word for mass-03, -04 and -05: go on with A1.7a
   and report the numbers, no further stop); a gate step prints
   anything but its expected last line; or a `git status` of the code paths in P0.2 is not empty.
9. No code is edited. The helpers under `tools/` of this directory are the lane's own and read-only on the
   lane's state.

## 2. Setup and how the state is read

```bash
cd /c/PythonProjects/AncientMap
PY=C:/PythonProjects/AncientMap/.venv/Scripts/python.exe
M=output/remediation; RUNS=$M/wc_runner/runs; H=$M/handoff; L=$M/logs/p4wc
ROOT=$M/logs/_write_apply_p4wc
D=$M/final-2026-10-08/drivers/wc-finish
C="$PY scripts/remediation/wc/cli.py"; OH="$PY scripts/remediation/opus_handoff.py"
G="$PY $M/tools/write_gate4.py --group WC"
V="$PY $M/tools/verify_writes4.py --lane p4wc --allow-stamp wb-teaser-prov-% --allow-stamp wb-card-exact-s%"
mkdir -p $D/briefs $D/logs $D/voided
```

`$V` is expanded unquoted: never put quotes around a stamp pattern inside it.

**Every shell call begins with this block.** An agent's shell keeps neither the working directory nor a
variable of the call before, and the tools resolve a run's handoffs against the working directory. Save the
block once as `output/remediation/final-2026-10-08/drivers/wc-finish/env.sh` (the driver's own file, like its
notes) and begin every call with
`cd /c/PythonProjects/AncientMap && . output/remediation/final-2026-10-08/drivers/wc-finish/env.sh`; set `R`,
`NEXT`, `PLANS`, `S` and `STAMPS` in the same call that uses them.

Helpers (tested 2026-11-10 against the real tree):

| command | prints |
| --- | --- |
| `$PY $D/tools/state.py [RUN ...]` | per run: every check and verification round with its handoff, answers by model, imported or not, voids, built or not, the plan's batch range, the state of its write batches, the judge; last line: accepted steps, a step awaiting acceptance, stopped batches |
| `$PY $D/tools/open.py $H/<handoff>` | each batch that misses answers with its open labels; last line `OPEN n` |
| `$PY $D/tools/prompts_probe.py RUN ...` | whether today's code still builds the frozen prompts of the run's rounds that are not imported; `PROBE_OK` |
| `$PY $D/tools/plans.py [RUN]` | the `--wc-plan ...` list for the gate: every run whose batches are in the apply root, in write order, then RUN |
| `$PY $D/tools/written.py RUN [PREFIX]` | written / cleared / with-a-text counts of the run's applied batches; with PREFIX the two site lists |
| `$PY $D/tools/live_check.py RUN [N] [SEED]` | N random written sites compared with `https://ancientnerds.com/api/sites/<id>`; `LIVE_CHECK n/n match`. A retired site answers 410 and the tool ends in `HTTPError: HTTP Error 410` without that line (3 to 5 sites of each mass run are retired): no finding, run it again with another SEED |

**Before every step run `$PY $D/tools/state.py <run>` and act on what it prints, not on a note.** Every tool
of the lane prints a last line `WC_EXIT=<n>` (`JUDGE_EXIT=<n>` for `judge-import`, `WRITE_EXIT=<n>` for the
gate, `ACCEPT_EXIT=<n>` for the acceptance); a refusal prints `REFUSED: <why>` on stderr and exits 1. Imports
run for minutes up to an hour (they fetch every quoted page, one request per host per second): start them in
the background and wait for the exit line. An acceptance reads production only and takes under a minute
(24 s over the 2,161 rows of 2026-11-10). Append one dated line per finished step to `$D/NOTES.md` (counts as
the tool printed them); on a resume the disk is the authority, the notes are the history.

## 3. State on 2026-11-10

Production: 5,004 curated rows, 4,907 shown, 40 shown without a description. Lane WC's journal
(`remediation_change_log`, stamps `phase4wc:p4wc-NNNN:chunk-0001`): 2,161 rows at 1,063 sites in 56 batches
(`p4wc-4003`, `4200-4224`, `4300-4325`, `4400-4403`), accepted steps 1-13, no step awaiting acceptance, no
stopped batch. The only later writers of cells WC wrote are `wb-teaser-prov-sNNN` (226 rows) and
`wb-card-exact-sNNN` (8 rows): both are named in `$V`.

| run | kind | sites | state on disk | open |
| --- | --- | --- | --- | --- |
| `pilot-2026-09-27c`, `mass-2026-09-27-01`, `-02`, `defects-a1-2026-11-06` | - | 20 / 500 / 500 / 64 | built, written, accepted (the gate's chain today, in this order) | nothing |
| `mass-2026-09-27-05` | plain | 148 | check imported; verify round 1 imported (144 Sonnet); **verify2 imported, all 28 answers MiniMax** | void verify2, 28 answers, build, judge, write |
| `mass-2026-09-27-04` | plain | 500 | check imported; **verify round 1 imported with 109 MiniMax of 480**; verify2 exported (83 questions, 60 MiniMax answers, 23 unanswered), not imported | void, 109 answers, import, new verify2, build, judge, write |
| `mass-2026-09-27-03` | plain | 500 | check imported; **verify round 1 exported, all 492 answers MiniMax, not imported**; no verify2 | void, 492 answers, import, verify2, build, judge, write |
| `defects-2026-10-02` | list (136 Phase-4 texts with claims) | 136 | **check round 1 exported, 45 answered (Sonnet, batches wc-0001..0009), 91 unanswered (wc-0010..0028), not imported** | 91 answers, import, re-ask, verify, verify2, build, write |
| (no run) | plain | 9 | shown, unchecked March texts outside every run: retired when the chunks were read, shown again on 2026-10-24 (D58) | phase A4: a rest chunk, the whole chain |

The checked text still stands in production for 148/148 (mass-05), 493/500 (mass-04), 491/500 (mass-03)
and 136/136 (defects-2026-10-02) sites; the others moved since (rewritten by Phase 4) and are refused per
site by the gate (`written-by-p4` or `moved-since-check`). The frozen prompts of all four open rounds rebuild byte for byte under the code of
2026-11-10, and the description's own state in `raw_data` is still the read's for every site whose text
stands (it moved for 0 of the 1,268). Sites retired since the read (3 in mass-05, 4 in mass-04, 5 in
mass-03) are planned like the others: lane WC has no scope rule.

Defect population (reproduction of `defect-population`, 14 `DESCRIPTION_DEFECTS.jsonl` files, 284 lines, 85
on a text changed since): 157 standing sites + 5 lost = 162. 134 are asked by `defects-2026-10-02`; 22 are
to ask now (19 new from the three shorts pilots; Hatun Uchku and Larisa, Argos with a new claim beside the
one `defects-2026-10-02` carries; Niedertiefenbach with a new claim beside `defects-a1`'s); Leominster
beaker burial is `defect-kept` in `defects-a1` and goes to the adversarial check; the 5 lost sites
(Wamanmarka, Tanqa Tanqa, Lakhan-Jo-Daro, Wain's Hill, Cave of Niaux) have no claim to ask.

D10 list (reproduction of `minimax-sites`): 80 sites touched by a MiniMax answer (63 verify2 answers of
mass-02, 17 texts of the closed WN batch `p4wc-4325`); 71 still hold that text (55 mass-02, 16 WN), 5 are
cleared, 2 retired, 2 rewritten since.

## 4. Preflight P0 (before the first answer and at every resume)

```bash
git rev-parse --abbrev-ref HEAD
#   P0.1  run/2026-10-09-db-final. Another branch: stop and ask the orchestrator.
git status --short scripts/remediation/wc scripts/remediation/phase4 scripts/remediation/roles.py scripts/remediation/opus_handoff.py $M/tools
#   P0.2  prints nothing. Anything listed: the Fable switch (or another change) is still being written.
#         Wait; do not answer, import, build or write.
$PY -c "
import sys, json; sys.path.insert(0,'scripts/remediation')
import roles as R, opus_handoff as OH
from phase4 import model4 as M
from wc import cli as C
from pathlib import Path
for n in ('fact_checker','wc_web_verifier','pilot_judge','wc_adversarial'): print(n, R.role(n).model, R.role(n).effort)
print(M.ai_system_for([OH.SONNET_MODEL, OH.FABLE_MODEL]))
H=Path('output/remediation/handoff'); n=bad=0
for h,role in (('wc-defects-2026-10-02-r1','fact_checker'),('wc-mass-2026-09-27-04-verify','wc_web_verifier')):
    for m in OH.manifest(H/h):
        p=H/h/m['answer_path']
        if not p.is_file(): continue
        d=json.loads(p.read_text(encoding='utf-8'))
        if d['model']==OH.MINIMAX_MODEL: continue
        n+=1
        try: C._require_role(OH.Answer(d['text'],d['answered_by'],d['answered_at'],d['model']), role_name=role, where=m['label'])
        except C.WcRunError as e: bad+=1; print(e)
print('STORED_ANSWERS', n, 'refused', bad)
" 2>/dev/null
#   P0.3  four lines "<role> claude-fable-5-2 high" ("xhigh" for pilot_judge), one line naming
#         "Claude Sonnet and Claude Fable", then "STORED_ANSWERS <n> refused 0" (416 before the first Fable
#         answer: the 45 Sonnet checks of defects-2026-10-02 and the 371 Sonnet verifications of mass-04 that
#         the imports of B.2 and A2.4 read again). An exception, another model or a refused answer: stop.
#         No tool sets a Claude answer aside; a refused stored answer needs the orchestrator's decision
#         before one new answer is bought for that round.
test -f $M/final-2026-10-08/wiki_cache/INDEX.jsonl && echo ok
#   P0.4  ok (a brief is refused without the cache)
df -h /c | tail -1
#   P0.5  at least 10G available; the lane adds about 3 GB (section 11)
$PY $D/tools/state.py | tail -1
#   P0.6  ... step awaiting acceptance False | stopped batches []
$PY $D/tools/prompts_probe.py mass-2026-09-27-05 mass-2026-09-27-04 mass-2026-09-27-03 defects-2026-10-02 2>/dev/null | tail -1
#   P0.7  PROBE_OK. PROBE_FAILED: a question text changed in code; stop, no agent answers a round that
#         cannot be imported.
curl -s -L -o /dev/null -m 40 -A 'AncientMapRemediation/1.0 (research)' -w '%{http_code}\n' 'https://web.archive.org/web/2023/https://en.wikipedia.org/wiki/Stonehenge'
#   P0.8  200: archived pages can be quoted (2026-11-10 20:10 UTC: 200 from this workstation, 429 from the
#         VPS; the imports fetch from the workstation). 429: this network is blocked again (as on
#         2026-11-07): add the archive line to every agent's head (R3) until the probe prints 200.
```

## 5. Procedure R: one round is answered

Inputs: the run, the round's handoff, the brief command (`brief` for a check round, `verify-brief`,
`judge-brief`), the role.

| role | rounds | effort | web |
| --- | --- | --- | --- |
| `fact_checker` | check rounds (`brief`) | high | yes |
| `wc_web_verifier` | `verify`, `verify2` (`verify-brief`) | high | yes |
| `pilot_judge` | sampled judge (`judge-brief`) | xhigh | yes |
| `wc_adversarial` | check rounds of the adversarial run (`brief`) | high | yes |

```bash
# R1 the open batches and their open labels
$PY $D/tools/open.py $H/<handoff>
# R2 the brief of each open batch B (stdout only; the exit line is cut)
$C <brief|verify-brief|judge-brief> --run-dir $RUNS/<run> --handoff $H/<handoff> --batch-id B 2>/dev/null \
  | sed '/^WC_EXIT=/d' > $D/briefs/<handoff>.B.md
test -s $D/briefs/<handoff>.B.md        # empty: the brief was refused, run the command again without 2>/dev/null
```

R3. One new agent per batch, model `claude-fable-5-2`, the role's effort, web tools on, at most 3 web agents
over all lanes. Its whole prompt is this head followed by the brief file:

> Working directory: C:/PythonProjects/AncientMap (run every command from there, in bash, with the paths as
> given). You are an answering agent of lane WC, run `<run>`, batch `<B>`. Follow the brief below exactly; it
> is the lane's own brief for this batch. Wikimedia throttles this network: request pages one at a time, at
> least one second apart. Write only into your batch's scratch directory and record through opus_handoff.py
> as the brief says; touch no other file, run no git command. At the end report how many answers you recorded
> and any problem.
>
> --- BRIEF ---

Only while P0.8 prints 429, add before `--- BRIEF ---` (the archive line): `web.archive.org answers HTTP 429
to every request from this network: never quote a web.archive.org URL, whatever the brief says about archived
copies; quote a live page, and where only an archived page supports a sentence, decide as the brief says for
an unsupported sentence and name the archived URL in the note.` Run P0.8 before each round's agents start.

For a batch that already holds answers (R1 lists fewer open labels than the batch has questions) add before
`--- BRIEF ---`: `Answer only these labels, the others are recorded: <labels>.`

R4. When the agents are back, run R1 again. A batch that still has open labels gets a **new** agent with the
same brief and this line added: `You are a second agent for this batch. Answer only these labels: <labels>.
Record with --answered-by <the brief's name>b and use the scratch directory <the brief's scratch>b/.`
(`c` for a third). An agent's report is never the evidence; `open.py` is.

R5. `$OH validate --dir $H/<handoff>` must print `"ok": true` (exit 0). `missing`: R4. `malformed`, `stale`,
`orphans`: move the named answer file to `$D/voided/` (keep it), then R4 for that label.

## 6. The runs, in order

Run them in this order, one after the other; a run is finished when its last write step is accepted and
procedure P ran. The next free batch number is read from disk in the same shell call as every build (each
`build` step below is: this line, then the build command):

```bash
NEXT=$($PY -c "import glob,json,os;a=[int(json.load(open(f,encoding='utf-8'))['plan']['last'][3:]) for f in glob.glob('$RUNS/*/SUMMARY.json') if (json.load(open(f,encoding='utf-8')).get('plan') or {}).get('last')];b=[int(d[5:]) for d in os.listdir('$ROOT') if d.startswith('p4wc-') and d[5:].isdigit()];print(max(a+b)+1)")
echo $NEXT        # 4404 on 2026-11-10
```

Where a run of this lane stands is read from `state.py <run>`, top to bottom; the first line that applies
names the next step:

| `state.py` shows for the run | next step |
| --- | --- |
| `built: no` and a verification round with `MiniMax` answers and `voids: []` (runs A1-A3 only; the 63 MiniMax answers of the written `mass-2026-09-27-02` are phase D's subject, a built run is never voided) | the void (A*.1) |
| a round with fewer answers than questions | procedure R for that handoff |
| a round fully answered, `imported False` | its import (`import`, `verify-import`) |
| every round imported, `built: no` | `verify-export` for the next round. It refuses with `round 1 left n sentence(s) to re-ask` (a list run whose check import printed `to_reask` > 0: `export-reask` first, B.3), and with `nothing to verify ... build` or `both verification rounds were exported` when no verification is due: then `build` |
| built, no `judge:` line (runs A1-A4 and D only) | `judge-export` |
| `judge:` with fewer answers than questions, or `result not imported` | procedure R, then `judge-import` |
| `judge: ... result [...]` (a list of failures), no `judge/O23.json` | decision O23: A1.7a (`judge-drops`, then `build` again) |
| `judge: ... result [...]` and `judge/O23.json`, `SUMMARY.json` without `"o23"` | `build` again (A1.7a step 3) |
| `judge: ... result passed` (or a run without judge), write batches not all `accepted` | procedure W |
| every write batch `accepted`, no `$D/<run>.REPAIRED_SITES.txt` | procedure P, then the next run |

### A1. `mass-2026-09-27-05` (148 sites)

```bash
R=mass-2026-09-27-05; $PY $D/tools/state.py $R
```

| step | command | produces | done when / refused when |
| --- | --- | --- | --- |
| A1.1 void | `$C verify-void --run-dir $RUNS/$R` (dry run: `answers_to_void 28`, `void_from 2`, `rounds_taken_back []`), then `$C verify-void --run-dir $RUNS/$R --apply --tag 20261110` | the 28 MiniMax answers moved to `$H/wc-$R-verify2.void-20261110/`, `verify/round-2/VERIFIED.jsonl.void`, `verify/VOID-20261110.json` | `"applied": true`; state shows `voids: ['VOID-20261110.json']`, verify2 `0/28 answered`, `imported False`. Skip the step when the void file is already there. Refused: other numbers in the dry run (stop), `was built`, `exists: a void is taken once per round`. |
| A1.2 answers | procedure R, `verify-brief`, handoff `wc-$R-verify2` | 28 answers in 6 batches `verify2-0001..0006` (5,5,5,5,5,3), role `wc_web_verifier` | R5 ok |
| A1.3 import | `$C verify-import --run-dir $RUNS/$R --handoff $H/wc-$R-verify2 > $D/logs/$R.verify2-import.json 2> $D/logs/$R.verify2-import.err` | `verify/round-2/VERIFIED.jsonl` | last line `WC_EXIT=0`. Refused (stderr): an answer without `--role`, a name that checked or verified the site before (re-ask that label under a new name), a malformed answer (move it to `$D/voided/`, R4). |
| A1.4 build | `$C build --run-dir $RUNS/$R --first-batch $NEXT > $D/logs/$R.build.json 2> $D/logs/$R.build.err` | `FINAL.jsonl`, `SUMMARY.json`, `WC4.jsonl` (8 write batches of 20 sites) | `WC_EXIT=0`; state shows `built: sites 148 ...`. Refused: `verification round ... is due`. |
| A1.5 judge export | `$C judge-export --run-dir $RUNS/$R --handoff $H/wc-$R-judge --sample 55 --seed 2026111105 --batch-size 10` | `judge/ROUND.json`, 55 questions in 6 batches `judge-0001..0006` | `WC_EXIT=0`, `"questions": 55` |
| A1.6 judge answers | procedure R, `judge-brief`, handoff `wc-$R-judge` | 55 answers, role `pilot_judge`, xhigh | R5 ok |
| A1.7 judge import | `$C judge-import --run-dir $RUNS/$R --handoff $H/wc-$R-judge > $D/logs/$R.judge-import.json 2> $D/logs/$R.judge-import.err` | `judge/JUDGED.jsonl`, `judge/RESULT.json` | `JUDGE_EXIT=0` and `"passed": true`. `JUDGE_EXIT=1` has two meanings. With `REFUSED:` in the `.err` file no verdict was written (a missing answer, an answer without the role, a malformed one): repair it by R4 or R5 and run `judge-import` again. With `"passed": false` in the `.json` file there is a verdict: if `failures` holds only `n site(s) judged by a checker or verifier of the run`, repair those answers (section 10) and import again; any other failure means the judge failed: record `failures`, `measured` and the judged sites in NOTES and go on with A1.7a (decision O23 of 2026-11-12; before O23 the run was not written and the lane stopped). |
| A1.7a O23 (only after a failed judge) | 1. `$C judge-drops --run-dir $RUNS/$R > $D/logs/$R.judge-drops-dry.json 2> $D/logs/$R.judge-drops-dry.err` (dry run, writes nothing); 2. `$C judge-drops --run-dir $RUNS/$R --apply > $D/logs/$R.judge-drops.json 2> $D/logs/$R.judge-drops.err`; 3. `NEXT` again, then `$C build --run-dir $RUNS/$R --first-batch $NEXT > $D/logs/$R.build-o23.json 2> $D/logs/$R.build-o23.err` | `judge/O23.json` (once); a new `FINAL.jsonl`, `SUMMARY.json` with `"o23"` (`excluded`, `sentences_dropped`, `cleared_by_drops`), `WC4.jsonl` | each `WC_EXIT=0`; the dry run and the apply print the same `sentences_dropped`, `sites_with_drops` and `excluded`. Write the excluded sites (name and id) and the counts into NOTES: they are the run's list for the final report, with the judge's measured rate. Refused: `a pilot is judged whole`, `the sampled judge passed`, `O23 decides only an independent verdict` (repair, A1.7), `is not the plan the judge judged` (the run was built again after its judge: stop and report), `recorded for this run once` (step 2 ran: go on with step 3). Never run `judge-import` again afterwards (refused). Measured on a copy of mass-05 (2026-11-12, read-only): 32 sentences dropped at 25 sites (28 `judge-wrong`, 4 `judge-unsupported`), 5 sites left out, 2 more texts cleared by the drops; 143 sites planned (116 texts, 27 clears, 287 kept sentences) in 8 batches. |
| A1.8 write | procedure W with `$R` (2 steps: 100 + 43 sites after A1.7a) | journal rows `phase4wc:p4wc-NNNN:chunk-0001`; under O23 every row's evidence names the decision (`evidence.judge`) | section 7; the dry run W2 prints `sampled judge failed, written on decision O23: .../$R (O23.json sha256 ..., 5 incoherent site(s) left out; ...)` |
| A1.9 after | procedure P with `$R` | export, checks, lists | section 8 |

### A2. `mass-2026-09-27-04` (500 sites)

```bash
R=mass-2026-09-27-04; $PY $D/tools/state.py $R
```

| step | command | produces | done when / refused when |
| --- | --- | --- | --- |
| A2.1 void | `$C verify-void --run-dir $RUNS/$R` (dry run: `answers_to_void 169`, `void_from 1`, `rounds_taken_back [2]`), then `--apply --tag 20261110` | 109 MiniMax answers of round 1 moved to `$H/wc-$R-verify.void-20261110/`; `verify/round-1/VERIFIED.jsonl.void`; round 2 taken back whole (`verify/void-20261110/round-2-ROUND.json`, handoff moved to `$H/wc-$R-verify2.void-20261110`) | `"applied": true`; state shows one verify round, `371/480 answered`, `imported False`, `import voided True` |
| A2.2 probe | `$PY $D/tools/prompts_probe.py $R 2>/dev/null` | - | `verify round 1 (verify): 480 prompts, 0 differ`, `PROBE_OK` |
| A2.3 answers | procedure R, `verify-brief`, handoff `wc-$R-verify` | 109 answers in 22 batches `verify-0075..0096` (`verify-0076` has 4 open labels of 5: answer only those), role `wc_web_verifier` | R5 ok (480 of 480) |
| A2.4 import | `$C verify-import --run-dir $RUNS/$R --handoff $H/wc-$R-verify > $D/logs/$R.verify-import.json 2> $D/logs/$R.verify-import.err` | `verify/round-1/VERIFIED.jsonl` over the 371 Sonnet and the 109 Fable answers | `WC_EXIT=0`; read `"to_verify2"` (`grep to_verify2 $D/logs/$R.verify-import.json`) |
| A2.5 verify2 export (only if `to_verify2` > 0) | `$C verify-export --run-dir $RUNS/$R --handoff $H/wc-$R-verify2 --batch-size 10` | `verify/round-2/ROUND.json`, batches `verify2-NNNN` (expect 70-95 questions) | `WC_EXIT=0`. `nothing to verify at verify2`: go to A2.8. |
| A2.6 answers | procedure R, `verify-brief`, handoff `wc-$R-verify2` | role `wc_web_verifier`, new agents | R5 ok |
| A2.7 import | `$C verify-import --run-dir $RUNS/$R --handoff $H/wc-$R-verify2 > $D/logs/$R.verify2-import.json 2> $D/logs/$R.verify2-import.err` | `verify/round-2/VERIFIED.jsonl` | `WC_EXIT=0` |
| A2.8 build | `NEXT` again, then `$C build --run-dir $RUNS/$R --first-batch $NEXT > $D/logs/$R.build.json 2> $D/logs/$R.build.err` | 25 write batches | `WC_EXIT=0` |
| A2.9-11 judge | as A1.5-A1.7 with `--sample 55 --seed 2026111104 --batch-size 10` | 55 answers, 6 batches | `JUDGE_EXIT=0`; a failed judge: A1.7a with this run |
| A2.12 write | procedure W (5 steps of 100 sites) | | expect 7 sites refused (`written-by-p4` or `moved-since-check`) |
| A2.13 after | procedure P | | |

### A3. `mass-2026-09-27-03` (500 sites)

As A2 with `R=mass-2026-09-27-03`: void dry run `answers_to_void 492`, `void_from 1`, `rounds_taken_back []`
(the round was never imported, so no `VERIFIED.jsonl.void`); probe `492 prompts, 0 differ`; **492 answers in
99 batches `verify-0001..0099`** (98 of 5, one of 2); `verify-import --handoff $H/wc-$R-verify`; verify2
export into `$H/wc-$R-verify2` with `--batch-size 10` (expect 65-95 questions); build; judge
`--sample 55 --seed 2026111103 --batch-size 10` (a failed judge: A1.7a); write in 5 steps (expect 9 sites refused, `written-by-p4` or `moved-since-check`);
procedure P.

### A4. `mass-2026-11-rest` (the unverified March texts no run asks; 9 on 2026-11-10)

Start it when A1-A3 are written. The plain population is finished only when a fresh export refuses with
`nothing to ask` (SENTENCE_CHECK.md section 4, step 3). On 2026-11-10 a fresh read still holds 9 shown,
unchecked March texts outside every run: the sites the scope lane showed again on 2026-10-24 (D58; stamp
`2026-10-24_mechanical-scope-unretire`), which were retired when the mass chunks were read - Prambanan
Temple, Preah Palilay, Bhagwan Bharat's Statue, Khushuu Tsaidam Museum, Great Kyz Kala, Buddhist Rock Carving
in Manglawar, Kameishi, Gondrani (Shehr-e-Roghan), Sakafune-ishi Ruins. A site an A batch refused as
`moved-since-check`, and a site block 9 (D20) shows again before this read, joins them by itself.

```bash
R=mass-2026-11-rest
$C read --run-dir $RUNS/$R
$C export --run-dir $RUNS/$R --handoff $H/wc-$R-r1 --limit 500 > $D/logs/$R.export.json 2> $D/logs/$R.export.err
grep -E '"population"|"questions"|WC_EXIT' $D/logs/$R.export.json; grep REFUSED $D/logs/$R.export.err
#   "population": n, "questions": n and WC_EXIT=0: go on.
#   REFUSED: ... nothing to ask - the population is empty (WC_EXIT=1): phase A is done, no run was made.
```

A mass run that was not written (a failed judge) still holds its sites unchecked: name it with `--after
$RUNS/<run>`, or this export asks all of them again; and `--after` every open run of another driver (phase
C). With a population above 50, stop and report before any answer: something else moved (an export is not
taken back: that run directory stays unanswered, a corrected export takes a new run name). Then the plain
chain, each step as in B and A1: `brief` (role `fact_checker`, one batch of up to 10), `import`, the re-ask
once if `to_reask` > 0 (`export-reask --handoff $H/wc-$R-r2`), `verify-export --handoff $H/wc-$R-verify`,
`verify-brief`, `verify-import`, verify2 if `to_verify2` > 0, build (`NEXT`), the judge over every built site
(`judge-export --handoff $H/wc-$R-judge --sample <the build's "sites"> --seed 2026111199`), procedure W (one
step), procedure P.

### B. `defects-2026-10-02` (136 Phase-4 texts, each with its reported claims in the question)

```bash
R=defects-2026-10-02; $PY $D/tools/state.py $R; $PY $D/tools/prompts_probe.py $R 2>/dev/null
```

| step | command | produces | done when / refused when |
| --- | --- | --- | --- |
| B.1 answers | procedure R, `brief`, handoff `wc-$R-r1` | 91 answers in 19 batches `wc-0010..wc-0028` (18 of 5, one of 1), role `fact_checker`; agent names `fable-check-r1-wc-00NN` | R5 ok (136 of 136) |
| B.2 import | `$C import --run-dir $RUNS/$R --handoff $H/wc-$R-r1 > $D/logs/$R.import-r1.json 2> $D/logs/$R.import-r1.err` | `round-1/ANSWERS.jsonl`, `round-1/REASK.json`, `pages/` | `WC_EXIT=0`; read `"to_reask"` and `"sites_to_reask"` |
| B.3 re-ask (only if `to_reask` > 0, once) | `$C export-reask --run-dir $RUNS/$R --handoff $H/wc-$R-r2 --batch-size 10`; procedure R with `brief` and handoff `wc-$R-r2`; `$C import --run-dir $RUNS/$R --handoff $H/wc-$R-r2 > $D/logs/$R.import-r2.json 2> $D/logs/$R.import-r2.err` | round 2; a sentence that fails again is dropped | `WC_EXIT=0` |
| B.4 verify export | `$C verify-export --run-dir $RUNS/$R --handoff $H/wc-$R-verify --batch-size 10` | every site whose check kept a sentence (expect 110-125 questions, 11-13 batches) | `WC_EXIT=0` |
| B.5 answers, import | procedure R with `verify-brief`; `$C verify-import --run-dir $RUNS/$R --handoff $H/wc-$R-verify > $D/logs/$R.verify-import.json 2> $D/logs/$R.verify-import.err` | role `wc_web_verifier` | `WC_EXIT=0`; read `"to_verify2"` |
| B.6 verify2 (only if `to_verify2` > 0) | `$C verify-export --run-dir $RUNS/$R --handoff $H/wc-$R-verify2 --batch-size 10`; procedure R; `$C verify-import --run-dir $RUNS/$R --handoff $H/wc-$R-verify2 > $D/logs/$R.verify2-import.json 2> $D/logs/$R.verify2-import.err` | expect 15-20 questions | `WC_EXIT=0` |
| B.7 build | `NEXT`, then `$C build --run-dir $RUNS/$R --first-batch $NEXT > $D/logs/$R.build.json 2> $D/logs/$R.build.err` | `SUMMARY.json` with `not_planned` (`defect-kept`: the check kept the whole text, nothing is written) and `defects_kept` (claims left standing: phase E's list) | `WC_EXIT=0` |
| B.8 write | procedure W (1-2 steps); no judge: a list chunk is written on its verification | | the dry run's line `planned over a live raw_data another lane moved since the check (...): n site(s)` shows n > 0: expected (118 of the 136 sites carry lane WB's card key since the read) |
| B.9 after | procedure P | | |

### C. `defects-rest-2026-11` (the defect sites no run asks yet; 22 on 2026-11-10)

Start it only when B's last step is accepted: the read must see B's texts.

```bash
R=defects-rest-2026-11
$C read --run-dir $RUNS/$R                                   # the one read-only production SELECT
DEF=$(for f in $M/teaser/runs/*/DESCRIPTION_DEFECTS.jsonl; do [ -s "$f" ] || continue; \
  case "$f" in *wave-a2*|*wave-a3*|*wave-a4*|*d81-a2*|*d81-a3*|*d81-a4*) continue;; esac; printf -- '--defects %s ' "$f"; done)
$C defect-population --run-dir $RUNS/$R $DEF --asked $RUNS/defects-2026-10-02 --asked $RUNS/defects-a1-2026-11-06 \
  --lost $M/final-2026-10-08/reconstructed/wb-cardgap-2026-10-07.DESCRIPTION_DEFECTS.lost.json \
  --out $RUNS/$R/DEFECT_SITES.txt > $D/logs/$R.population.json
wc -l < $RUNS/$R/DEFECT_SITES.txt                              # 0: skip phase C
$C export --run-dir $RUNS/$R --handoff $H/wc-$R-r1 --sites $RUNS/$R/DEFECT_SITES.txt \
  --defects $RUNS/$R/DEFECT_SITES.txt.report.json              # never --after a run of this lane: this plan takes the re-asked sites over
```

The files of card waves a2-a4 are left to the card lane's own D81 runs. Add one `--asked` for every other
`$RUNS/defects-*` directory that holds a `SITES.jsonl` when C starts (a card driver's D81 run). Then exactly as
B.1-B.9 with the handoffs `wc-$R-r1`, `-r2`, `-verify`, `-verify2` (new rounds take 10 sites per batch by
themselves: no `--batch-size`): about 22 check answers in 3 batches, about 19 verify answers in 2, no judge,
one write step.

**Runs of other drivers (for the exports of C, D and E).** Run `$PY $D/tools/state.py` without a run name
first. A run that is not this lane's, holds a `SITES.jsonl` and is not written (`built: no`, or write
batches that are not all `accepted`; the failed pilots `pilot-2026-09-27` and `-27b` do not count) is another
driver's open run - a card wave's `defects-a2-...`, a WN, dispute or enrichment run. Add `--after $RUNS/<that
run>` to the export: a site two unwritten plans ask is written from the plan the gate names later, and the
other plan's answers for it are spent for nothing. Report the ids the export's `POPULATION.json` lists under
`earlier-run`.

### D. `recheck-minimax-2026-11` (D10: the texts a MiniMax answer shaped and that still stand; 71 on 2026-11-10)

Start it when C's last step is accepted.

```bash
R=recheck-minimax-2026-11
$C read --run-dir $RUNS/$R
$C minimax-sites --run-dir $RUNS/$R --from $RUNS/mass-2026-09-27-01 --from $RUNS/mass-2026-09-27-02 \
  --closed $M/final-2026-10-08/reconstructed/p4wc-4325.closed.json \
  --out $RUNS/$R/MINIMAX_SITES.txt > $D/logs/$R.minimax-sites.json     # "sites": 71, others_counts by reason
$C export --run-dir $RUNS/$R --handoff $H/wc-$R-r1 --sites $RUNS/$R/MINIMAX_SITES.txt    # plus --after for another driver's open run (phase C)
```

Then as B.1-B.7 (check by `fact_checker`, re-ask once, `verify`, `verify2`, build), then a sampled judge as
A1.5-A1.7 with `--sample 20 --seed 2026111110` (handoff `wc-$R-judge`; if the build planned fewer than 20
sites, the sample is that number), then procedure W (one step) and P. Every asked site is planned, also one
whose sentences all stay: its check record and its citation markers are the new check's, so its text's sha256
moves (section 9, the card hand-off).

### E. `defects-adv-2026-11` (the adversarial second check of the claims a check left standing)

Start it when B, C and D are written. The sources are the built defect runs.

```bash
R=defects-adv-2026-11
$C read --run-dir $RUNS/$R                                   # a fresh read: the written texts are in it
$C defect-kept-sites --run-dir $RUNS/$R --from $RUNS/defects-2026-10-02 --from $RUNS/defects-a1-2026-11-06 \
  --from $RUNS/defects-rest-2026-11 --out $RUNS/$R/KEPT.txt > $D/logs/$R.kept.json   # leave a --from out if that run was skipped
wc -l < $RUNS/$R/KEPT.txt                                      # 0: no claim stands, phase E is done
$C export --run-dir $RUNS/$R --handoff $H/wc-$R-r1 --sites $RUNS/$R/KEPT.txt \
  --defects $RUNS/$R/KEPT.txt.report.json --adversarial        # no --pilot; --after only for another driver's open run (phase C)
```

A `--from` run must be built, and written where it planned a batch (`state.py`: `built: sites ...` and every
write batch `accepted`). Add one `--from` for every repair run of a card wave (`$RUNS/defects-a2-...`, `-a3-`, `-a4-`)
that is in that state when E starts: its `defects_kept` are this check's too. A wave repaired later gets a
run of its own by these commands (`defects-adv-<wave>`).

Then B.1-B.7 with the role `wc_adversarial` for the check rounds (the brief prints it; the verification
stays `wc_web_verifier`'s), no judge, procedure W if `SUMMARY.json` plans a batch (`plan.batches` > 0; an
adversary's KEEP of a whole Phase-4 text writes nothing), procedure P, and then the closure, once:

```bash
$C defect-closure --run-dir $RUNS/$R > $D/logs/$R.closure.txt          # writes CLOSURE.json; a second run is refused
sed -n '/^### Adversarial second check/,$p' $D/logs/$R.closure.txt | sed '/^WC_EXIT=/d' >> $M/AUDIT_LOG.md
```

`RESOLVED` lines are drops that were written; `REFUTED` lines close the defect line on the adversary's quotes.
`AUDIT_LOG.md` is a tracked file: it is committed with the block's records by the orchestrator, never pushed
by the driver. The block report names how two parked cases ended: Leominster beaker burial (`eebdcbf3`, in the
database "Aymestrey Burial", `defect-kept` in `defects-a1`) and the martyrdom year of La basilique
Sainte-Crispine at Tebessa (`9e2b99df`, 304 or 305, a site of `defects-2026-10-02`: settled by B's drop or by
this check).

## 7. Procedure W: the write of one built run

Lane `p4wc`; journal stamps `phase4wc:p4wc-NNNN:chunk-0001`; test ids `WC/description`, `WC/raw_data`,
`WC/description-clear`, `WC/raw_data-clear`; apply root `$ROOT`; acceptance records
`$ROOT/ACCEPTED/step-NNNN.json`. Steps 1-13 are accepted; the next step is 14. One step is at most 100 sites
(5 write batches of 20). Lane WC has no `emit` and no `probe-guards` command: the dry run plans and renders,
the guards run inside the transaction, the read-back and the rollback rehearsal are part of `--apply`.

W0. Preconditions, once per run before W1, all read-only but the backup:

```bash
$PY $D/tools/state.py | tail -1          # step awaiting acceptance False | stopped batches []
$PY $D/tools/state.py | grep "write batches of" | grep -E "rendered|APPLIED-not-accepted"   # must print nothing: no driver is mid-write in group WC (on a resume inside W the run itself is listed: go on at the step state.py shows)
ssh ancientnerds 'tail -2 /var/www/ancientnerds/backups/$(date +%F)_remediation/DRILL_REPORT.txt'
#   single quotes: the date is the VPS's own (CET), as the script's stamp is. It must end
#   "VERDICT: dump is restorable and matches production row-for-row."; on a missing file or another last
#   line run the backup with its drill, once per VPS day:
ssh ancientnerds "cd /var/www/ancientnerds/scripts/remediation && DO_DRILL=1 ./00_backup_and_drill.sh"
#   (a few minutes; exit 0 and the VERDICT line above, else stop: no write without a proven restore point)
ssh ancientnerds "docker exec ancient_nerds_db psql -U ancient_map -d ancient_map -At -F '|' -c \"SELECT run_stamp, count(*) FROM remediation_change_log WHERE applied_at > now() - interval '15 minutes' GROUP BY 1\""
#   must print nothing: no lane is writing right now. Tell the orchestrator that group WC writes until W4 is
#   accepted; no card step (wb-teaser-*) may run over these sites meanwhile.
```

W1. The chain: every run whose batches are in the apply root, in write order, this run last.

```bash
PLANS=$($PY $D/tools/plans.py $R); echo "$PLANS"
#   2026-11-10: pilot-2026-09-27c, mass-2026-09-27-01, mass-2026-09-27-02, defects-a1-2026-11-06, then $R
```

W2. Dry run (plans and renders, sends only read-only questions):

```bash
$G $PLANS > $D/logs/$R.gate-dry.log 2>&1; tail -3 $D/logs/$R.gate-dry.log
```

Done: last line `WRITE_EXIT=0`; the line before reads `rows planned: N | refused by rule: {...} | ... | open
batches: K | dry run, nothing is sent` with K = the run's batch count (plus the open batches of another
driver's plan that `plans.py` named); a line `pilot passed: .../pilot-2026-09-27c ...`; a line `closed batch
p4wc-4325: written and accepted ...`; a line `lane N: the live API runs <commit>, which contains ...` (the
chain holds lane-WN texts). `refused by rule` may hold `written-by-p4` (11 before this lane; mass-04 adds 7 and
mass-03 adds 9 refused sites under this rule or the next), `moved-since-check` and `asked-again-later` per
site. The line `planned over a live raw_data another lane moved since the check (...): n site(s)` may show
any n: the sites were read weeks ago and other lanes wrote keys of their own since. Refused as a whole (no
`WRITE_EXIT=0`): `holds write batches of a WC plan not named here` (another driver rendered a plan: wait for
it, then W1 again), `git cannot relate the live API's commit` (a deploy this checkout has not fetched: `git
fetch origin`, then the same command again), `the sampled judge ...` (rule 5), `did not pass its
verification`, a site planned by two batches. Report any of the last two. From this dry run on the run's
batches lie in the apply root (`rendered`): every other driver of group WC must name this plan until it is
written, so go on to W3 and W4 without a pause, and never leave a rendered plan behind unreported.

W3. Rehearsal (every open batch's exact write, ending in ROLLBACK):

```bash
$G $PLANS --rehearse > $D/logs/$R.gate-rehearse.log 2>&1; tail -2 $D/logs/$R.gate-rehearse.log
```

Done: `every open batch rehearsed`, `WRITE_EXIT=0`, every batch line `"rehearsed": true, "blocked": []`.

W4. One step, repeated until the gate prints `done: no open batch left to write`. `NN` is the step number:
`ls $ROOT/ACCEPTED | wc -l` plus 1.

```bash
$G $PLANS --apply --step 100 > $D/logs/$R.gate-apply-NN.log 2>&1; tail -2 $D/logs/$R.gate-apply-NN.log
#   STEP COMPLETE: <s> site(s) written in <b> batch(es) ... / WRITE_EXIT=0 ; every batch line:
#   rows_written == rows_planned, read_back and inverse "n/n row(s) hold the planned value, n journal row(s)",
#   "rollback_rows_left": 0
$V --plan $ROOT/LANE_PLAN.jsonl > $L/accept-$R-step-NN.log 2> $L/accept-$R-step-NN.err; tail -2 $L/accept-$R-step-NN.log
#   RESULT: 0 deviation(s) / ACCEPT_EXIT=0     (stdout only in the .log: the gate refuses a log with other lines)
$G --accept $L/accept-$R-step-NN.log > $D/logs/$R.gate-accept-NN.log 2>&1; tail -2 $D/logs/$R.gate-accept-NN.log
#   ACCEPTED step NN: <s> site(s) in <b> batch(es) / WRITE_EXIT=0
```

Journal recount after each accepted step (the two numbers must be the step's `rows` and `sites`):

```bash
S=$ROOT/ACCEPTED/step-00NN.json
$PY -c "import json;s=json.load(open('$S',encoding='utf-8'));print(s['rows'],s['sites'])"
STAMPS=$($PY -c "import json;print(','.join(chr(39)+x+chr(39) for x in json.load(open('$S',encoding='utf-8'))['stamps']))")
ssh ancientnerds "docker exec ancient_nerds_db psql -U ancient_map -d ancient_map -At -F ' ' -c \"SELECT count(*), count(DISTINCT site_id_ref) FROM remediation_change_log WHERE run_stamp IN ($STAMPS)\""
```

W5. When the run's last step is accepted, run the dry run of W2 once more (into `$D/logs/$R.gate-dry-after.log`).
It must show `open batches: 0`; then:

```bash
$V --plan $ROOT/LANE_PLAN.jsonl --complete > $L/complete-$R.log 2> $L/complete-$R.err; tail -2 $L/complete-$R.log   # RESULT: 0 deviation(s)
```

`--complete` counts every planned row of the apply root that is not written as a deviation. If the dry run
still shows open batches and `state.py` gives them to another driver's rendered run, skip `--complete` for
this run and note it: it is run by whoever writes the last open batch. Open batches of this run: W4 is not
finished.

Stops inside W, and what they mean:

- `STOP: the step ... has no acceptance`: a step waits (yours or another driver's). Yours: finish W4. Not yours:
  wait, never accept another driver's step.
- `STOP at p4wc-NNNN: ...` with a `STOPPED.json` in that batch: nothing more is written. A preflight stop
  (a row no longer held its old value: another lane wrote between the gate's read and the transaction) wrote
  nothing. Record the file's content in NOTES, count the stamp's journal rows
  (`SELECT count(*) FROM remediation_change_log WHERE run_stamp = 'phase4wc:p4wc-NNNN:chunk-0001'`), report.
  Do not remove the file.
- `the outcome is UNKNOWN` (psql did not answer): the commit may have landed. Never run `--apply` again; count
  the stamp's journal rows as above and report.
- `RESULT: n deviation(s)` with n > 0: the step is not accepted. `CHANGED LATER ... [<stamp>]` names a later
  writer: if it is a lane whose runbook says it writes only its own `raw_data` key into these sites, add its
  pattern by name to `$V` (`--allow-stamp <prefix>-s%`) and run the acceptance again; anything else: stop and
  report. The undo of a batch is `$PY scripts/remediation/phase4/revert4.py --stamp-like
  'phase4wc:p4wc-NNNN:%' --rehearse`, then `--apply`, then `$G --close-reverted` (SENTENCE_CHECK.md section
  6); it is the orchestrator's decision, not the driver's.

## 8. Procedure P: after the last accepted step of a run

```bash
ssh ancientnerds "docker exec ancient_nerds_api python -m api.services.rebuild_static"; echo "exit=$?"
#   0 = exported; 3 = an export already runs (wait 5 minutes, run it again); 1 = failed (stop, report)
scp scripts/remediation/static_export_check.py ancientnerds:/tmp/static_export_check.py
ssh ancientnerds "docker cp /tmp/static_export_check.py ancient_nerds_api:/tmp/x.py && docker exec ancient_nerds_api python /tmp/x.py"; echo "exit=$?"
#   0 = no differing site; 1 = differences (another lane's write may have landed after the export: run the
#   export again, then the check; still 1: report); 2 = the exported file is unusable (stop, report)
ssh ancientnerds "docker exec ancient_nerds_api python -c 'from pipeline.indexnow import submit_recent; print(submit_recent())'"
#   prints the number of URLs announced; an error is not a stop: Lyra's hourly cycle announces every journal write of its last 2 hours
$PY $D/tools/live_check.py $R 5              # LIVE_CHECK 5/5 match (exit 0); "HTTP Error 410" (a retired site was drawn): again as  live_check.py $R 5 <another seed>
$PY $D/tools/written.py $R $D/$R             # $D/$R.REPAIRED_SITES.txt and $D/$R.CLEARED_SITES.txt
```

Qdrant needs no step: the API's nightly reindex takes the new texts. Then one line in `$D/NOTES.md`: run,
steps, sites written, cleared, rows, answers spent (`state.py` prints the answers by model), the seed of the
judge sample.

## 9. Hand-offs and the closing report

- **Lane WN (D145):** the sites in `$D/<run>.CLEARED_SITES.txt` have no description now; `export --wn` asks
  every shown site without one, so WN must start after this lane's last write. The WN driver's preflight
  reads `$D/NOTES.md`: a run of this lane that stays unwritten for good (a failed judge, on the orchestrator's
  word only) must stand there as one line `ABANDONED <run>: <why>`; without it the WN lane waits for this one.
- **Cards (D81, D147):** `$D/<run>.REPAIRED_SITES.txt` of runs B, C, D and E are the sites whose description
  this lane rewrote. A lane-WB card is tied to the sha256 of the text it was written from, so each of these
  sites that carries one has a stale card from the write on (measured 2026-11-10: 118 of B's 136 sites and 5
  of D's sites carry a card tied to the text now served; of D's 71 sites 3 are in card wave a2 and 1 in a3,
  where a description written before the wave's plan is listed `stale-description` and the site keeps its old
  card). No playbook of this programme starts a card run for these lists: the card driver runs only the
  repair runs of its own waves, and D147 ends new cards after wave A, while D81 asks for a new card after a
  repair. Hand the lists with their counts to the orchestrator as an open item; the decision is not the
  driver's, and no card command is run from this lane.
- **Later card waves (a2-a4):** each wave's `DESCRIPTION_DEFECTS.jsonl` is repaired by that wave's driver with
  B's commands (a run `defects-<wave>-<date>`, exported `--after` every WC run not yet written); its
  `defects_kept` are checked by phase E when the run is written by then, else by an adversarial run like E.
- **Identity lane (D13):** Tichit (`1e5f61dd`, `CLOSEOUT_FOLLOWUPS.jsonl`) carries the description of Dhar
  Tichitt. No defect line names it and a sentence check would keep sourced sentences about the other site:
  it is a re-target case, not this lane's.
- **Report per block (D151):** answers spent against the estimate, sites written, sentences kept and dropped
  (`SUMMARY.json`: `sentences`, `sentences_kept`, `cleared`, `drop_reasons`), sites refused by the gate by
  rule, judge results with their seeds, deviations (must be 0), the size of both hand-off lists.

## 10. What can go wrong

| what | the check that catches it | what the driver does |
| --- | --- | --- |
| A sampled judge fails (`"passed": false`). One kept sentence WRONG with a found quote in 55 sites is enough; the two pilots before the verification stage failed this way, the pilot with it passed. Since D154 this sample is the lane's only measurement of the Fable chain | A*.7, and the gate (`the sampled judge did not pass ... unless decision O23 is recorded`) | Decision O23 (2026-11-12): record the failures and the judged sites in NOTES, then A1.7a - `judge-drops` turns the judge's WRONG and UNSUPPORTED kept sentences into drops and leaves the incoherent sites out, `build` writes the plan the gate accepts by `judge/O23.json`. The unsampled sites can still carry a wrong sentence: the final report gives the judge's measured rate per chunk (`measured` in `RESULT.json`), never "clean". A pilot's failed judge is not O23's (`judge-drops` refuses it). The failed run is no longer `ABANDONED`. |
| `judge-import` ends `JUDGE_EXIT=1` with `REFUSED:` on stderr | the `.err` file; no `judge/RESULT.json` was written | not a verdict: repair the named answer (R4, R5), run `judge-import` again |
| An agent records fewer answers than its batch | `open.py`, `validate` (`missing`) | R4 |
| A verifier or judge name that already answered in the run | the import (`checked or verified this site before`; `judged by a checker or verifier of the run` in `RESULT.json` `failures`) | move the answer to `$D/voided/`, R4 under a new name |
| An answer recorded without `--role`, or under another model | the import (`names no role`, `was given in role ...`, the stamp is not the role's) | move it to `$D/voided/`, R4 |
| A quoted page that answers 403 or 429 at the import; web.archive.org blocking this network again | P0.8 before each round and before each import; check import: the sentence is re-asked once (`to_reask`), then dropped; verify and judge imports only record the failed quote | while P0.8 prints 429: the archive line in every head (R3), and before an import `grep -l web.archive.org $H/<handoff>/*/*/*.answer.json \| wc -l`; above 0, hold that import (a failed fetch is stored for the run and is never fetched again) and probe again; still 429 an hour later: report `blocked: web.archive.org` with the count, the orchestrator decides (on 2026-11-07 the import ran anyway and 5 sentences went through the re-ask) |
| A question text changed in code since the export | `prompts_probe.py`; the import (`the exported prompt is not this question's`) | stop; no answer of that round can be imported until the code is the exporting one again |
| Code changes under the run (the Fable switch, another lane's branch merge) | P0.2, P0.3 at every resume | wait; never import or build over a tree that is being edited |
| Another lane moved a site's text or its description state after the check | the gate, per site: `written-by-p4`, `moved-since-check`, `asked-again-later` | nothing: the site is left out, the batch goes on; count them in the report |
| Another lane writes `raw_data` between the gate's read and the transaction | the preflight: `STOP at p4wc-NNNN`, `STOPPED.json`, nothing written | section 7; W0's two checks exist to prevent it |
| Two drivers of group WC (WN, lane E, a card wave's D81 run) share the apply root | W0 (`rendered`, `APPLIED-not-accepted` of another run), the gate (`not named here`), `STOP: the step ... has no acceptance` | one write at a time: wait; `plans.py` names their plans once they are in the root |
| Two builds take the same batch numbers | `NEXT` is read from disk right before each build; the gate (`batch p4-NNNN twice`) | never build two runs at once; never reuse a `NEXT` |
| The disk fills (C: had 13 GB free at 19:35 UTC, 39 GB at 19:56 UTC and 28 GB at 20:05 UTC on 2026-11-10: it moves by tens of GB while other lanes run; the stop is at 10 GB) | P0.5 before every round and every import | stop and report; nothing of `handoff/` or `wc_runner/` is deleted by the driver |
| A lane-N text in the plan and a live API the local git does not know | the gate (`git cannot relate the live API's commit`) | `git fetch origin`, run the gate command again |
| The acceptance log is refused by `--accept` | `--accept` prints why | the log must be one acceptance run, stdout only, made after the step, used once: run `$V` again into a new file |
| A later lane's stamp on WC's cells | acceptance: `CHANGED LATER` | section 7; never `--allow-stamp %` |
| A backup stamp of your own that is never pruned | - | run `00_backup_and_drill.sh` without a stamp argument (the default `<date>_remediation` is pruned after 7) |

Never, in this lane: hand-edit a run directory or the apply root; answer a question yourself as the driver;
reuse an agent for a second batch; run `import` twice or a check round after `verify-export`; rebuild a
written run; run a calibration command; push; write production by any other path than `write_gate4.py
--group WC`.

## 11. Population and estimate

| block | population | check | re-ask | verify | verify2 | judge | answers | agent batches | write steps |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| A1 mass-05 | 148 sites | done | - | done (Sonnet) | 28 (6) | 55 (6) | 83 | 12 | 2 |
| A2 mass-04 | 500 sites | done | - | 109 (22) | ~85 (9) | 55 (6) | ~250 | 37 | 5 |
| A3 mass-03 | 500 sites | done | - | 492 (99) | ~80 (8) | 55 (6) | ~630 | 113 | 5 |
| A4 mass-rest | 9 sites (more if an A batch refuses a site as moved) | 9 (1) | ~1 (1) | ~8 (1) | ~2 (1) | 9 (1) | ~30 | 5 | 1 |
| B defects-2026-10-02 | 136 sites, 795 sentences | 91 (19) | ~6 (1) | ~118 (12) | ~18 (2) | - | ~235 | 34 | 2 |
| C defects-rest | 22 sites | 22 (3) | ~1 (1) | ~19 (2) | ~3 (1) | - | ~45 | 7 | 1 |
| D recheck-minimax | 71 sites | 71 (8) | ~3 (1) | ~67 (7) | ~10 (1) | 20 (2) | ~170 | 19 | 1 |
| E defects-adv | ~20 sites (6 from `defects-a1` today, the rest from B and C) | ~20 (2) | - | ~18 (2) | ~3 (1) | - | ~40 | 5 | 1 |
| **lane** | 1,157 March texts + 157 standing defect sites (136 in B; 22 in C, of which 2 are B's and 1 is `defects-a1`'s; Leominster in E) + 71 D10 texts | | | | | | **~1,480** | **~232** | **~18** |

Basis: the counts of the open rounds are exact; verify2 follows the measured share of the written runs
(13-19 % of the verified sites); B's verify share follows `defects-a1` (55 of 64 sites kept a sentence, 8 of
55 went to verify2, 6 of 64 sites left a claim standing). Re-asked agents add about 3 %. The owner's figure
for this block is about 1,200-1,400 answers (D145); the recount is about 80 above its upper end, which the
first block report says. The D151 stop, whichever comes first: the lane at 1,750 recorded Fable answers (25 %
above 1,400), a phase at 25 % above its own figure (A 1,240; B 295; C 60; D 215; E 50). The count is the
`claude-fable-5-2` figure in the line `answers by model over the listed runs` of `$PY $D/tools/state.py
mass-2026-09-27-05 mass-2026-09-27-04 mass-2026-09-27-03 mass-2026-11-rest defects-2026-10-02
defects-rest-2026-11 recheck-minimax-2026-11 defects-adv-2026-11`, plus the answer files under `$D/voided/`.
Agent time: a verify batch of 5 sites
about 15 minutes, a batch of 10 about 30, a judge batch of 10 about 45; with all three web slots about 25
hours, longer while other lanes hold slots. Disk: about 3 GB (run page stores about 0.5 MB per verified site
and 3 MB per checked list site, agent page stores about 3 MB per checked site, 23 MB per fresh read).
Expected result of A, from the written runs: 5-10 % of the sites cleared (60-90), about 40 % of the kept
texts under 300 characters; the clears are lane WN's, the thin texts the enrichment's.

## 12. Code that must exist first

| what | files | size | blocks |
| --- | --- | --- | --- |
| The Fable switch committed and at rest: every role on `claude-fable-5-2`, the `claude-fable-5-2` stamp, earlier stamps still valid at import, the Fable disclosure strings. On 2026-11-10 20:15 UTC it was uncommitted work of another agent in the main checkout (P0.2 listed `opus_handoff.py`, `roles.py`, `phase4/model4.py`, `wc/cli.py`, `wc/enrich.py`); P0.3 and P0.7 already passed on it. The live API needs no deploy for it: the site page passes a text's `ai_system` through unread. | `scripts/remediation/roles.py`, `opus_handoff.py`, `phase4/model4.py`, `wc/cli.py`, `wc/enrich.py`, the pinned tests under `tests/remediation/` | S | P0.2, so every answer, import, build and write |
| **Built 2026-11-12 (O16/O23, gap wc-finish#2):** `wc/cli.py judge-drops` records decision O23 for a run whose sampled judge failed (`judge/O23.json`), `build` drops the judge's WRONG and UNSUPPORTED kept sentences and leaves the incoherent sites out, the gate accepts the rebuilt plan by the record. No second judge (O23: written as strictly better than the live text). Runbook: `docs/procedures/SENTENCE_CHECK.md` 15.4a | `scripts/remediation/wc/cli.py`, `phase4/wc4.py`, `phase4/write4.py` (invariant 5), `tools/write_gate4.py`, `tests/remediation/test_wc_roles.py`, `test_phase4_wc_write.py`, `phase3/mutation_sweep.py "o23"` | M | built |

Nothing else is missing in code. Not blocking: `tools/live_check.py` ends in a traceback when it draws a
retired site (410, section 8); skipping such a site would be a two-line change of that helper.

What was exercised for this playbook, read-only: `verify-void` as a dry run on the three mass runs; `brief`,
`verify-brief` and `judge-brief` printed under the Fable registry; the frozen prompts of the four open rounds
rebuilt; the 416 stored Claude answers of the two rounds that are imported again passed the role gate and
their parsers; the gate's chain rebuilt from disk; the acceptance over the chain as it stands (`$V --plan
$ROOT/LANE_PLAN.jsonl` to the screen: 2,161 planned and journal rows, 168 superseded by the two allowed
stamps, `RESULT: 0 deviation(s)`); the populations of `defect-population` and `minimax-sites` recomputed
outside the tools against production; every helper but the write half of `written.py`. Read in source only
and never run on a production run: the gate's dry run under the Fable tree (it renders into the apply root),
`judge-export --sample`, `defect-kept-sites`, `export --adversarial` and `defect-closure` (the adversarial
export ran once on a calibration copy, `wc-adv-1o`). Their first real use is A1.5, A1.8 and phase E: read the
tool's output there before the agents start or the next command runs.
