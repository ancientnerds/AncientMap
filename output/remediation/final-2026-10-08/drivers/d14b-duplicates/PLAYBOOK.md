# PLAYBOOK: D14 part B - duplicates (90 clusters, Tarxien, Dodona, Caparra)

State read on 2026-11-10 (19:00-20:10 UTC; the workstation clock is UTC+1, every time below is UTC).
Decisions: D8 (writes without asking, each journalled, rehearsed, its rollback rehearsed, accepted with 0
deviations; `dup_merge.py` holds a wave to 100 sites under it), D14 (merge: judged survivor, loser retired,
images and links moved), D144 (run part B, about 180 answers), D151 (order, stop
rule), D153 (every role on `claude-fable-5-2`), D154 (no calibration, seal, verdict or release step), D155
(no weekly cap), D156 (no owner gate; a bad spot check or a block more than 25 % above its estimate stops
the block), D135 (stop below 10 GB free on C:).

The lane in one sentence: two model stages decide each cluster (`dup-verdict`, then `dup-recheck`), the
decisions become waves of pairs, and each wave is written by two journalled lanes (`dup-merge-move-<wave>`,
then `dup-merge-retire-<wave>`); a retired loser's URL answers 301 to its survivor (live since part A).

What a driver can finish today and what waits for code: the answering (steps 0 to 8) runs on the tree as it
is. The write (step 9) waits for code in most waves: a wave that moves an image row needs G1 (the `files`
command), Caparra needs G2 before step 2, and the retirement's guard probe needs G3 when the wave's first
loser has no neighbour. G1, G2 and G3 are built on branch `build/track-b` (commit `049f052`, 2026-11-10),
and so is the rule of O14 for a merge beyond 2,000 m (G5, commit `b3ed4ec`):
**every command this playbook marks "available after the merge of build/track-b" exists only once that
branch is merged into the tree the driver runs in** - the gates of step 0 say whether it is. The move's
guard probe can still refuse on G4 (section 5). The driver never builds code; it stops at the gate that
names the gap and reports.

## 0. Frame for every command

Every shell call starts with these lines (the working directory does not carry over between calls):

```bash
cd /c/PythonProjects/AncientMap && export PYTHONIOENCODING=utf-8
PY=./.venv/Scripts/python.exe
RUN=output/remediation/final-2026-10-08/identity
DRV=output/remediation/final-2026-10-08/drivers/d14b-duplicates
H=output/remediation/handoff
```

Fixed names of this lane:

| thing | value |
|---|---|
| run directory (fixed in code, `identity/common.py RUN_SUBDIR`) | `output/remediation/final-2026-10-08/identity` |
| stage state | `$RUN/dup/dup-verdict/` and `$RUN/dup/dup-recheck/` (`ROUNDS.jsonl`, `DECISIONS.jsonl`, `answers/rN.jsonl`, `pages/`) |
| handoff directories | `$H/d14b-dup-verdict-r1` (`-r2`, `-r3`), `$H/d14b-dup-recheck-r1` (`-r2`, `-r3`) |
| agents' scratch (the brief names it) | `<handoff>-scratch/<batch>/<label>.json` |
| decisions | `$RUN/DUP_DECISIONS.jsonl` |
| wave directory | `output/remediation/mechanical_dup_merge/<W>/` (`PAIRS.json`, `move/`, `retire/`) |
| lanes | `dup-merge-move-<W>`, `dup-merge-retire-<W>`, then `card-stats-<C>` |
| run stamps in `remediation_change_log` | `<W>_mechanical-dup-merge-move`, `<W>_mechanical-dup-merge-retire`, `<C>_mechanical-card-stats` |
| journal test ids | `D14/dup-merge-move`, `D14/dup-merge-retire` |
| driver log | `$DRV/NOTES.md` (append one line per iteration: UTC time, step, counts) |

`<W>` is the UTC date on which `dup_merge.py waves` runs (for example `2026-11-11`); a second wave gets
`<W>b`. `2026-11-05` is used (part A). `<C>` is the next free label under
`output/remediation/mechanical_card_stats/` (today the newest is `2026-11-07d`). A wave label is a date
with at most one letter (`2026-11-11`, `2026-11-11b` ... `2026-11-11z`); no other form resolves to a lane.

Roles (read them, do not assume): `$PY -c "import sys; sys.path.insert(0,'scripts/remediation'); import roles as R; print([(r, R.role(r).model, R.role(r).effort, bool(R.owner_standing(r))) for r in ('web_verifier','adversarial','pilot_judge')])"`
must print `claude-fable-5-2` and `True` three times, efforts `high`, `high`, `xhigh` (it did on 2026-11-10
19:52 UTC, from uncommitted edits of the Fable switch).

## 1. Where the lane stands (2026-11-10)

* Part A is written and accepted: run `2026-11-05_mechanical-dup-merge-move`, 52 journal rows (28
  `site_content_links.site_id` over 11 sites, 12 + 12 `unified_site_names` cells over 12 sites), recounted
  today. 16 pairs moved, 5 had nothing to move, Tarxien and Dodona were excluded
  (`mechanical_dup_merge/2026-11-05/EXCLUDED.json`). No image row moved in part A: all 265 loser images
  collide with the survivor's own copy of the same URL.
* Two things of part B have never run on production: a move of `wiki_images` rows, and the lane
  `dup-merge-retire-<wave>` at all (the journal holds no `%_mechanical-dup-merge-retire` row). Their first
  rehearsal and guard probe are the first proof; read every line of them.
* Part B has not started: `$RUN/dup/` does not exist, no round is exported, no handoff directory
  `d14b-*` exists, `$RUN/DUP_DECISIONS.jsonl` holds 90 `unanswered` clusters and 23 `complete`
  retired-loser records (basis: the export of 2026-11-05 22:31 UTC, shown 4,909).
* Production today: 5,004 curated sites, 4,907 shown, 25 retired as `duplicate_of:`. None of the 225
  cluster members is retired and none has a `scope_status` (a loser with one is held by `plan-retire`). The
  two retirements of D138 touch no cluster.
* What the 225 members hold (production, 2026-11-10): 3,374 image rows; 1,333 of them, in 55 of the 90
  clusters, carry a URL no other record of their cluster has, so a merge there moves image rows and their
  files (G1, step 9.3); 92 pairs of rows in 37 clusters share a filename under different URLs
  (`hero.webp`): such a row stays on the loser (measured on 2026-11-10 over the 524 loser/survivor
  combinations the 90 clusters allow, each pair in both directions: 2,968 rows would move, 183 would stay
  for their filename, 167 of them a `hero.webp`); 7 of the 272 folders of the cluster members, the retired
  losers and their survivors hold a file no row names (4 times `hero.webp`), which the plan reads from the
  folder itself; none of their 4,106 image rows lacks its file; 148 members have another shown curated site
  within 2,000 m outside the clusters (the retirement's probe needs one planned loser that has one, G3);
  `site_content_links` holds no row of a non-curated site (gap G4).
* One survivor of part A is a cluster member: **Alba Fucens** (`dup-a3956ca430`), onto which "Area
  Archeologica di Alba Fucens" is retired. If the verdict merges Alba Fucens away, the plans hold both
  pairs (`... is retired onto the loser already`, `the loser is retired for another reason`); they go on
  the held list.
* The three named cases:
  * **Tarxien Temples** `4a5a324f-832f-4dca-b688-d4a006d297c7`: retired onto **Templos de Tarxien**
    `318414bc-098b-4459-95c0-41e1ec49c8a8`. The loser holds 20 images (1 hero), 0 links; the survivor 0
    images, 5 links, 36 name rows (one is the alias "Tarxien Temples"), a card text. The loser's files are in
    `/var/www/ancientnerds/public/data/images/wiki/4a5a324f/` (20 files); the folder `318414bc` does not exist.
  * **Dodona** `5a04d6f3-c82d-4c82-b1e9-3d70bff135ae`: retired onto **Archaeological Site of Dodoni**
    `56f594fc-6819-4d51-98a4-1cf5b4a265a6`. Loser 20 images (1 hero), 5 links (2 collide); survivor 0 images,
    5 links, 20 name rows (one is the alias "Dodona"), a card text. The loser's 20 files are in
    `.../wiki/5a04d6f3/`; the survivor's folder `56f594fc` holds one file that no `wiki_images` row names
    (`Dodona-Greece-April-2008-107.webp`).
  * **Ciudad Romana de Cáparra** `cf49332c-0a05-4ba7-bf4f-48a703ee7a1e`: retired onto **Cáparra**
    `577f2ec4-3dc0-4d10-9425-39f1cb654009`; it holds no image and no link, and its name is the one retired
    duplicate name that is no name of its survivor.
* Path chosen for Tarxien and Dodona, and decided by the orchestrator as O14 (2026-11-10): **no survivor
  swap.** They enter a wave as the already-retired pairs
  they are (no model answer: a retired loser is in no cluster), and their images and links move to the
  present survivor. This departs from `plans/identity.md` 3.1 and O5, which expected a swap; the reasons:
  no lane un-retires a `duplicate_of:` row (`scope_unretire.py` leaves them), the card text, the name rows
  and the live URL sit on the present survivor, and `card_stats` does not move. The English name is lane
  D23's write (Templos de Tarxien is in its triage; Dodoni is not: see section 9).
* The daily backup and restore drill of 2026-11-10 passed (`backups/2026-11-10_remediation/DRILL_REPORT.txt`).

## 2. What a driver must never do in this lane

1. Never run `identity/export.py` or `identity/dup_clusters.py` after step 3 has exported its first round
   and before step 8 has written `PAIRS.json` (one exception: the re-run of `dup_clusters.py` for gap G2,
   exactly as step 2 describes it). Every prompt carries the export's clock and is rebuilt from
   `EXPORT.jsonl`, `DUP_CLUSTERS.jsonl` and the wiki cache at every import: after a new export the import
   of an open round refuses every answer (`stale: the answer names prompt ...`; `opus_handoff.py validate`
   does not see it), and a cluster whose members changed gets a new id, so its decision is orphaned without
   an error and a later export crashes on the old label. The run directory is shared with the lanes D20,
   D13, D23 and D25. The D13 and D23/D25 playbooks wait for this lane's last wave; the D20 playbook runs
   `export.py` whenever no identity round is exported and unimported, which is true between two rounds
   of this lane: the orchestrator must keep D20's export out of this whole window, not only while a round
   is open. If the probe of section 3 shows another export basis than the one noted at step 2:
   * a round of this lane is open: stop and report before another agent answers (its answers will not
     import);
   * no round is open: note it and go on (the next export is built on the new basis, the decisions are
     keyed by cluster id); a `KeyError` that names a site id at an export, a brief or an import means a
     cluster member left the shown sites: stop and report.
2. Never edit a file by hand under `$RUN`, a handoff directory, a `pages/` directory, `PAIRS.json`,
   `PLAN.jsonl`, `APPLY.sql` or `ROLLBACK.sql`. Never write `$RUN/dup/OVERRIDES.json`: a merge beyond
   2,000 m needs none (O14: verdict and re-check decide it like any other merge, G5; on a tree
   without G5 it is held and reported, step 3).
3. Never pass two stage flags to `mechanical/apply.py` in one call: `--verify` and `--probe-guards` return
   before any other flag runs. One flag, one call, in the order of step 9.
4. Never run `--apply` twice for a lane, and never re-plan a lane whose run stamp has journal rows: the
   re-plan is refused, but only after it has overwritten `READ.jsonl`, the read the applied plan rests
   on (`DISK.json`, the folder listing, is written with a plan and stays the applied plan's: G1 as
   built).
   Read the journal (section 3) before every `plan-move` and `plan-retire`.
5. Never apply a move whose plan moves an image row (`images` > 0) before the files are in the survivor's
   folder (gate 9.3). The served path is `/data/images/wiki/<site id, 8 hex>/<filename>`. After the merge
   of build/track-b `apply.py --apply` refuses such a move itself (exit 1, `REFUSED: <n> picture(s) of the
   moved image rows are not in place`); on a tree without that commit nothing but this rule stands in the
   way. Never copy, move or delete a file of the image tree by hand: `dup_merge.py files --copy` is the
   only writer (it never moves and never overwrites).
6. Never start `plan-retire` before the move of the same wave passed `--apply`, `--verify`,
   `--rehearse-rollback` and, when it moved image rows, the served-image read-back of 9.4 (a wave whose
   move plan was refused with `nothing to plan` has no move and goes straight to `plan-retire`); never
   rehearse the move's rollback after the retirement was applied.
7. Never run a `ROLLBACK.sql` on your own. A reversal is the orchestrator's decision; the order is retire,
   then move, and after a Lyra restart the move's name row no longer rolls back cleanly.
8. Never use `waves --exclude` on your own (an exclusion is the orchestrator's decision, handed to you as
   a file of `{"loser": id, "reason": why}` entries), never merge a pair that is not a CONFIRMed MERGE of
   `DUP_DECISIONS.jsonl`, never pick a survivor yourself.
9. Never run more web agents than the orchestrator grants (at most 3 over all lanes together), never give
   one agent two batches, never let an agent record under a model id it does not run as, never run a
   calibration, seal, verdict or release command.
10. Never read production with a join on `CAST(id AS text)` over `unified_sites` (1.76 million rows): filter
    `u.id = '<uuid>'::uuid` and set `statement_timeout`. Never write to production outside `apply.py`.
11. Never edit code and never push. A refusal that names a code gap of section 5 stops that step; log it and
    report.
12. Stop and report when `df -h /c` shows less than 10 GB free (D135; it read 20, 13 and 30 GB within one
    hour on 2026-11-10, so read it before every step).

## 3. Read the state before every step

```bash
$PY - <<'EOF'
import json, pathlib, collections
run = pathlib.Path('output/remediation/final-2026-10-08/identity')
def jl(p):
    return [json.loads(l) for l in p.read_text(encoding='utf-8').splitlines() if l.strip()] if p.exists() else []
counts = json.loads((run / 'COUNTS.json').read_text(encoding='utf-8'))
print('export basis', counts['export']['exported_at'], '| shown', counts['export']['shown'], '| clusters', counts['dup_clusters']['clusters'], '| retired losers listed', counts['dup_clusters']['retired_losers_holding'])
print('clusters built from this export', (run / 'DUP_CLUSTERS.jsonl').stat().st_mtime >= (run / 'EXPORT.jsonl').stat().st_mtime)
for stage in ('dup-verdict', 'dup-recheck'):
    d = run / 'dup' / stage
    for r in jl(d / 'ROUNDS.jsonl'):
        n = sum(len(v) for v in r['batches'].values())
        print(stage, r['name'], '| handoff', r['handoff'], '| batches', len(r['batches']), '| questions', n, '| imported', (d / 'answers' / (r['name'] + '.jsonl')).exists())
    dec = jl(d / 'DECISIONS.jsonl')
    print(stage, 'decisions', dict(collections.Counter(x['status'] for x in dec)) or 'none')
dd = jl(run / 'DUP_DECISIONS.jsonl')
print('DUP_DECISIONS', dict(collections.Counter(x['status'] for x in dd)), '| merges', sum(len(x['merges']) for x in dd), '| part_of', sum(len(x['part_of']) for x in dd), '| wrong_id', sum(len(x['wrong_id']) for x in dd))
waves = pathlib.Path('output/remediation/mechanical_dup_merge')
for w in sorted(p for p in waves.iterdir() if p.is_dir()):
    print('wave', w.name, '| PAIRS', (w / 'PAIRS.json').exists(), '| move plan', (w / 'move' / 'PLAN.jsonl').exists(), '| retire plan', (w / 'retire' / 'PLAN.jsonl').exists())
EOF
```

What it printed on 2026-11-10: `export basis 2026-11-05 22:31:43.774089+00 | shown 4909 | clusters 90 |
retired losers listed 23`, `clusters built from this export True`, `dup-verdict decisions none`,
`dup-recheck decisions none`, `DUP_DECISIONS {'unanswered': 90, 'complete': 23} | merges 23 | part_of 0 |
wrong_id 0`, one wave `2026-11-05` (`PAIRS True`, `move plan True`, `retire plan False`).

Where to resume from what it prints:

| the probe shows | go to |
|---|---|
| export basis `2026-11-05 ...` and no `dup-verdict` round | step 1 |
| export basis of the lane's start day, no `dup-verdict` round, `clusters built from this export False` | step 2, `dup_clusters.py` only |
| export basis of the lane's start day, no `dup-verdict` round, `clusters built from this export True` | step 3 |
| a round with `imported False` | the answering loop of its step (validate, agents, import) |
| newest `dup-verdict` round imported, `held` > 0, fewer than 3 rounds | step 4 |
| `dup-verdict` finished (no `held`, or 3 rounds), no `dup-recheck` round | step 5 |
| newest `dup-recheck` round imported, `held` > 0, fewer than 3 rounds | step 6 |
| both stages finished, `DUP_DECISIONS` still shows `unanswered` 90 | step 7 |
| `DUP_DECISIONS` without `unanswered`, no wave newer than `2026-11-05` | step 7 (lists, spot check), then 8 |
| a wave `<W>` with `PAIRS` and a missing plan | step 9 at the first missing piece |

A wave directory alone does not say what was written: a plan file exists before its apply.

Whether a lane was applied is read from the journal, never from files:

```bash
ssh ancientnerds "docker exec ancient_nerds_db psql -U ancient_map -d ancient_map -At -F ' | ' -c \"SET statement_timeout='15s'\" -c \"SELECT run_stamp, table_name, column_name, count(*), count(DISTINCT site_id_ref) FROM remediation_change_log WHERE run_stamp LIKE '%_mechanical-dup-merge-%' GROUP BY 1,2,3 ORDER BY 1,2,3\""
```

Answers spent (for the D151 stop rule, estimate 180, stop above 225):
`find $H -path '*d14b-dup-*' -name '*.answer.json' | wc -l`. Read it after every export, before the briefs
go out: the answers recorded so far plus the questions the export just printed must stay at or below 225.
If they would not, hand out no brief and report (the exported round waits; nothing is lost).

## 4. Steps

### Step 0 - gates before anything runs

| gate | command | pass |
|---|---|---|
| roles on Fable | the `roles` one-liner of section 0 | three times `claude-fable-5-2`, `True` |
| the import asks owner standing | `grep -c owner_standing scripts/remediation/identity/label_rounds.py` | 1 or more (2 today, uncommitted) |
| tools import | `for t in identity/dup_judge.py identity/dup_clusters.py identity/export.py mechanical/dup_merge.py mechanical/apply.py; do $PY scripts/remediation/$t --help > /dev/null 2>&1; echo "$t $?"; done` | five times `0` |
| wiki cache | `wc -l < output/remediation/final-2026-10-08/wiki_cache/INDEX.jsonl` | 4767 |
| cluster input | `ls output/remediation/bcases/dup_pairs.jsonl` | the file exists |
| no open identity round | `find $RUN -name ROUNDS.jsonl` | prints nothing (true today); else every listed stage's newest round has its `answers/<round>.jsonl` |
| disk | `df -h /c` | 10 GB or more under `Avail` |

A gate that fails stops the lane here. Nothing has been written. A tool that fails at import while the
Fable switch is being edited: note the traceback's last line, wait, try again; never edit code.

Report to the orchestrator before step 2, with these three readings (they do not stop the answering):

```bash
grep -c name_is_alias_on_survivor scripts/remediation/identity/dup_clusters.py
$PY scripts/remediation/mechanical/dup_merge.py --help 2>/dev/null | grep -c files
grep -c LANE_SPHERE scripts/remediation/identity/dup_judge.py
```

* First line `1`: G2 is in the tree (available after the merge of build/track-b). `0` (the tree of
  2026-11-10 before the merge): Caparra enters this pass only if G2 is in the tree when step 2 runs
  `dup_clusters.py`, or through the one re-run step 2 allows.
* Second line `1` or more (it prints `3`): G1 is in the tree (available after the merge of
  build/track-b), and with it G3. `0`: step 9 stops at gate 9.3 for every wave that moves an image row,
  and at 9.1 for a wave whose first loser has no neighbour.
* Third line `2`: G5 is in the tree (available after the merge of build/track-b): a MERGE beyond 2,000 m
  is decided by verdict and re-check (O14). `0`: the verdict import holds such a MERGE in every round
  (step 3, `beyond 2000 m ...`); it reaches the re-check only if G5 is in the tree at the import of a
  verdict round that answers its cluster (r1, r2 or r3). The merge changes no prompt text, so a round
  exported before it imports after it.

### Step 1 - keep part A's basis

Read first: the probe shows the export basis `2026-11-05 ...`. The copy is named after the basis date, as
the D20 playbook names it; whichever lane comes first makes it, the other skips it. If the probe already
shows a newer basis, the copy must exist (`ls -d output/remediation/final-2026-10-08/identity-2026-11-05`);
if it does not, report it and go on: part A's inputs are also in git (`mechanical_dup_merge/2026-11-05/`).

```bash
[ -e output/remediation/final-2026-10-08/identity-2026-11-05 ] || cp -r $RUN output/remediation/final-2026-10-08/identity-2026-11-05
```

Produces a 12 MB copy of the run directory as part A left it. No agent. Done when
`ls output/remediation/final-2026-10-08/identity-2026-11-05/DUP_DECISIONS.jsonl` succeeds.

### Step 2 - fresh production read and clusters (no model)

Read first: the probe shows no `dup-verdict` round, and `find $RUN -name ROUNDS.jsonl` still shows no
round of another identity lane that is exported and not imported (`export.py` would void its answers).

```bash
$PY scripts/remediation/identity/export.py
$PY scripts/remediation/identity/dup_clusters.py
```

Run both, in this order, once. If the probe already shows an export basis less than 6 hours old (the D20
driver refreshed it), skip `export.py` and run `dup_clusters.py` only.

* `export.py` reads production once (read-only, one repeatable-read snapshot, over ssh) and replaces
  `$RUN/EXPORT.jsonl`. It prints the counts: expect `shown` 4907 and `losers` 25 (other lanes may have
  retired sites since; write the numbers and `exported_at` into `NOTES.md`). Tell the orchestrator that
  `EXPORT.jsonl` was refreshed: the other identity lanes rebuild their own discovery files from it.
* `dup_clusters.py` replaces `$RUN/DUP_CLUSTERS.jsonl` and prints its counts: expect `clusters` 90,
  `cluster_sites` 225, `retired_losers_holding` 23 without G2. With G2 in the tree (available after the
  merge of build/track-b) it lists every retired loser that holds an image, a link or a name its survivor
  lacks, each with `"holds": [...]`, and prints `retired_losers_holding` 24 and
  `retired_losers_holding_name` 1 on a fresh export (Caparra; run on the export of 2026-11-05 it printed
  24 and 13, because that export predates part A's 12 name moves).
* Done when the probe shows the new export basis and `clusters built from this export True`. Refused or
  wrong when a command exits non-zero, or `clusters` is outside 85 to 95: stop and report (the population
  moved). With another `clusters` count inside that range, every count of steps 3 to 7 and of section 7
  moves with it (one verdict question per cluster, 5 per batch).
* Caparra: `grep -c cf49332c $RUN/DUP_CLUSTERS.jsonl`. `1` means it is in the write (its record says
  `"holds": ["name"]`; its move is two cells, the loser's label row 3580496 becoming an alias of Cáparra).
  `0` means G2 is not in the tree (build/track-b is not merged): report it now; the answering goes on.

From here until step 8 is done, `EXPORT.jsonl`, `DUP_CLUSTERS.jsonl`, the wiki cache and the checkout's
path are frozen (rule 1).

**The one allowed re-run, for G2** (available after the merge of build/track-b). When the orchestrator
reports build/track-b merged after this step, and before step 7: only while no round of this lane is
exported and unimported, and only if the probe still shows the export basis noted above,

```bash
grep '"record": "cluster"' $RUN/DUP_CLUSTERS.jsonl | sha256sum > $DRV/clusters-before.sha256
cp $RUN/DUP_CLUSTERS.jsonl $DRV/DUP_CLUSTERS.before-g2.jsonl
$PY scripts/remediation/identity/dup_clusters.py
grep '"record": "cluster"' $RUN/DUP_CLUSTERS.jsonl | sha256sum | diff - $DRV/clusters-before.sha256 && echo CLUSTERS-UNCHANGED
grep -c cf49332c $RUN/DUP_CLUSTERS.jsonl
```

must print `CLUSTERS-UNCHANGED` and `1` (the cluster lines are a pure function of the unchanged
`EXPORT.jsonl`: built with the G2 code from the export of 2026-11-05, the 90 cluster records were
identical on 2026-11-10; only `retired_loser` lines change - one is added, and `holds` can gain
`"name"`). Without `CLUSTERS-UNCHANGED`: stop and report at
once, export nothing, and do not copy the saved file back (that is the orchestrator's decision). `export.py`
is never part of this re-run. Without G2 by step 7, Caparra's alias stays open and is named in the lane
report.

### Step 3 - `dup-verdict` round 1 (agents)

Read first: the probe shows no `dup-verdict` round and `ls $H/d14b-dup-verdict-r1` fails.

```bash
$PY scripts/remediation/identity/dup_judge.py export --stage dup-verdict --handoff output/remediation/handoff/d14b-dup-verdict-r1
```

Prints `{"round": "r1", "batches": {"r1-b01": 5, ...}}`: one question per cluster, 5 clusters per batch,
18 batches for 90 clusters. It writes `$RUN/dup/dup-verdict/ROUNDS.jsonl` and, per batch,
`<handoff>/<batch>/MANIFEST.jsonl` with the prompt files. Refused: exit 2 and `REFUSED: ...` (the handoff
directory is not empty: use the next free name and write it into `NOTES.md`; the wiki cache index is
missing: stop).

One brief per batch (stdout is the brief, the logging line goes to stderr):

```bash
mkdir -p $DRV/briefs/dup-verdict-r1
for b in $($PY -c "import json;print(' '.join(json.loads(open('output/remediation/final-2026-10-08/identity/dup/dup-verdict/ROUNDS.jsonl',encoding='utf-8').read().splitlines()[-1])['batches']))" | tr -d '\r'); do
  $PY scripts/remediation/identity/dup_judge.py brief --stage dup-verdict --round r1 --batch-id $b > $DRV/briefs/dup-verdict-r1/$b.txt 2>/dev/null
done
head -c 60 $DRV/briefs/dup-verdict-r1/r1-b01.txt   # must start with "You are agent r1-b01"
grep -L "^You are agent" $DRV/briefs/dup-verdict-r1/*.txt   # must print nothing
grep -c "claude-fable-5-2 --role web_verifier" $DRV/briefs/dup-verdict-r1/r1-b01.txt   # 1
```

(`tr -d '\r'` is needed: this Python prints CRLF, and the last batch id would carry the `\r`.) The batch
list is read from the newest round of the stage; for r2 and r3 change `r1` in `--round` and in the
directory name. A brief file that `grep -L` names is empty: the brief command was refused (run it once
without `2>/dev/null` and read the `REFUSED:` line).

Agents:

| | |
|---|---|
| role | `web_verifier` |
| model, effort | `claude-fable-5-2`, high |
| web research | yes: the cached Wikipedia files first, every other source live |
| batch size | 5 clusters (2 to 11 records each) |
| answers expected | one per cluster: 90 |
| width | what the orchestrator grants, at most 3 web agents over all lanes |
| prompt | the brief file's text, verbatim, to one fresh agent per batch, working directory `C:/PythonProjects/AncientMap` |

The agent writes each answer to its scratch file, checks its shape with
`dup_judge.py check-answer` and records it with `opus_handoff.py answer --role web_verifier --model
claude-fable-5-2` (both commands are in the brief). An answer is written once.

Done detection:

```bash
$PY scripts/remediation/opus_handoff.py validate --dir $H/d14b-dup-verdict-r1
```

Exit 0 and `"ok": true` with `answered` = `questions`; exit 1 while anything is open. `missing` lists the
open questions by batch and label: give a fresh agent the same brief with one added line, "Only these
labels are open: <labels>; record with `--answered-by <batch>b`". `stale`, `malformed` or `orphans`
entries mean a file of the handoff directory was touched (rule 2): stop. This check compares each answer
with the handoff's own prompt files; it does not see a moved basis (the import does).

Import (fetches the quoted pages serially, 1 s per host; run it while fewer than 3 web agents of any lane
are fetching):

```bash
$PY scripts/remediation/identity/dup_judge.py import --stage dup-verdict --round r1
```

Prints `{"answers": N, "decided": d, "held": h, "held_reasons": {...}, "pages": {...}, "round": "r1",
"stage": "dup-verdict"}` and writes `$RUN/dup/dup-verdict/answers/r1.jsonl`, `DECISIONS.jsonl` and `pages/`.
Done when the probe shows `r1 ... imported True`. Refusals (exit 2, nothing written):

* `... does not validate (...)`: answers are missing; back to the agents.
* `...: stale: the answer names prompt ..., the question is ...`: the prompt rebuilt from the data is not
  the one the agent read: `EXPORT.jsonl`, `DUP_CLUSTERS.jsonl` or the wiki cache changed since the export
  (rule 1). Stop and report; no answer of the round imports until the orchestrator has decided.
* `round rN is not the newest (...)`: import the newest round only.
* `role web_verifier answered, but no passed calibration of it is named`: the Fable switch is not in the
  tree (gate of step 0); stop. Do not pass `--calibration`, do not run a calibration.
* `answered in role ...`, `answered by MiniMax`, a stamp that is not the role's: the answer does not count;
  stop and report the batch.

The import keeps every fetched page under `$RUN/dup/dup-verdict/pages/`, a failed fetch too, and never
fetches a kept URL again in this stage.

Checkpoint: `held` above 40 % of the round's answers (36 of 90) stops the lane for a report. List the held
clusters and why:

```bash
$PY - <<'EOF'
import json, pathlib, collections
d = pathlib.Path('output/remediation/final-2026-10-08/identity/dup/dup-verdict/DECISIONS.jsonl')
rows = [json.loads(l) for l in d.read_text(encoding='utf-8').splitlines() if l.strip()]
print(dict(collections.Counter(r['status'] for r in rows)))
print('decided with a MERGE or PART_OF (the recheck asks these):', sum(1 for r in rows if r['status'] == 'decided' and any(m['verdict'] in ('MERGE', 'PART_OF') for m in r['members'])))
for r in rows:
    if r['status'] == 'held':
        print(r['label'], '|', r['reason'][:220])
EOF
```

The reasons and what they ask of the driver:

* `a quote does not count (fetch failed: <url>)` with a 403 or 429 is the throttle, not a finding: test
  the URL with `curl -s -o /dev/null -w '%{http_code}' '<url>'`, note it, and lower the width. The stored
  failed page stays failed for this stage; the re-ask shows the agent which quote did not count, and it
  cites another page.
* `a quote does not count (not found: <url>)`: the page was read and the text is not on it; the re-ask
  carries it.
* `shape: ...`: the answer was not the JSON the prompt asks for (the agent skipped `check-answer`); the
  re-ask carries it.
* `beyond 2000 m (<n> m): a per-pair override ...`: a MERGE further apart than the limit, held by a tree
  without G5 (the third reading of step 0 is `0`). O14 decides such a pair by verdict and re-check, and
  the code that does it is on build/track-b: report the cluster to the orchestrator at once, with both
  names and the distance, and "build/track-b is not merged". The re-ask (step 4) asks the cluster
  again; once G5 is in the tree at that round's import the MERGE is decided like any other and the
  re-check is asked it. A cluster still held for its distance after the third verdict round stays on
  the held list. With G5 in the tree this reason does not occur: the distance alone holds nothing,
  the pair's limit becomes its own distance (`metres_limit` in `DECISIONS.jsonl`, above 2000), and
  only a re-check that CONFIRMs it with a found quote makes the merge (step 7). No
  `$RUN/dup/OVERRIDES.json` is written (rule 2).

### Step 4 - `dup-verdict` re-asks (rounds r2 and r3)

Read first: the newest `dup-verdict` round is imported and `held` > 0.

```bash
$PY scripts/remediation/identity/dup_judge.py export --stage dup-verdict --handoff output/remediation/handoff/d14b-dup-verdict-r2
```

It asks the whole of every held cluster again, each prompt carrying why the earlier answer was not counted.
Then exactly the loop of step 3 with `r2` in every path and command (briefs into
`$DRV/briefs/dup-verdict-r2`, batches `r2-b01`...), then once more with `r3` if clusters are still held.
The stage is finished when the export answers `REFUSED: no question to ask - nothing to export` (nothing is
held) or `REFUSED: 3 dup-verdict rounds are out: what stays held is listed, not asked`. Expect about 14
questions in r2 and about 4 in r3. On a tree without G5 a cluster with a MERGE beyond 2,000 m is held in
every round; with G5 it is decided on its quotes like any other (O14).

### Step 5 - `dup-recheck` round 1 (agents)

Read first: step 4 is finished: the probe shows the newest `dup-verdict` round imported and either no
`held` or three rounds. The tool does not enforce this order; the playbook does: the recheck prompt is
built from the verdict decisions, and a cluster that a later verdict round decides would use up one of
the three recheck rounds.

```bash
$PY scripts/remediation/identity/dup_judge.py export --stage dup-recheck --handoff output/remediation/handoff/d14b-dup-recheck-r1
```

It asks every cluster whose verdict is decided and holds a MERGE or PART_OF: expect about 60 clusters in 12
batches. `REFUSED: no cluster has a decided MERGE or PART_OF to recheck` means the lane has nothing to
write: go to step 7 for the lists and stop after them.

Briefs: the first ten clusters (batches `r1-b01` and `r1-b02`) are read by the pilot judge, the rest by the
adversarial reader:

```bash
mkdir -p $DRV/briefs/dup-recheck-r1
for b in $($PY -c "import json;print(' '.join(json.loads(open('output/remediation/final-2026-10-08/identity/dup/dup-recheck/ROUNDS.jsonl',encoding='utf-8').read().splitlines()[-1])['batches']))" | tr -d '\r'); do
  case $b in r1-b01|r1-b02) role=pilot_judge;; *) role=adversarial;; esac
  $PY scripts/remediation/identity/dup_judge.py brief --stage dup-recheck --round r1 --batch-id $b --role $role > $DRV/briefs/dup-recheck-r1/$b.txt 2>/dev/null
done
grep -L "^You are agent" $DRV/briefs/dup-recheck-r1/*.txt   # must print nothing
grep -l -e "--role pilot_judge" $DRV/briefs/dup-recheck-r1/*.txt   # exactly r1-b01.txt and r1-b02.txt
```

| | batches `r1-b01`, `r1-b02` | all other batches |
|---|---|---|
| role | `pilot_judge` | `adversarial` |
| model, effort | `claude-fable-5-2`, xhigh | `claude-fable-5-2`, high |
| web research | yes | yes |
| batch size | 5 clusters | 5 clusters |
| answers expected | 10 | about 50 |

Validate and import as in step 3:

```bash
$PY scripts/remediation/opus_handoff.py validate --dir $H/d14b-dup-recheck-r1
$PY scripts/remediation/identity/dup_judge.py import --stage dup-recheck --round r1
```

The import prints the same summary; a recheck decides per relation CONFIRM, RETARGET or REJECT. Only a
CONFIRM of the same target makes a merge.

### Step 6 - `dup-recheck` re-asks (rounds r2 and r3)

Read first: the newest `dup-recheck` round is imported and `held` > 0.

```bash
$PY scripts/remediation/identity/dup_judge.py export --stage dup-recheck --handoff output/remediation/handoff/d14b-dup-recheck-r2
```

The loop of step 5 with `r2` (then `r3`); every re-ask batch is briefed without `--role` (the adversarial
reader). Finished at `REFUSED: no question to ask - nothing to export` or `REFUSED: 3 dup-recheck rounds are
out`. Expect about 8 and about 2 questions.

### Step 7 - decisions, lists, spot check (one agent)

Read first: both stages are finished.

```bash
$PY scripts/remediation/identity/dup_judge.py decisions
```

Writes `$RUN/DUP_DECISIONS.jsonl` and prints `{"clusters": ..., "held_members": ..., "merges": ...,
"part_of": ..., "status": {"complete": ..., "held": ...}, "wrong_id": ...}`. Done when `status` has no
`unanswered`. `pending-recheck` > 0 with recheck rounds left: back to step 6. A `pending-recheck` that is
left after three recheck rounds (a recheck answer that never was in shape) is written to
`OPEN_CLUSTERS.jsonl` below and reported; nothing of that cluster is merged, and the lane goes on. The
command may be run again at any time before step 8; it rewrites the file from the imported rounds.
Expected: 25 to 40 new merges plus the 23 or 24 retired-loser records, 35 to 45 PART_OF members, 5 to 10
WRONG_ID records. Ten clusters hold records more than 2,000 m apart (Kilmartin up to 2,217 m,
Engomi/Enkomi 2,058 m and the eight clusters between 8.7 km and 2,589 km, which should come back
DISTINCT or WRONG_ID). With G5 in the tree a MERGE among them is a merge when the re-check CONFIRMed
it with a found quote, and held with the reasons of both readers when it did not (O14); on a tree
without G5 every such MERGE is held for its distance. The merges beyond 2,000 m are the lines of
`$DRV/MERGES.jsonl` (written below) with `metres_limit` above 2000: name each in `NOTES.md` and in
the lane report, with both names and `metres`.

Lists for the report and the other lanes (writes only into `$DRV`):

```bash
$PY - $DRV <<'EOF'
import json, pathlib, random, sys
run = pathlib.Path('output/remediation/final-2026-10-08/identity')
drv = pathlib.Path(sys.argv[1])
NL = chr(10)
recs = [json.loads(l) for l in (run / 'DUP_DECISIONS.jsonl').read_text(encoding='utf-8').splitlines() if l.strip()]
def dump(name, rows):
    (drv / name).write_text(''.join(json.dumps(r, ensure_ascii=False, sort_keys=True) + NL for r in rows), encoding='utf-8', newline=NL)
    print(name, len(rows))
merges = [dict(m, cluster_id=r['cluster_id']) for r in recs for m in r['merges']]
new = [m for m in merges if not m.get('already_retired')]
dump('MERGES.jsonl', merges)
dump('PART_OF_LIST.jsonl', [dict(m, cluster_id=r['cluster_id']) for r in recs for m in r['part_of']])
dump('WRONG_ID_LIST.jsonl', [dict(m, cluster_id=r['cluster_id']) for r in recs for m in r['wrong_id']])
dump('HELD_LIST.jsonl', [dict(h, cluster_id=r['cluster_id'], cluster_status=r['status']) for r in recs for h in r['held']])
dump('OPEN_CLUSTERS.jsonl', [{'cluster_id': r['cluster_id'], 'status': r['status']} for r in recs if r['status'] in ('unanswered', 'pending-recheck')])
(drv / 'LOSERS.txt').write_text(''.join(m['site_id'] + NL for m in new), encoding='utf-8', newline=NL)
dump('SPOT_PACK.jsonl', random.Random(20261110).sample(new, min(10, len(new))))
(drv / 'DUP_DECISIONS.final.jsonl').write_bytes((run / 'DUP_DECISIONS.jsonl').read_bytes())
EOF
```

Spot check (the orchestrator's checkpoint, D156; not a handoff answer, nothing is recorded in a lane): one
fresh agent, `claude-fable-5-2`, effort high, web allowed. Prompt: "Read
`output/remediation/final-2026-10-08/drivers/d14b-duplicates/SPOT_PACK.jsonl`. Each line says that record
`site_id` (`name`) is the same site as record `target` (`target_name`) and will be retired onto it, with
`why`, `recheck_why`, `quotes` and `metres`. For each line decide HOLDS or WRONG from sources you read
yourself (the cached article under `output/remediation/final-2026-10-08/wiki_cache/` first, then live
pages), looking for the reasons a merge is wrong: two buildings of one complex, a town and its ancient site,
a site and its museum, namesakes. Write
`output/remediation/final-2026-10-08/drivers/d14b-duplicates/SPOT_RESULT.json`: a list of
`{site_id, target, verdict, reason, source}`." Done when the file exists with one entry per pack line. Any
WRONG stops the lane before step 8; the pair goes to the orchestrator.

### Step 8 - waves (no model)

Read first: `SPOT_RESULT.json` has no WRONG; `ls output/remediation/mechanical_dup_merge/` shows no
directory of today's date.

```bash
W=$(date -u +%F)
$PY scripts/remediation/mechanical/dup_merge.py waves --date $W
```

Prints `{"<W>": {"pairs": n, "file": ".../PAIRS.json"}, ..., "excluded": []}`: waves of whole pairs, at
most 100 sites each, the pairs of one survivor together, a merge chain followed to its final survivor. The
retired-loser records come last, so a second wave `<W>b` may hold only those. The 21 pairs of part A are
in the waves again (their record is still `complete` in `DUP_DECISIONS.jsonl`); their plans answer
`nothing to move`. Write every label into `NOTES.md`. No `--exclude`, unless the orchestrator handed you
an exclusion file after the spot check (rule 8): then `--exclude <file>`, and the printed `excluded` must
name exactly its losers. Refused (exit 1): `... exists: a wave is planned once - take a new label` (the
label is taken: `--date` must be a plain date as soon as the split gives two waves, because the second
label is `<date>b`; use the next free date, tomorrow's, and write it into `NOTES.md`; a wave directory
that holds only an unused `PAIRS.json` stays as it is), `DUP_DECISIONS.jsonl holds no decided MERGE`,
`... excluded, but no decided pair has it as its loser` (a wrong id in the exclusion file: back to the
orchestrator).

Check that the named cases are in:

```bash
for id in 4a5a324f 5a04d6f3 cf49332c; do echo "$id: $(grep -l "\"loser\": \"$id" output/remediation/mechanical_dup_merge/$W*/PAIRS.json | tr '\n' ' ')"; done
```

names one wave file for Tarxien (`4a5a324f`) and one for Dodona (`5a04d6f3`), and one for Caparra
(`cf49332c`) when step 2 found it. A named case without a file: stop and report before step 9.

Give `$DRV/LOSERS.txt` to the orchestrator now: the card, description and image lanes drop these sites
from their populations.

### Step 9 - write one wave (repeat per wave label, in label order)

Set `W` to the wave label in every call, and in 9.4 to 9.6 also `L` and `D` as their first line sets them
(no variable carries over between calls). The driver detects a finished stage by its exit code, written as
`EXIT=<n>` into the evidence file, and by the texts named below. Before 9.2 and before 9.5 read the journal
query of section 3: the wave's stamp must have no row for the lane about to be planned (rule 4).

**9.0 Backup and restore drill, once per day.**

```bash
ssh ancientnerds 'S=$(date +%F)_remediation; tail -1 /var/www/ancientnerds/backups/$S/DRILL_REPORT.txt'
```

Must print `VERDICT: dump is restorable and matches production row-for-row.` If the file is missing, run
`ssh ancientnerds "cd /var/www/ancientnerds/scripts/remediation && DO_DRILL=1 ./00_backup_and_drill.sh"`
(exit 0, about 5 minutes) and read the line again.

**9.1 Pre-flight for the retirement's guard probe** (G3). The probe of the check "a loser retires onto
the survivor decided for it" needs another shown curated site within 2,000 m of a planned loser. With G3
in the tree (available after the merge of build/track-b; gate: the second reading of step 0 is not `0`)
`apply.py --probe-guards` asks the planned losers in plan order, takes the first that has such a
neighbour and corrupts that loser's cell; it refuses only when no planned loser has one. The pre-flight
asks the same of the whole wave (read-only, 1.5 s for 23 pairs on 2026-11-10):

```bash
mkdir -p /c/tmp/d14b && $PY - "$W" <<'EOF' > /c/tmp/d14b/preflight.sql
import json, sys
pairs = json.load(open('output/remediation/mechanical_dup_merge/%s/PAIRS.json' % sys.argv[1], encoding='utf-8'))['pairs']
new = [p for p in pairs if not p['already_retired']]
if not new:
    print("SELECT 'no pair to retire in this wave';")
else:
    values = ", ".join("('%s'::uuid, '%s'::uuid)" % (p['loser'], p['survivor']) for p in new)
    planned = ", ".join("'%s'::uuid" % p['loser'] for p in new)
    d = "ST_DistanceSphere(ST_MakePoint(s.lon, s.lat), ST_MakePoint(u.lon, u.lat))"
    print("SET statement_timeout = '30s';")
    print("SELECT count(DISTINCT u.id) || ' of %d planned loser(s) have a neighbour, one of them: ' || min(u.name) FROM (VALUES %s) AS p(loser, survivor) JOIN unified_sites u ON u.id = p.loser JOIN unified_sites s ON s.source_id = 'ancient_nerds' AND s.scope_status IS DISTINCT FROM 'retired' AND s.id <> p.survivor AND s.id NOT IN (%s) WHERE %s <= 2000 HAVING count(*) > 0;" % (len(new), values, planned, d))
EOF
ssh ancientnerds "docker exec -i ancient_nerds_db psql -U ancient_map -d ancient_map -At -F ' | '" < /c/tmp/d14b/preflight.sql
```

It prints `SET` and then the answer. Pass: one line `<n> of <m> planned loser(s) have a neighbour, one of
them: <name>`, or `no pair to retire in this wave`. Only `SET`: no loser of the wave has a neighbour, and
the retirement's probe will refuse (`REFUSED: none of the <m> planned site(s) has another curated shown
site within 2000 m`); do not start the wave's move (a move without its retirement leaves a shown duplicate
with an emptied gallery) and report it: the orchestrator plans those pairs in a wave with others. About a
third of the cluster members have no such neighbour, so a wave of several pairs passes as a rule (14 of
23 in the trial of 2026-11-10). The pre-flight reads every pair of `PAIRS.json` that is not retired yet;
the probe reads the losers `plan-retire` really plans, which are fewer when a pair is held in 9.5: then
9.6's own refusal decides. On a tree without G3 (the second reading of step 0 is `0`) the probe takes the
first planned loser only, and this pre-flight does not say whether that one has a neighbour: do not start
a wave's move on such a tree, report "build/track-b is not merged".

**9.2 Plan the move** (reads production read-only, one snapshot; with G1 in the tree also one read-only
sha256 listing of the wave's image folders on the VPS, about 10 s for 272 folders).

```bash
$PY scripts/remediation/mechanical/dup_merge.py plan-move --wave $W --write
```

Prints `{"lane": "dup-merge-move-<W>", "sites": .., "cells": .., "pairs": .., "images": .., "images_stay":
.., "heroes_demoted": .., "links": .., "links_stay": .., "names": .., "held": ..}` and writes
`mechanical_dup_merge/<W>/move/{READ.jsonl,PLAN.jsonl,PLAN.md,HELD.jsonl,ROLLBACK.sql}`.

Available after the merge of build/track-b (G1): the summary also prints `"images_stay_filename": ..`, and
the directory also holds `DISK.json` (the folder listing the plan was built on: folder, filename, sha256)
and `FILES.jsonl` (one line per moved image row: `row_id`, `filename`, `source` and `dest` as
`<folder>/<filename>`, `sha256`; an empty file when the plan moves no image row). What the plan does with
an image row of the loser:

| the row | the plan |
|---|---|
| its `original_url` is on a row of the survivor | stays on the loser (`images_stay`), as before |
| its filename is the filename of a row of the survivor, or the survivor's folder holds other bytes under that name (`hero.webp`; a file no row names counts) | stays on the loser (`images_stay_filename`): moved, it would show the survivor's picture under its own credit. The retirement takes such a row as it is |
| its file is not in the loser's folder | the pair is held: `image row <id> names the file '<name>', which is not in the loser's folder <8 hex>: there is no picture to carry` |
| anything else | moves (`images`), and its file is in `FILES.jsonl` |

* `REFUSED: no pair of the wave has a row to move: nothing to plan`: this wave has no move; go to 9.5.
* Read `move/HELD.jsonl`. `nothing to move: the pair goes straight to its retirement` is expected (every
  part A pair says so). Any other reason (a changed name, a retired survivor, a distance above the limit,
  `the alias would need an INSERT`, `... is retired onto the loser already`, `the loser is retired for
  another reason`, `... there is no picture to carry`, a premise mismatch) means that pair is not written:
  copy the line into `NOTES.md` for the lane report.
* `REFUSED: the folder listing ...`, `REFUSED: the script on the VPS exited ...` or `REFUSED: the VPS did
  not answer ...`: the listing of the folders failed (it changes nothing on the VPS); run 9.2 again.
* Expect `images` 40 or more in the wave that holds Tarxien and Dodona (20 each; a trial plan of the three
  named cases from production on 2026-11-10 gave 45 cells: 40 images, 0 `images_stay_filename`, 3 links,
  2 `links_stay`, 1 name - Caparra's -, 0 held).
* Write `images_stay_filename` into `NOTES.md`: these pictures stay on the retired loser and are in the
  lane report (they are among the `wiki_images` count of 10.5).
* `REFUSED: ... journal row(s) exist for this wave: a lane that has written is never re-planned`: the
  move of this wave is applied already and this call broke rule 4 (`READ.jsonl` is overwritten: say so in
  `NOTES.md`); go on at the first missing step after its apply.
* Probe pre-check (gap G4, **built 2026-11-12, commit `3464223`, O24**): the guard probe borrows a row of a
  non-curated site from the first table of the plan, in plan order, that has one
  (`rowlane.foreign_row(lane, rowlane.plan_tables(records))`), and swaps it into a cell of that table. It
  refuses only when no table of the plan has such a row: `REFUSED: no row of a non-curated site in any table
  of the plan (<tables>) to probe the source guard with`; stop and report then. Measured read-only for
  `2026-11-12/move` (tables `site_content_links`, `unified_site_names`, `wiki_images`): `site_content_links`
  0 rows, `unified_site_names` answers (row 1855772, Great Pyramid of Giza), so guard 1 is probed on a
  `unified_site_names` cell. No pre-check command is needed any more.

**9.3 File gate** (G1; the `files` command is available after the merge of build/track-b). Read `images`
of 9.2.

* `$PY scripts/remediation/mechanical/dup_merge.py --help 2>/dev/null | grep -c files` prints `0`: the
  tree has no `files` command. With `images` = 0 go to 9.4. With `images` > 0 stop this wave here, before
  any emit, and report "blocked by G1: build/track-b is not merged" with the wave's `images` count; a
  later wave whose plan has `images` 0 may still be written.
* It prints `1` or more: the plan must come from that code - `ls $D/FILES.jsonl` must succeed
  (`D=output/remediation/mechanical_dup_merge/$W/move`); when the merge landed after 9.2, run 9.2 again
  first (its stamp has no journal row yet). Then, also when `images` is 0 (the commands then answer
  `"files": 0` without asking the VPS):

```bash
D=output/remediation/mechanical_dup_merge/$W/move; mkdir -p $D/evidence
$PY scripts/remediation/mechanical/dup_merge.py files --wave $W --copy > $D/evidence/00a_files-copy.txt 2>&1; rc=$?; echo "EXIT=$rc" >> $D/evidence/00a_files-copy.txt; echo "copy exit $rc"
$PY scripts/remediation/mechanical/dup_merge.py files --wave $W --verify > $D/evidence/00b_files-verify.txt 2>&1; rc=$?; echo "EXIT=$rc" >> $D/evidence/00b_files-verify.txt; echo "verify exit $rc"
```

  * `--copy` reads the folders, copies every picture of `FILES.jsonl` that is not yet in its survivor's
    folder (on the VPS, `cp` under a partial name `<file>.d14-part`, then renamed; a new folder gets mode
    777 and a new file 666 like the rest of the tree; it never moves a file - the loser keeps its own -
    and never overwrites one), reads the folders again and compares each file's sha256 with the plan's.
    Pass: exit 0 and `{"lane": ..., "files": n, "copied": c, "already_there": n - c}` with `files` equal to
    the plan's `images`. Running it again is safe (`copied` 0).
  * `--verify` is read-only. Pass: exit 0 and `"not": []`. Exit 1 lists each picture that is not in place.
  * Exit 1 and `REFUSED: the image folders are not as the plan read them, nothing was copied`, with lines
    `the loser's file is gone or is another file than the plan read: ...` or `the survivor's folder holds
    another file under this name: ...`: a folder changed between 9.2 and now. Run 9.2 again (allowed while
    the stamp has no journal row), then this step.
  * Exit 1 and `REFUSED: after the copy these pictures are not in place`, `the script on the VPS exited
    ...` or `the VPS did not answer ...`: the copy stopped. Run `--copy` again; if it refuses twice, stop
    and report (a file `*.d14-part` may be left in a survivor's folder: name it in the report, do not
    delete it).
  * `REFUSED: ... FILES.jsonl does not exist` or `... is not the file list of ...`: the plan is not from
    this code, or a file of the plan directory was touched (rule 2): run 9.2 again.

  Continue only when `--verify` exits 0. The copy is a write on the VPS outside the journal: it only adds
  files, never replaces or deletes one, and the image tree is not in the database backup. For the wave
  with Tarxien and Dodona it creates the folder `318414bc` (20 files) and adds 20 files to `56f594fc`,
  whose own file `Dodona-Greece-April-2008-107.webp` stays as it is.

**9.4 The move lane.** One flag per call.

```bash
L=dup-merge-move-$W; D=output/remediation/mechanical_dup_merge/$W/move; mkdir -p $D/evidence
for s in 01:emit 02:rehearse 03:probe-guards; do
  n=${s%%:*}; f=${s#*:}
  $PY scripts/remediation/mechanical/apply.py --lane $L --$f > $D/evidence/${n}_$f.txt 2>&1; rc=$?
  echo "EXIT=$rc" >> $D/evidence/${n}_$f.txt; echo "$f exit $rc"; [ $rc -eq 0 ] || break
done
grep -c "guard=False" $D/evidence/03_probe-guards.txt; grep -c "ERROR" $D/evidence/02_rehearse.txt
```

Pass before the apply: three times exit 0; `02_rehearse.txt` shows `NOTICE:  D14 duplicate move: <cells>
of <cells> planned cell(s) changed and journalled over <n> curated site(s)`, `INSERT 0 <cells>`, `DO`,
`ROLLBACK` and `journal rows for this run stamp | 0`, no `ERROR`; `03_probe-guards.txt` has every probe
line `refused by its own guard=True`, `journal rows left by this probe: 0` and no `guard=False` (exit 7
is a probe that its own guard did not refuse: stop; exit 1 with `REFUSED: no ... row of a non-curated
site to probe the source guard with` is gap G4: stop, nothing is written). A line `[site invariant - ...]
not probed: the plan writes no cell it could corrupt` is information, not a failure: copy it into
`NOTES.md`. This is the first wave that moves image rows: read the whole of both files, not only the
greps.

```bash
$PY scripts/remediation/mechanical/apply.py --lane $L --apply > $D/evidence/04_apply.txt 2>&1; rc=$?; echo "EXIT=$rc" >> $D/evidence/04_apply.txt; echo "apply exit $rc"; grep -c "APPLY OK" $D/evidence/04_apply.txt
```

| exit | meaning | what to do |
|---|---|---|
| 0 and `APPLY OK: the read-back matches the plan, row for row` | written | continue |
| 1 `REFUSED` | nothing was sent | read the message; a moved premise or old value: run 9.2 again (allowed while the stamp has no journal row), then 9.3 and 9.4 from `emit`. `REFUSED: <n> picture(s) of the moved image rows are not in place - run dup_merge.py files --copy for this wave first` (available after the merge of build/track-b: the apply reads the folders itself before the write): back to 9.3, then `--apply` again. `REFUSED: ... FILES.jsonl does not exist`: the plan was written by a tree without G1; run 9.2 again, then 9.3 and 9.4 from `emit` |
| 3 | not committed | as exit 1 |
| 4 | committed, psql did not end cleanly | treat as written, run `--verify`, never apply again |
| 5 | outcome unknown | run the journal count of section 3 until it is settled; never retry before it reads 0 rows |
| 6 | committed, read-back not confirmed | stop and report |

```bash
for s in 05:verify 06:rehearse-rollback; do
  n=${s%%:*}; f=${s#*:}
  $PY scripts/remediation/mechanical/apply.py --lane $L --$f > $D/evidence/${n}_$f.txt 2>&1; rc=$?
  echo "EXIT=$rc" >> $D/evidence/${n}_$f.txt; echo "$f exit $rc"; [ $rc -eq 0 ] || break
done
```

Acceptance of the move (0 deviations), read from `05_verify.txt` and `04_apply.txt`:

* `journal rows for this run stamp` equals `wc -l < $D/PLAN.jsonl` (`journal rows for this test id` is the
  sum over every move wave: 52 of part A plus the waves of part B written so far);
* `journal rows for the rollback stamp`, `... on non-curated sites`, `... outside wiki_images.site_id, ...`,
  `... with no site_id_ref`, `curated sites with more than one live hero` and `retired duplicates whose
  survivor is retired or not curated` are all 0;
* the three totals (`wiki_images rows`, `site_content_links rows`, `unified_site_names rows of curated
  sites`) are the same under `=== before ===` and `=== after ===`;
* `06_rehearse-rollback.txt`: exit 0, no `ERROR`. Run it right after the verify: once a deploy has
  restarted Lyra, its boot gives the loser a new label row and the rehearsal stops at `uq_usn` for every
  pair that moved a name row (section 8). That one refusal after a deploy is reported, not repaired; the
  forward state stands.

When images moved: every picture of every survivor that gained one must be served. First the lane's own
check (available after the merge of build/track-b): one HEAD request per moved image row, for the path the
row is served from now, `https://ancientnerds.com/data/images/wiki/<survivor, 8 hex>/<filename>`:

```bash
$PY scripts/remediation/mechanical/dup_merge.py files --wave $W --served > $D/evidence/07_files-served.txt 2>&1; rc=$?; echo "EXIT=$rc" >> $D/evidence/07_files-served.txt; echo "served exit $rc"
```

Pass: exit 0 and `"not": []` with `files` equal to the plan's `images`. Exit 1 lists `<status> <url>` for
every picture the site does not answer 200 for: stop, do not plan the retirement, report at once.
`REFUSED: <urlopen error ...>` is a request that got no answer: run it again.

Then the driver's own read-back, which reads what the public API lists for each survivor (the survivor's
own pictures too) and asks for each file; it needs no tool of G1:

```bash
$PY - "$D/PLAN.jsonl" <<'EOF'
import json, sys, urllib.error, urllib.parse, urllib.request
rows = [json.loads(l) for l in open(sys.argv[1], encoding='utf-8') if l.strip()]
survivors = sorted({r['new_value'] for r in rows if r['row_table'] == 'wiki_images' and r['column'] == 'site_id'})
moved = sum(1 for r in rows if r['row_table'] == 'wiki_images' and r['column'] == 'site_id')
bad = listed = 0
for s in survivors:
    images = json.load(urllib.request.urlopen('https://ancientnerds.com/api/wiki-images/' + s, timeout=60))['images']
    listed += len(images)
    for i in images:
        url = 'https://ancientnerds.com' + urllib.parse.quote(i['url'])
        try:
            code = urllib.request.urlopen(urllib.request.Request(url, method='HEAD'), timeout=60).status
        except urllib.error.HTTPError as e:
            code = e.code
        if code != 200:
            bad += 1
            print(code, url)
    print(s, len(images), 'image(s) listed')
print('survivors', len(survivors), '| image rows moved', moved, '| listed', listed, '| not 200:', bad)
EOF
```

Pass: `not 200: 0`, and every survivor lists at least one image (the list holds the rows that are not
excluded, the survivor's own included, so `listed` can differ from `image rows moved`; Templos de Tarxien
`318414bc...` and Archaeological Site of Dodoni `56f594fc...` must list 20 each). Any line with a 404 is
a row whose file is not in the survivor's folder: stop, do not plan the retirement, report at once (that
picture is broken on the live page until its file is there).

**9.5 Plan the retirement** (a fresh read, after the move).

```bash
$PY scripts/remediation/mechanical/dup_merge.py plan-retire --wave $W --write
```

Prints `{"lane": "dup-merge-retire-<W>", "sites": n, "cells": 2n, "held": h}` and writes
`mechanical_dup_merge/<W>/retire/{READ.jsonl,PLAN.jsonl,PLAN.md,HELD.jsonl,ROLLBACK.sql}`.

* `REFUSED: no loser of the wave can be retired yet: nothing to plan` with every pair of the wave already
  retired (a wave of retired-loser records only): expected, the wave is done after 9.4.
* The same refusal with shown losers listed, or lines in `retire/HELD.jsonl`: each line says why
  (`N image(s) the survivor lacks are still on the loser: run the move first`, `the loser already has a scope
  decision`, `the loser shows an image and the survivor shows none`, a journal break). A held loser is not
  retired; copy the line into `NOTES.md`.
* Available after the merge of build/track-b: `plan-retire` reads the wave's image folders too and writes
  `retire/DISK.json` (no `FILES.jsonl`: a retirement moves no picture). An image row that 9.2 left on the
  loser for its filename (`images_stay_filename`) does not hold the retirement; a row whose file was
  copied but which is still on the loser does (`... are still on the loser: run the move first`). On a
  tree without that commit such a row holds its loser for good.

**9.6 The retirement lane.** The commands of 9.4 with `L=dup-merge-retire-$W` and
`D=output/remediation/mechanical_dup_merge/$W/retire`, in the same order: `emit`, `rehearse`,
`probe-guards`, `apply`, `verify`, `rehearse-rollback`, each its own call, with the same pass rules and the
same exit table (the retirement has no picture step: 9.3 and `files --served` belong to the move). With G3
in the tree (available after the merge of build/track-b) `probe-guards` reads a neighbour from the first
planned loser that has one; the probe line `[site invariant - planned site(s) retire onto a survivor other
than the one decided for them] ... refused by its own guard=True` is its proof. `REFUSED: none of the <n>
planned site(s) has another curated shown site within 2000 m: '...' cannot be probed with this plan`: no
loser of the plan has a neighbour (pre-flight 9.1 should have said so); on a tree without G3 the message is
`REFUSED: <name> (<id>) has no other curated shown site within 2000 m` and names the first loser only.
Either way: stop and report at once (the wave is half-written: moved, not retired).

This lane has never been written on production: its rehearsal (`NOTICE:  D14 duplicate retirement: <cells>
of <cells> planned cell(s) changed and journalled ...`, `INSERT 0 <cells>`, `DO`, `ROLLBACK`) and its guard
probes are the first proof. Read both files whole before the apply.

Acceptance of the retirement, from `retire/evidence/04_apply.txt` and `05_verify.txt`:

* `journal rows for this run stamp` = `wc -l < $D/PLAN.jsonl` (two per loser);
* `journal rows for the rollback stamp`, `journal rows for this run outside ...`, `journal rows for this
  run on non-curated rows`, `journal rows for this run with a site_id_ref of another site`, `curated rows
  with a scope_status but no scope_reason` and `retired duplicates whose survivor is retired or not
  curated` are all 0;
* `curated rows retired as a duplicate` and `curated rows with scope_status retired` each rose by the
  number of planned losers between `=== before ===` and `=== after ===` (25 and 97 before the first wave),
  `curated rows with scope_status NULL` fell by it;
* `retired duplicates with a live image whose survivor shows none` is 0 once the move of the wave with
  Tarxien and Dodona is written (2 before it);
* `06_rehearse-rollback.txt`: exit 0, no `ERROR`.

**9.7 Journal recount and read-back, after the wave.**

```bash
ssh ancientnerds "docker exec ancient_nerds_db psql -U ancient_map -d ancient_map -At -F ' | ' -c \"SET statement_timeout='15s'\" -c \"SELECT run_stamp, table_name, column_name, count(*), count(DISTINCT site_id_ref) FROM remediation_change_log WHERE run_stamp IN ('${W}_mechanical-dup-merge-move','${W}_mechanical-dup-merge-retire') GROUP BY 1,2,3 ORDER BY 1,2,3\" -c \"SELECT count(*) FILTER (WHERE scope_status='retired' AND scope_reason LIKE 'duplicate_of:%'), count(*) FILTER (WHERE scope_status IS DISTINCT FROM 'retired') FROM unified_sites WHERE source_id='ancient_nerds'\""
for k in move retire; do mkdir -p output/remediation/mechanical_dup_merge/$W/$k/evidence; $PY scripts/remediation/mechanical/apply.py --lane dup-merge-$k-$W --verify > output/remediation/mechanical_dup_merge/$W/$k/evidence/08_verify_after.txt 2>&1; done
```

The row sums per stamp equal the two plans' line counts; the first count is 25 plus every loser retired so
far, the second 4,907 minus them (unless another lane retired a site meanwhile: say so in `NOTES.md`).
Write one `NOTES.md` line: wave, pairs, cells per lane, held pairs, both recounts.

### Step 10 - after the last wave

Run these in order, once, after the last wave of the lane and after any deploy that is under way has
finished (a deploy restarts the API container and kills a running export).

**10.1 card_stats wave** (the merge moved images and content links, both inputs of a card, and retired
sites). Only one card_stats wave may be in flight over all lanes: ask the orchestrator for the slot.

```bash
ls output/remediation/mechanical_card_stats/      # C = today's date, or the next free letter after it
C=<label>
$PY scripts/remediation/mechanical/card_stats.py --wave $C --export
$PY scripts/remediation/mechanical/card_stats.py --wave $C --write
```

`--write` refuses a plan it cannot prove (the counterfactual must read `0 of N cells differ`) and writes
`mechanical_card_stats/<C>/{PLAN.jsonl,PLAN.md,SKIPPED.jsonl,BASIS.json,ROLLBACK.sql}`; `PLAN.md` states
`<n> cell(s) over <m> ... card(s) will be written`. With 0 cells there is nothing to apply. Otherwise the
six calls of 9.4 with `L=card-stats-$C` and `D=output/remediation/mechanical_card_stats/$C` (pass:
`NOTICE: card_stats recompute: n of n planned cell(s) changed and journalled`, `APPLY OK`, `journal rows for
this run stamp` = n, probes all `guard=True`). Then the read-back that the recompute is complete: plan
again under the next free label (`2026-11-11` is followed by `2026-11-11b`, `2026-11-11b` by
`2026-11-11c`; a label has one letter at most) with `--export`, then `--write`: it must plan 0 cells.
`--write` plans from the export on disk: a write of another lane after the export is refused by guard 5
at the rehearsal or the apply (exit 1 or 3, nothing written) and means: `--export` and `--write` again
under the same label, which is allowed while its stamp has no journal row, then the six calls from `emit`.

**10.2 Image copies** (only when a wave moved image rows):
`ssh ancientnerds "docker exec ancient_nerds_api nice -n 19 python -m pipeline.wiki_thumbs"` (exit 0).

**10.3 Static export and its check.**

```bash
ssh ancientnerds "docker exec ancient_nerds_api python -m api.services.rebuild_static"
scp scripts/remediation/static_export_check.py ancientnerds:/tmp/static_export_check.py
ssh ancientnerds "docker cp /tmp/static_export_check.py ancient_nerds_api:/tmp/x.py && docker exec ancient_nerds_api python /tmp/x.py"
```

`rebuild_static`: `static export ok`, exit 0 (exit 3: an export already runs, wait and run it again; exit
1: failed or interrupted by a deploy, run it again). The check: exit 0, differing 0 (a retired loser the
file still lists counts as a difference). No IndexNow command: Lyra's hourly cycle announces changed and
retired curated sites.

**10.4 Live read-back.**

```bash
while read L; do curl -s -o /dev/null -w "$L %{http_code} %{redirect_url}\n" "https://ancientnerds.com/site.html?id=$L"; done < $DRV/LOSERS.txt
curl -s -o /dev/null -w '%{http_code} %{redirect_url}\n' "https://ancientnerds.com/site.html?id=4a5a324f-832f-4dca-b688-d4a006d297c7"
```

`site.html?id=` answers `301` for every curated id, a shown site to its own page: what is read is the
end of the path. Every retired loser answers `301` to a path that ends in the first 8 hex of its
survivor's id (the `target` of its line in `$DRV/MERGES.jsonl`); a loser that a plan held answers with its
own id and is on the report's held list. Tarxien must still answer
`301 .../sites/malta/templos-de-tarxien-318414bc` (it does today), and the two survivors must list their
20 pictures:

```bash
for s in 318414bc-098b-4459-95c0-41e1ec49c8a8 56f594fc-6819-4d51-98a4-1cf5b4a265a6; do curl -s "https://ancientnerds.com/api/wiki-images/$s" | $PY -c "import json,sys; print('$s', len(json.load(sys.stdin)['images']))"; done
```

prints `20` twice once their wave is written (`0` today).

**10.5 What the merge left on the losers** (report only; no lane moves these rows):

```bash
mkdir -p /c/tmp/d14b && $PY - <<'EOF' > /c/tmp/d14b/left.sql
import pathlib
ids = [l.strip() for l in pathlib.Path('output/remediation/final-2026-10-08/drivers/d14b-duplicates/LOSERS.txt').read_text(encoding='utf-8').splitlines() if l.strip()]
if not ids:
    print("SELECT 'no loser';")
else:
    v = ", ".join("'%s'::uuid" % i for i in ids)
    print("SET statement_timeout = '30s';")
    for t, c in (('news_items', 'site_id'), ('research_paper_sites', 'site_id'), ('card_collections', 'site_id'), ('site_likes', 'site_id'), ('site_bookmarks', 'site_id'), ('site_proposals', 'an_site_id'), ('site_shorts', 'site_id'), ('research_nodes', 'site_id'), ('wiki_images', 'site_id'), ('site_content_links', 'site_id')):
        print("SELECT '%s', count(*) FROM %s WHERE %s IN (%s);" % (t, t, c, v))
    print("SELECT 'losers retired as duplicates', count(*) FROM unified_sites WHERE id IN (%s) AND scope_status = 'retired' AND scope_reason LIKE 'duplicate_of:%%';" % v)
EOF
ssh ancientnerds "docker exec -i ancient_nerds_db psql -U ancient_map -d ancient_map -At -F ' | '" < /c/tmp/d14b/left.sql
```

**10.6 Hand-offs and record.**

* D25 (parents) reads `$RUN/DUP_DECISIONS.jsonl` (`part_of`, and the losers a parent must not be). Nobody
  runs `dup_judge.py decisions` again after a later `dup_clusters.py`; the copy is
  `$DRV/DUP_DECISIONS.final.jsonl`. `$DRV/PART_OF_LIST.jsonl` is the readable list.
* `$DRV/WRONG_ID_LIST.jsonl`: records whose Wikidata item or article names something else. Nothing was
  merged for them; their links are repaired with the link steps of lane D13 (`qid_repair`).
* `$DRV/HELD_LIST.jsonl`: held members with the reason of both readers, among them the merges beyond
  2,000 m that verdict and re-check did not both carry (O14: held and listed): the owner list of this
  lane.
* The image lanes (D17, D59): the survivors that gained pictures are the distinct `new_value` of the
  `wiki_images.site_id` cells of every `move/PLAN.jsonl`; Templos de Tarxien and Archaeological Site of
  Dodoni leave the no-image population.
* Lane D23 (names): the two survivors keep their names here; D23 renames.
* Lane report into `NOTES.md`: answers per stage and round, batches, held and why, merges written, losers
  retired, held pairs, the three named cases, the counts of 10.5, answers against the estimate of 180.
* The orchestrator commits the records on `run/2026-10-09-db-final` (`mechanical_dup_merge/` is ignored:
  `git add -f`; the card_stats tree and `$DRV` are not ignored; `$RUN` is ignored and stays local), as
  part A did: per wave `PAIRS.json`, `move/` and `retire/` `{APPLY.sql,HELD.jsonl,PLAN.jsonl,PLAN.md,
  READ.jsonl,ROLLBACK.sql,evidence/}`, the card_stats wave's `{BASIS.json,PLAN.md,ROLLBACK.sql,
  SKIPPED.jsonl,evidence/}`, and `$DRV`. The card_stats `ROLLBACK.sql` carries premise digests that gitleaks
  reports (13 on 2026-11-10): they are triaged in `.gitleaksignore` before any push to main. The driver
  does not push.

## 5. Code that is missing or must change

| id | gap | files | size | blocks |
|---|---|---|---|---|
| G0 | The Fable switch (D153, D154) is in the working tree, uncommitted: the registry, the recorder and the identity import's standing gate (`check_calibrated` asks `roles.owner_standing`). Without it the briefs name another model, `answer --role` refuses and the import demands `--calibration`. | `scripts/remediation/roles.py`, `opus_handoff.py`, `calibrate_claude.py`, `identity/label_rounds.py` (another agent, in progress) | S | steps 3 to 6 |
| G1 | **Built on `build/track-b` (commit `049f052`); every command of it is available after the merge of build/track-b.** The move lane moves `wiki_images.site_id`, and every reader builds the served path from the site's id (`api/routes/wiki_images.py`, `api/routes/sites_html.py`, `pipeline/static_exporter.py`): a moved row's file has to be in the survivor's folder. What exists: `plan-move --write` and `plan-retire --write` read `wiki_images.filename` and one read-only sha256 listing of the wave's folders (`DISK.json`); a row whose filename the survivor's folder uses for another picture stays on the loser (`images_stay_filename`; a row of the survivor names it, or the folder holds other bytes under it - the folder is asked, not only the rows), and the retirement no longer holds a loser for such a row; a row whose file is not in the loser's folder holds its pair; the move plan writes `FILES.jsonl`. Commands: `$PY scripts/remediation/mechanical/dup_merge.py files --wave $W --copy` (copies on the VPS, never moves, never overwrites, reads every file back by its sha256), `... files --wave $W --verify` (read-only, exit 0 only when every picture is in place), `... files --wave $W --served` (after the apply: HTTP 200 for each). `apply.py --lane dup-merge-move-$W --apply` refuses before the write while a picture is not in place. No cell was added to the lane: `mechanical/lane.py` is unchanged, and no filename is ever rewritten. Tests in `tests/remediation/test_mechanical_dup_merge.py` (the 7 tests that run the copy script need a POSIX file system: they skip under Git Bash on Windows, where `mkdir -m 777` fails, and run under pytest on the workstation when the `bash` first on PATH is the WSL launcher, as in a fresh PowerShell: 176 passed, 0 skipped on 2026-11-10; the file asks no shell while it is collected; no CI run has seen them yet); 50 mutation-sweep cases, all fired (`identity/mutation_sweep_merge.py`: 47 labelled `files:`, 3 `apply:` ones for the gate). As built after the review of 2026-11-10: `DISK.json` is written with the plan, so a refused re-plan leaves the applied plan's listing; a read that lacks a folder of the wave fails instead of reading as an empty folder; `files --verify` and the apply's gate are pinned for a taken destination and a changed source, `plan-retire --write` end to end. **Not proven: `files --copy` has never run against the VPS** (a builder writes nothing there); the listing it rests on has (272 folders, 4,113 files, 10 s). The first wave's 9.3 is its first real run: read `00a_files-copy.txt` and `00b_files-verify.txt` whole. | `scripts/remediation/mechanical/dup_merge.py`, `mechanical/apply.py`, `tests/remediation/test_mechanical_dup_merge.py`, `identity/mutation_sweep_merge.py` | built | steps 9.2 to 9.5; without the merge, step 9.3 stops every wave whose plan has `images` > 0: Tarxien and Dodona (40 images), and on today's data most new merges |
| G2 | **Built on `build/track-b` (commit `049f052`); available after the merge of build/track-b.** `dup_clusters.py` lists a retired loser when it holds an image, a link or a name that is no name row of its survivor (`name_is_alias_on_survivor` false), each with `"holds"` saying which, and counts them in `retired_losers_holding_name`; `dup_judge.py decisions` writes that list into the pair's `why` (`... still on it: name`). Command: `$PY scripts/remediation/identity/dup_clusters.py` (step 2, or its one allowed re-run). Run on the export of 2026-11-05 it listed 24 losers, Caparra among them, and left the 90 cluster records as they were. | `scripts/remediation/identity/dup_clusters.py`, `identity/dup_judge.py`, `tests/remediation/test_identity_dups.py`, `test_identity_dup_judge.py`, `identity/mutation_sweep.py` | built | Caparra only. It must be in the tree when step 2 runs `dup_clusters.py`, or come in through the one re-run of step 2 before step 7; after step 7 Caparra is out of this pass |
| G3 | **Built on `build/track-b` (commit `049f052`); available after the merge of build/track-b.** The retirement's guard probe (`apply.neighbour_of`) asks the planned losers in plan order for another shown curated site within 2,000 m, takes the first that has one and corrupts that loser's `scope_reason` cell (next to another loser the neighbour would be far, and the distance check would refuse the probe first); it refuses only when no planned loser has a neighbour: `REFUSED: none of the <n> planned site(s) has another curated shown site within 2000 m`. Command, unchanged: `$PY scripts/remediation/mechanical/apply.py --lane dup-merge-retire-$W --probe-guards`. The test is `tests/remediation/test_mechanical_dup_merge.py` (`TestTheDecidedSurvivorInvariant`, where the lane's neighbour tests already were), not `test_mechanical_dups.py`. | `scripts/remediation/mechanical/apply.py`, `tests/remediation/test_mechanical_dup_merge.py`, `identity/mutation_sweep_merge.py` | built | step 9.6 (`--probe-guards` of the retirement), found early by pre-flight 9.1; left: a wave in which no loser has a neighbour (148 of the 225 cluster members have one) |
| G4 | **Built 2026-11-12 (O24), commit `3464223`.** The move's guard probe takes the row of a non-curated site it corrupts guard 1 with from the table of the plan's first line (`apply.cmd_probe_guards`, `rowlane.foreign_row(lane, records[0].table)`). `site_content_links` holds no row of a non-curated site (0 on 2026-11-10; `wiki_images` 2, `unified_site_names` 1.76 million), so a plan whose first cell is a content link is refused: `REFUSED: no site_content_links row of a non-curated site to probe the source guard with`. Part A passed because its first cell was a name row. Now: the plan's tables are asked in plan order and the first with such a row answers; refused only when none has one. | `scripts/remediation/mechanical/apply.py`, `mechanical/rowlane.py`, `tests/remediation/test_mechanical_rowlane.py` | built | step 9.4 (`--probe-guards` of a move whose first planned pair moves no image but a content link; 11 of part A's 16 moved pairs were of that kind), found before the emit by the pre-check of 9.2 |
| G5 | **Built on `build/track-b` (commit `b3ed4ec`); available after the merge of build/track-b.** O14: a pair beyond 2,000 m is merged only when verdict and re-check both call it the same site with quoted evidence, else held and listed. Before, `decide_verdict` held every such MERGE unless `OVERRIDES.json` existed, so the re-check (which asks only decided clusters) never read the pair. Now the distance alone holds nothing: the verdict decides the MERGE on its found quotes, the re-check is asked it, and only its CONFIRM with a found quote makes the merge; the pair carries its own distance as its limit (`metres_limit`, measured as the lanes measure it, which the plans and the retirement's survivor check read per loser). `OVERRIDES.json` is still read when someone hands one in (a limit with a quote of its own; one that does not carry holds the member), and the driver never writes it. No prompt text changed: rule 5 of the verdict prompt still tells the agent that such a merge "is held for the owner's decision whatever you answer", which is no longer what happens; rewording it voids every answer of a round exported before, so it is the orchestrator's call and only while no verdict round is open. | `scripts/remediation/identity/dup_judge.py`, `tests/remediation/test_identity_dup_judge.py`, `identity/mutation_sweep_merge.py` | built | steps 3, 4 and 7 for the clusters with a MERGE beyond 2,000 m (expected: Engomi Ancient City Ruins / Enkomi at 2,058 m, Kilmartin Glen records up to 2,217 m). It must be in the tree at the import of a verdict round that answers the cluster |

Not gaps: the 301 of a retired duplicate (`api/routes/sites_html.py`, live: Olympos Ruins and Tarxien
Temples answered 301 to their survivors on 2026-11-10); the lanes `dup-merge-move-<wave>` and
`dup-merge-retire-<wave>` (`mechanical/lane.py`, resolved by `apply.py`); `waves --exclude`.

None of G1 to G5 takes a model answer. G1, G2 and G3 are one commit (`049f052` on `build/track-b`, built
2026-11-10 in the worktree `.worktrees/build-b`), G5 and the review fixes of G1 the commit after it (`b3ed4ec`): none
of them is in the main checkout until the orchestrator merges that branch. Neither commit changes a
prompt text (`dup_judge.py`: one line of `decisions`, the distance rule of `decide_verdict` and the
docstring), so an open round's answers still import after the merge; G2 takes effect
at the next `dup_clusters.py` (step 2 or its one allowed re-run), G5 at the next import of a verdict
round. G4 is still open. Without the merge
step 9 stops at the gate that names the gap, and nothing is half-written as long as the gates 9.1 to 9.3
are read before the move's emit.

What the build decided, for the record: a row whose filename is taken stays on the loser and is not
renamed (the other way named on 2026-11-10 - copy under a free name and journal the row's `filename` -
was not built); the folder on the VPS is read at plan time, so the plan and not the copy decides what
stays; the apply itself asks for the pictures.

## 6. What can go wrong, and the check that catches it

| what | caught by |
|---|---|
| The basis moves between an export and its import (someone re-ran `export.py`) | the probe of section 3 shows another export basis; the import refuses with `stale: the answer names prompt ...` (`opus_handoff.py validate` stays green: it compares with the handoff's own prompt files). Rule 1. |
| `dup_clusters.py` re-run on another export | a cluster with changed members has a new id: `decisions` shows it `unanswered` again (step 7 lists it in `OPEN_CLUSTERS.jsonl`), and an export that re-asks its old label stops with a `KeyError`. Rule 1; the hash check of step 2 for the one allowed re-run |
| Wikimedia throttles (403, 429) or the network drops at an import, and good quotes do not count | the page is kept as failed for the whole stage; `held_reasons` of the import, the held list of step 3, `curl` on the URL; lower the width; the re-ask cites another page |
| An answer under the wrong role, model or a MiniMax stamp | the import stops with `RoundError`, nothing written |
| A survivor picked by age or by count | the recheck's RETARGET holds the member; rule 3 of the prompt |
| A false MERGE | the recheck (REJECT), the pilot judge on the first ten clusters, the 2,000 m limit, the spot check of step 7, the rehearsal |
| A MERGE beyond 2,000 m | after the merge of build/track-b (G5, O14): merged only when the verdict's quotes are found and the re-check CONFIRMs it with a found quote, else held with both readers' reasons (`HELD_LIST.jsonl`); the pair's limit is its own distance, so the plans hold it if the two rows have moved further apart since (`the two rows are <n> m apart; the pair's limit is <m> m`); each is named in the report (step 7). Before the merge: held by `decide_verdict` in every round |
| An image row moved without its file, or onto another picture's filename | after the merge of build/track-b: the plan keeps a row whose filename is taken on the loser (9.2), `files --verify` (gate 9.3), the apply's own refusal `<n> picture(s) of the moved image rows are not in place` (9.4), `files --served` and the driver's served-image read-back (9.4); before the merge only gate 9.3's stop and that read-back |
| A folder changes between the plan and the copy (a file added, replaced or removed) | `files --copy` refuses with nothing copied (`the image folders are not as the plan read them`); plan again |
| A copy stops half-way (ssh drop, full disk on the VPS) | the copy is written under `<file>.d14-part` and renamed when whole; every file is read back by its sha256; `files --copy` again finishes it; a left-over `.d14-part` is reported, never deleted by hand |
| The move's probe has no foreign row for the plan's first table | the pre-check of 9.2; gap G4; exit 1 at `--probe-guards`, nothing written |
| The first image move and the first `dup-merge-retire` write on production behave unlike part A | their rehearsal and probe files read whole before each apply; `curated sites with more than one live hero` = 0; the read-back of 9.4 |
| A plan run again after its apply | refused, but `READ.jsonl` is overwritten (`DISK.json`, `FILES.jsonl` and the plan stay the applied plan's): rule 4, the journal read before every plan |
| A second live hero on a survivor | the plan demotes it; row invariant inside the transaction; `curated sites with more than one live hero` = 0 |
| A loser retired while it still holds something the survivor lacks, or onto an imageless survivor | `plan-retire` holds it (`_complete`); the retirement's premise (guard 5) |
| A site changed between plan and apply (another lane wrote it) | guards 3 and 5 refuse inside the transaction: exit 1 or 3, nothing written; plan again |
| psql timeout, ssh drop | exit 5 and the journal count; rule 4 |
| The retirement's probe has no neighbour | after the merge of build/track-b the probe takes the first planned loser that has one (G3); pre-flight 9.1 says whether any loser of the wave has; a wave in which none has is refused at `--probe-guards` |
| A wave moved but not retired | the journal recount of 9.7 shows a move stamp without its retire stamp although the wave's `PAIRS.json` holds a pair with `already_retired` false: report at once |
| A Lyra restart after the move (a deploy) re-inserts the loser's label row | only a reversal is affected (`uq_usn`): rule 7; the forward state is right |
| Two card_stats waves at once, or an input moved after the export | `card_stats.py --write` refuses (basis, counterfactual); guard 5; one slot over all lanes |
| The static export killed by a deploy, or a retired loser still in `index.json` | `rebuild_static` exit 1; `static_export_check.py` exit 1 |
| Stories, paper links, likes left on a retired loser | the counts of 10.5 in the report |
| D25 loses the PART_OF list | `$DRV/DUP_DECISIONS.final.jsonl`; hand-off note of 10.6 |
| cp1252 crash, a full disk | `PYTHONIOENCODING=utf-8` in the frame; `df -h /c` before every step |

## 7. Population and estimate

Population (export of 2026-11-05, unchanged in production on 2026-11-10): 90 clusters with 225 shown
records (73 of 2, 9 of 3, 2 of 4, 1 of 5, 2 of 6, 2 of 8, 1 of 11); 58 clusters within 200 m, 22 within
2 km, 5 within 20 km, 5 beyond; 38 clusters carry an owner-case PART-OF pair. 212 of the 225 records have a
card text. Plus the retired losers: 23 listed (21 of part A, where only URL collisions remain, Tarxien,
Dodona) and Caparra with G2. The retired losers take no answer.

An answer is one cluster question answered by one agent. What is fixed and what is assumed:

| stage | role, effort | questions | batches | how the number is made |
|---|---|---|---|---|
| dup-verdict r1 | web_verifier, high | 90 | 18 | one per cluster: exact |
| dup-verdict r2, r3 | web_verifier, high | about 14 + 4 | 3 + 1 | assumed: 15 % of r1 held (quotes, shape; on a tree without G5 also the 2 merges beyond 2,000 m), 30 % of those again |
| dup-recheck r1 | pilot_judge xhigh (10), adversarial high (about 50) | about 60 | 12 | the decided clusters with a MERGE or PART_OF: of about 76 decided, the 8 far-apart clusters and about 8 neighbours come back without a relation |
| dup-recheck r2, r3 | adversarial, high | about 8 + 2 | 2 + 1 | assumed: 13 % held, 25 % of those again |
| **total** | all `claude-fable-5-2`, all with web research | **178, about 180 answers (D144)** | **37 batches** | bounds: 90 at least, 540 at most (3 rounds of 90 in both stages) |
| spot check | one agent, high, no handoff answer | 10 merges | 1 | not an answer of the count |

No round of this stage has been imported before, so the held rates are assumptions, not measurements: the
count of section 3 is read after every export. Stop rule (D151): more than 225 recorded answers (25 %
above the estimate) stops the block for a report. After the import of `dup-verdict` r1 and of
`dup-recheck` r1, write the projection into `NOTES.md` (answers recorded, plus the held clusters of the
round, plus for the verdict stage the decided clusters with a relation) and tell the orchestrator when it
passes 225, before the next export.

Expected result: 25 to 40 new merges (50 to 80 sites in one wave, a second wave for the rest of the
retired-loser records), 35 to 45 PART_OF members for D25, 5 to 10 WRONG_ID records, up to 10 clusters held.
Wall time at web width 3: about 3 h verdict, 2.5 h recheck, 1.5 h re-asks, 2 h write, 1 h after-steps; at
width 1 about twice that for the answering.

## 8. Reversal

Not a driver step (rule 7). For the record: `psql < retire/ROLLBACK.sql`, then `psql < move/ROLLBACK.sql`,
each an explicit decision of the orchestrator; the move's reversal refuses while the loser is retired
(guard 5), and after a Lyra restart it stops at `uq_usn` until the label row Lyra's boot re-inserted for
the loser is removed. Copied image files stay in the survivor's folder (they are served by no row after a
reversal). A card_stats wave is not undone from its file once any input moved; the next wave recomputes.

## 9. What D1-D156 left open (none blocks the lane)

Items 1 to 3 were decided by the orchestrator under the owner's AFK mandate of 2026-11-10 as **O14**
(`output/remediation/OWNER_DECISIONS_2026-10-08.md`); the owner may overturn it. Item 4 is not decided.

1. Decided (O14): Tarxien and Dodona are not swapped (section 1), against the plan of 2026-10-08
   (`plans/identity.md` 3.1) and O5's expectation; the pictures move to the present survivors. A swap
   would need code no lane has (un-retire a `duplicate_of:` row, retire the other record, carry the card
   text and the name rows). "Archaeological Site of Dodoni" is not in lane D23's name triage, so it keeps
   that name unless the owner asks for "Dodona".
2. Decided (O14): a pair beyond 2,000 m (expected: Engomi Ancient City Ruins / Enkomi at 2,058 m,
   Kilmartin Glen records up to 2,217 m) is merged only when verdict and re-check both call it the same
   site with quoted evidence, else held and listed. Built as G5 on build/track-b: no
   `$RUN/dup/OVERRIDES.json` is needed or written; on a tree without G5 these merges stay held (step 3).
   The merged ones are named in the lane report (step 7), the held ones are in `HELD_LIST.jsonl`.
3. Decided (O14): stories (`news_items.site_id`, 92 rows on the 225 cluster records), paper links (4),
   proposals (46), one like, one bookmark, one collected card and the 225 `research_nodes` rows are not
   moved by any lane; they stay on the retired loser, whose URL redirects to the survivor, and are
   counted in the final report (the counts of 10.5). Moving them would need new cells in the row lane.
4. Not decided: the move's journal rows name the loser (`site_id_ref`), so the sitemap `lastmod` and the
   hourly IndexNow cycle do not move for a survivor that gains pictures and links; the loser's retirement
   is announced. Nothing in this lane moves a survivor's `lastmod`.
