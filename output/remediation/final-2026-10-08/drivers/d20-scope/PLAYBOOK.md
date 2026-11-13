# D20 scope review - driver playbook

State measured read-only on 2026-11-10, 19:50 UTC (production and the main checkout
`C:/PythonProjects/AncientMap`, branch `run/2026-10-09-db-final`). Decisions that bind this lane:
D20 (check and retire autonomously; a wrong period is corrected, sourced), D58 (the label rule is the
window), X13 (Islamic and Byzantine Europe dated 500-1500 is medieval Europe: outside the window),
D138 (done: Caus Castle and Ayazini Kaya Church retired, wave `2026-11-07`), D146 (D20 with the 5
pending rows belongs to the close-out), D151 (the order: after D14 B, before D23/D25 and D13; a short
report per block; stop when the block costs more than 25 % above its estimate or a spot check is bad),
D153 (every role answers on `claude-fable-5-2`), D154 (no calibration, seal, verdict or release step),
D155 (no weekly cap; the answers are still counted), D156 (no owner gate in this lane), D135 (stop and
report below 10 GB free on C:), D8 (every write journalled, rehearsed, its rollback rehearsed, accepted
with 0 deviations).

The label rule: only the medieval Old World of Europe, Byzantium (Cyprus) and the Vikings ends at
500 AD. Every other region keeps its sites through 1500 AD. A site dated 500-1500 in Anatolia, the
Levant, Egypt, Byzantine Africa, the Caucasus or Greenland stays unless its subject is Byzantine,
Crusader or Norse.

## 1. Where the lane stands

| thing | state |
| --- | --- |
| Question rounds of D20 | none. `identity/scope-window/` does not exist; `status` of both stages prints `"rounds": []` |
| Answers recorded, imported | 0, 0 |
| Waves selected or planned for D20 | none |
| Discovery file `identity/SCOPE_WINDOW.jsonl` | stale: written 2026-10-08 under the old numeric rule, 130 rows, no `label_borderline` group. Unusable. No tool refuses it: S1 replaces it and S2 proves that |
| Discovery file `identity/EXPORT.jsonl` | production read of 2026-11-05 22:31 UTC (4,909 shown). Too old |
| `identity-2026-10-08/`, `identity-2026-10-24/` | old copies of the discovery (130 and 69 rows). Never read by the tools. Do not use |
| Calibration `ident-scope-window-1` | unfinished, no verdict. Dropped by D154. Do not touch |
| Lane `scope-window-2026-11-07` | written (D138, 2 sites, 4 journal rows). That label is used up |
| Roles | `web_verifier` and `adversarial`: `claude-fable-5-2`, effort high, standing `owner decision D153` (read from `roles.py` in the working tree) |
| Backup and restore drill of 2026-11-10 | passed (`backups/2026-11-10_remediation/DRILL_REPORT.txt`) |
| Disk C: | 30 GB free |

Production today:

| count | value |
| --- | --- |
| curated sites | 5,004 |
| `scope_status` NULL / `pending` / `in_scope` / `retired` | 4,876 / 5 / 26 / 97 |
| shown (not retired) | 4,907 |
| shown outside the D58 window | 68 (51 undecided, 1 pending, 16 `in_scope`) |
| of those, the five sites of X13 (Islamic and Byzantine Europe) | 5 (Huéscar, Ponferrada, Ponte de Rubiães, Ruins of Talamanca, Villaggio Bizantino). Asked like any European site after the merge of build/track-b; held out of the population by the code before it |
| shown label-borderline | 2 (Nimrod Fortress, Comer's Midden) |
| pending | 5 (Chacamarca Historic Sanctuary, Situs Megalit Tebing Tinggi, Northern Avenue Petroglyph Site, Keno Daas Rock Carvings, Church of the Holy Apostles Peter and Paul in Ras; only the last is outside the window) |
| Hadrian's Wall Path (`360a4afb`) | shown, dated 2003, undecided, inside the 63 |
| **D20 population the discovery will build** | **74** after the merge of build/track-b = 68 outside the window + 2 borderline + 4 pending inside the window. **69** on code without the merge (63 outside the window: the five X13 sites are held out) |
| museums in the population | 21 (16 already `in_scope`, 5 undecided) |
| regions of the 69 | 41 medieval Old World (cutoff 500), 18 Americas, 10 rest of the world (cutoff 1500) |

The plan of 2026-10-08 counted 131 sites: 127 outside the numeric window, the pending ones and
Hadrian's Wall Path. The period re-research of October took the 127 to 83, the label rule D58 to 68.
Code without build/track-b holds 5 of the 68 out (gap G1, closed on that branch): the population
is 74 after the merge and 69 before it. The counts of 69 below (S1 to S3, section 10) are the
pre-merge ones; after the merge read 74 sites, 15 batches in r1.

## 2. Header of every shell call

The working directory and the shell variables reset between calls. Start every call with this block.

```bash
cd /c/PythonProjects/AncientMap
export PYTHONIOENCODING=utf-8
PY=./.venv/Scripts/python.exe
I=scripts/remediation/identity
H=scripts/remediation/opus_handoff.py
A=scripts/remediation/mechanical/apply.py
RUN=output/remediation/final-2026-10-08/identity
LANE=$RUN/scope-window
WEB=$LANE/scope-window-web
RECHECK=$LANE/scope-window-recheck
HO=output/remediation/handoff/d20-scope-window
DRV=output/remediation/final-2026-10-08/drivers/d20-scope
mkdir -p $DRV/briefs $DRV/tools
W=$(cat $DRV/WAVE_LABEL 2>/dev/null)     # the wave label, empty until S12 chose it
```

Every tool prints `REFUSED: <reason>` on stderr and exits 1 when it will not do what was asked. A
refusal has written nothing. The tools also print one log line (`Logging configured`) on stderr;
stdout is clean JSON. Discard stderr only on read-only commands, never on a step that changes state.

Keep a log `$DRV/NOTES.md`: one dated line per step with the counts the step printed.

## 3. Rules for the answering agents

- One new agent per batch. Never reuse an agent for a second batch. The driver never answers itself.
- Model `claude-fable-5-2`, effort high, web research on. An agent on another model would record a
  false stamp.
- Working directory of the agent: `C:/PythonProjects/AncientMap`.
- The agent's instruction is the brief file, verbatim, plus these three lines:
  `Do not cite web.archive.org or archive.ph: the machine cannot fetch them from here.`
  `Do not quote whc.unesco.org, megalithic.co.uk, britainexpress.com, hmdb.org or atlasobscura.com: they refuse the machine's fetch (403).`
  `A 403 or 429 from a server is no finding: cite another page.`
- A re-ask round (r2, r3) adds two more lines:
  `A page your prompt names after "fetch failed" is never fetched again: quote another page.`
  `After "not found" the page was read and your quote was not in its text: quote word for word, or quote another page.`
- Both stages are web research. At most 3 web agents run at once over all lanes together. Use only
  the slots the orchestrator grants. An `import` fetches pages itself: count it as one slot.
- An agent that stops mid-batch leaves questions open. Launch a new agent with the same brief and
  the added line `Only these labels are open: <labels>. Record with --answered-by <batch>b.`

## 4. Steps

### S0 Preflight (read-only)

```bash
$PY -c "
import sys; sys.path[:0]=['.','scripts/remediation']
import roles
for r in ('web_verifier','adversarial'): print(r, roles.role(r).model, roles.role(r).effort, roles.owner_standing(r))"
$PY $I/run.py --lane scope-window import --help 2>/dev/null | grep -c '\[--calibration CALIBRATION\]'
test -s output/remediation/final-2026-10-08/wiki_cache/INDEX.jsonl && echo cache-ok
$PY $A --lane scope-window-$(date -u +%F) --verify 2>/dev/null | grep -E "scope_status|label window|curated sites"
df -h /c | tail -1
git rev-parse --short HEAD; git status --short scripts/remediation/identity scripts/remediation/mechanical scripts/remediation/opus_audit scripts/remediation/roles.py scripts/remediation/opus_handoff.py scripts/remediation/web_rules.py
```

Pass when: both roles print `claude-fable-5-2 high` and a dict with `'owner_decision': 'D153'`; the
`grep -c` prints 1; `cache-ok`; the scope counts print (on 2026-11-10: 4876 NULL, 5 pending,
26 in_scope, 97 retired, residual 51; a D14 B wave since then moves NULL and retired by its
retirements); `Avail` is 10 GB or more (D135: below that, stop and report). Write the commit and the
`git status` lines into NOTES.md: they are the code this run answers and writes with.

If a command fails at import (another agent edits `roles.py`, `opus_handoff.py` and the gates):
write the error into NOTES.md, wait 10 minutes, try again. Never edit code.

Where the lane stands (run it at every start and after every interruption):

```bash
for s in scope-window-web scope-window-recheck; do
  $PY $I/run.py --lane scope-window status --stage $s 2>/dev/null | tr -d '\n '; echo
  echo "imported: $(ls $LANE/$s/answers 2>/dev/null | tr '\n' ' ')"
done
echo "waves: $(ls $LANE/waves 2>/dev/null | tr '\n' ' ')"
for d in output/remediation/mechanical_scope_window/*/; do echo "$d $(ls $d | tr '\n' ' ')"; done
```

| the probe shows | go to |
| --- | --- |
| both stages `"rounds":[]` | S1 |
| web: newest round not under `imported` | S3 for that round, then S4 |
| web: newest round imported, `"held"` above 0 | S5 |
| web: newest round imported, `"held"` 0 or the re-asks used up; re-check `"rounds":[]` | S6 |
| re-check: newest round not under `imported` | S7 |
| re-check: newest round imported, `"held"` above 0 | S8 |
| both stages finished, no wave | S9 |
| a wave under `waves`, no `PLAN.jsonl` in its `mechanical_scope_window/<W>/` | S13 |
| `PLAN.jsonl` and no `APPLY.sql` | S13 again (a fresh plan), then S14 |
| `APPLY.sql` | the recount of S15 first. 0 rows: the wave was emitted and not written; report. Rows: S15 onward |

### S1 Fresh discovery

Read the state:

```bash
$PY -c "import json;c=json.load(open('$RUN/COUNTS.json',encoding='utf-8'));print(c['export']['exported_at'],c['scope_window'])"
$PY - <<'EOF'
import json, pathlib
run = pathlib.Path("output/remediation/final-2026-10-08/identity")
for f in sorted(run.rglob("ROUNDS.jsonl")):
    if "calibration" in f.parts:
        continue
    rows = [json.loads(x) for x in f.read_text(encoding="utf-8").splitlines() if x.strip()]
    name = rows[-1].get("name") or "r%s" % rows[-1]["round"]
    done = (f.parent / "answers" / (name + ".jsonl")).exists()
    print(f.parent.as_posix(), name, "imported" if done else "OPEN")
EOF
ls -d $RUN/dup $RUN/parent $RUN/names $RUN/retarget 2>/dev/null
```

`export.py` replaces `$RUN/EXPORT.jsonl`, which every identity lane reads (D14 B `dup/`, D25
`parent/`, D23 `names/`, D13 `retarget/`). It may run only when all three hold:

1. The second command prints no line `OPEN`. An open round of another lane carries the export's
   clock in its prompts.
2. D14 B is not in its frozen window. Its driver forbids `export.py` from its first exported round
   until its last wave is planned. `$RUN/dup` absent, or the orchestrator has reported D14 B's last
   wave accepted: free. Otherwise frozen.
3. `$RUN/parent`, `$RUN/names` and `$RUN/retarget` are absent (D23/D25 and D13 start after this
   lane's report, D151).

When one fails: do not run `export.py`. With condition 2 alone failing and an `exported_at` less than
24 hours old, keep the export D14 B's driver wrote and run only `scope_window.py` (a site that
changed since that export is skipped by the plan as `entry-moved`). In every other case: report to
the orchestrator and wait.

Run (skip `export.py` also when `exported_at` is less than 6 hours old):

```bash
mkdir -p $DRV/basis-before && cp -n $RUN/EXPORT.jsonl $RUN/SCOPE_WINDOW.jsonl $RUN/COUNTS.json $DRV/basis-before/
$PY $I/export.py
$PY $I/scope_window.py
```

- The copy keeps the three files this step replaces (about 8 MB; `-n` never overwrites a kept copy).
- `export.py` reads production once (read-only transaction) and replaces `$RUN/EXPORT.jsonl`.
  Done: exit 0, it prints the counts with `'shown': 49xx` and today's `exported_at`.
- `scope_window.py` replaces `$RUN/SCOPE_WINDOW.jsonl`. Done: exit 0, it prints the counts.
  Available after the merge of build/track-b: it builds the discovery also after a wave retired
  Hadrian's Wall Path (the group `hadrians_wall_path` is then absent from the counts). On code
  without the merge it ends with `IdentityError ... is not one shown site named "Hadrian's Wall
  Path"` once that site is retired, and the discovery can be built only before the first wave.
- No agents. About 2 minutes.

Check the printed `scope_window` counts. After the merge of build/track-b: `population` 74,
`group_outside_window` 68, `group_label_borderline` 2, `group_pending` 5,
`group_hadrians_wall_path` 1, `museum_question` 21, and no key `held_label_open_question` (X13 is
in the code: the five sites are asked in r1, 15 batches, and S19 falls away). On code without the
merge: `population` 69, `group_outside_window` 63 and `held_label_open_question` 5 (gap G1 open,
section 7). A population more than 5 away from the expected one without a known write since
2026-11-10: stop and report.

Tell the orchestrator whether `EXPORT.jsonl` was refreshed: the other identity lanes must rebuild
their own discovery files from a refreshed export before they export a round.

### S2 Export the web round r1

Run it right after S1. Read the state:

```bash
$PY $I/run.py --lane scope-window status --stage scope-window-web 2>/dev/null | grep rounds
ls $HO-web-r1 2>&1 | head -1
[ $RUN/SCOPE_WINDOW.jsonl -nt $RUN/EXPORT.jsonl ] && echo discovery-fresh
wc -l < $RUN/SCOPE_WINDOW.jsonl; grep -c label_borderline $RUN/SCOPE_WINDOW.jsonl
```

Pass when: `"rounds": []`; `ls` fails; `discovery-fresh`; the line count is S1's `population` (69);
the `grep -c` is S1's `group_label_borderline` (2). The stale file of 2026-10-08 prints no
`discovery-fresh`, 130 and 0.

```bash
$PY $I/run.py --lane scope-window export --stage scope-window-web --handoff $HO-web-r1
```

Produces `$HO-web-r1/r1-b01 ... r1-b14` (each with `MANIFEST.jsonl` and
`scope-window-web/<site id>.prompt.txt`), `$WEB/ROUNDS.jsonl`, `$WEB/contexts/r1.jsonl`. Done: it
prints `"round": "r1", "sites": 69, "batches": 14`. Refused when the handoff directory is not empty.
No agents.

The prompt probe (read-only). It renders every question of a round again and compares it with the
exported prompt. Run it now, and again before every import (`STAGE=web` or `recheck`, `ROUND=r1`,
`r2`, `r3`):

```bash
STAGE=web ROUND=r1 $PY - <<'EOF'
import os, sys
sys.path[:0] = ["scripts/remediation", "."]
from pathlib import Path
import opus_handoff as OH
from identity import common, rounds as R, scope_judge as SJ
spec = SJ.web_spec() if os.environ["STAGE"] == "web" else SJ.recheck_spec()
out, name = R.stage_dir(common.run_dir(), spec), os.environ["ROUND"]
rec, ctx, bad, n = R.find_round(out, name), R.load_contexts(out), 0, 0
for batch, sids in rec.batches.items():
    man = OH.read_manifest(Path(rec.handoff), batch)
    for s in sids:
        n += 1
        bad += OH.prompt_sha256(spec.render(ctx[s], rec.earlier.get(s))) != man[(spec.stage, s)]["prompt_sha256"]
print(name, "questions", n, "drifted", bad)
EOF
```

`drifted 0`: go on. Above 0: the prompt code changed after the export (another agent's edit); the
import would refuse every such answer as stale. Stop and report before any agent answers.

### S3 Answer the web round r1

- Role `web_verifier`, `claude-fable-5-2`, effort high, web research, 5 questions per batch,
  14 batches (13 of 5, one of 4), 69 answers.
- Brief per batch (the batch ids are the directory names of the handoff):

```bash
for b in $(ls $HO-web-r1 | grep '^r1-b'); do
  $PY $I/run.py --lane scope-window brief --stage scope-window-web --round r1 --batch-id $b 2>/dev/null > $DRV/briefs/web-$b.txt
  test -s $DRV/briefs/web-$b.txt || echo "no brief for $b"
done
```

- Launch one agent per brief (section 3). The brief tells the agent to run `check-answer` and
  `opus_handoff.py answer --role web_verifier --model claude-fable-5-2` for each question.
- Done: `$PY $H validate --dir $HO-web-r1` exits 0 and prints `"ok": true, "answered": 69`.
  Exit 1 lists `missing`, `stale`, `malformed`, `orphans`. Missing: a new agent for those labels.
  Malformed or stale: delete that answer file
  (`$HO-web-r1/<batch>/scope-window-web/<site id>.answer.json`) and have it answered by a new agent.
  Orphan: an answer file no question asked for; delete it.

### S4 Import the web round r1

Read the state: `ls $WEB/answers/r1.jsonl` fails (not imported yet), S3's validate is ok, the
prompt probe of S2 prints `drifted 0`, and the network answers:

```bash
curl -s -o /dev/null -w '%{http_code}\n' -A "AncientNerdsSiteAudit/1.0 (https://ancientnerds.com; database audit; ancient.nerds@protonmail.com)" "https://en.wikipedia.org/wiki/Hadrian%27s_Wall_Path"
```

It must print 200. A 429 or 000: wait and try again before the import, and start no import while
3 web agents run. The import keeps every fetch, the failed ones too, and never fetches a kept URL
again in this stage: a quote on a page that failed once cannot count in a later round.

```bash
$PY $I/run.py --lane scope-window import --stage scope-window-web --round r1 > $DRV/web_import_r1.json; echo "exit=$?"; cat $DRV/web_import_r1.json
$PY -c "
import json, collections
from urllib.parse import urlsplit
rows = [json.loads(l) for l in open('$WEB/PAGES.jsonl', encoding='utf-8') if l.strip()]
bad = collections.Counter((urlsplit(r['url']).hostname, r.get('status')) for r in rows if r.get('status') != 200)
print(len(rows), 'pages, not fetched:', sum(bad.values()), bad.most_common(15))"
```

No `--calibration` (D154). The import fetches every cited page once (1 s pace per host) and looks
for every quote. Produces `$WEB/answers/r1.jsonl`, `$WEB/DECISIONS.jsonl`, `$WEB/PAGES.jsonl`,
`$WEB/TITLES.json`, `$WEB/pages/`. Done: `exit=0` and a JSON with `answers`, `decided`, `held`,
`held_reasons`, `"calibration": null`, `"standing": "owner decision D153 ..."`. No agents.

The second command lists the kept pages that were not fetched, by host and HTTP status (`None`: no
answer at all). Scattered 403 and 503 are normal (4 to 8 % of the pages in the earlier lanes: some
hosts refuse the machine); those answers are held and asked again. Stop and report before S5 when a
Wikimedia host (`*.wikipedia.org`, `www.wikidata.org`, `commons.wikimedia.org`) shows a page with
`429` or `None`, or when more than a tenth of all pages failed: a throttle or a network fault, and
those URLs stay failed for this stage.

Refusals and what to do:
- `does not validate`: back to S3.
- `answer(s) are not the stage's role's`: delete the named answer files, have them answered again
  by a new Fable agent, validate, import.
- `stale`: the prompt code changed since the export. Stop, report.
- `--calibration ID` demanded: the Fable switch is not in the code that ran. Stop, report (G3).

A held answer is one whose quote the machine did not find, whose page could not be fetched, or
whose shape is wrong (`held_reasons`: `quotes`, `shape`).

### S5 Web re-ask rounds r2 and r3

Read the state: `status --stage scope-window-web` prints `held`. `held` 0: go to S6.

```bash
$PY $I/run.py --lane scope-window export-reask --stage scope-window-web --handoff $HO-web-r2
```

Each prompt carries why the earlier answer was not counted. Then as S3 and S4 with `--round r2`,
the batch ids `r2-b01 ...`, the handoff `$HO-web-r2`, the brief files `$DRV/briefs/web-r2-b01.txt
...`, the two re-ask lines of section 3 and the output file `$DRV/web_import_r2.json`. If `held` is still above 0, once more with `$HO-web-r3`
and `--round r3`. Expected: about 9 answers in 2 batches, then about 3 in 1 batch.

Done when `held` is 0, or when `export-reask` is refused with `2 re-ask rounds are out`. What is
still held then stays held and goes to the owner list. Refused with `no question to ask`: nothing
is held.

### S6 Export the re-check round r1

Read the state: every web round is imported (`ls $WEB/answers/` lists each round of
`$WEB/ROUNDS.jsonl`), S5 is finished, `status --stage scope-window-recheck` prints `"rounds": []`.
A web round imported after this export would leave its retirements without a re-check until a
further `export` of this stage.

```bash
$PY $I/run.py --lane scope-window export --stage scope-window-recheck --handoff $HO-recheck-r1
```

It asks every decided web verdict that retires: `OUT_OF_WINDOW`, `NOT_A_SITE`, `MEDIEVAL_SUBJECT`.
Done: it prints `"round": "r1", "sites": N, "batches": ceil(N/5)`; expected N about 30.
Refused with `no question to ask`: no web verdict retires; go to S9.

### S7 Answer and import the re-check round r1

- Role `adversarial`, `claude-fable-5-2`, effort high, web research, 5 questions per batch,
  about 6 batches, about 30 answers. The reviewer answers `CONFIRM` or `REJECT`.

```bash
for b in $(ls $HO-recheck-r1 | grep '^r1-b'); do
  $PY $I/run.py --lane scope-window brief --stage scope-window-recheck --round r1 --batch-id $b 2>/dev/null > $DRV/briefs/recheck-$b.txt
  test -s $DRV/briefs/recheck-$b.txt || echo "no brief for $b"
done
# agents answer, then:
$PY $H validate --dir $HO-recheck-r1
# the prompt probe of S2 with STAGE=recheck ROUND=r1, and the curl of S4, then:
$PY $I/run.py --lane scope-window import --stage scope-window-recheck --round r1 > $DRV/recheck_import_r1.json; echo "exit=$?"; cat $DRV/recheck_import_r1.json
```

Done and refused exactly as S3 and S4, with `$RECHECK/answers/r1.jsonl` as the proof of the import
and `$RECHECK/PAGES.jsonl` for the status count.

### S8 Re-check re-ask rounds r2 and r3

As S5 with `--stage scope-window-recheck` and the handoffs `$HO-recheck-r2`, `$HO-recheck-r3`.
Expected: about 4 answers in 1 batch.

### S9 Result

```bash
$PY $I/run.py --lane scope-window result > $DRV/result_before_wave.json; echo "exit=$?"; cat $DRV/result_before_wave.json
```

Writes `$LANE/RESULT.jsonl`, `$LANE/OWNER_LIST.jsonl`, `$LANE/WAVE_SKIPS.jsonl`. It prints `asked`
(69) and `by_verdict_and_state`. States: `kept` (PERIOD_WRONG, MUSEUM_KEEP: written `in_scope`),
`confirmed` (a retirement the re-check confirmed: written `retired`), `rejected`, `held`,
`waiting-for-recheck` (these three are written nowhere and are on the owner list).

Go on only when no key ends in `:waiting-for-recheck`, or the re-check's two re-ask rounds are out.
No tool enforces this: a wave selected earlier leaves the waiting sites out for good.

### S10 The driver reads every retirement (the block's spot check)

```bash
$PY - <<'EOF' 2>/dev/null
import sys
sys.path[:0] = ["scripts/remediation", "."]
from identity import common, rounds as R, scope_judge as SJ
run = common.run_dir()
wd, rd = R.stage_dir(run, SJ.web_spec()), R.stage_dir(run, SJ.recheck_spec())
web, second, ctx = R.decisions_by_site(wd), R.decisions_by_site(rd), R.load_contexts(wd)
for row in SJ.final_state(web, second):
    if row["state"] != "confirmed":
        continue
    s = row["site_id"]; c = ctx[s]; d = web[s]["data"]
    q = next(x for x in d["quotes"] if x["outcome"] == "found")
    print("\n", s[:8], c["name"], "|", c["country"], "|", c["site_type"], "| status", c["scope_status"],
          "| cutoff", c["cutoff"], "| stored", c["date_used"], "|", row["verdict"],
          d["found_start"], d["kind"])
    print("  why:", d["why"]); print("  quote:", q["quote"], "-", q["url"])
    print("  re-check:", second[s]["data"]["why"])
EOF
```

Read each block. It is right when the quote is about this site at this place and states the date
past the cutoff (OUT_OF_WINDOW), that the place is no archaeological site (NOT_A_SITE), or the
Byzantine, Crusader or Norse subject (MEDIEVAL_SUBJECT). Read these twice:

- a site whose status is `in_scope` or `pending`: its retirement turns a decided page into a 410;
- a record of a town or village (type `City/town/settlement` or `Village`) and every record of D13's
  funnel of modern-town records (13 of the 69 in the funnel of 2026-10-08: Björkö, Clare, Frohnleiten,
  Furby, Giecz, Justinianopolis, Kłopot, Neuchâtel, Olmeto, Palma di Montechiaro, Pudliszki,
  Tarnowskie Góry, Yeavering). The retirement is right only when the answers name no older site at
  that point. Where they name one, the entry belongs to D13 (re-target), not to a retirement;
- Traditional Arts Museum (`2372d1b2`, Palmyra): it has no `site_type`, so the museum verdict is
  closed to it.

One retirement that is not right: stop before S12 and report the site. There is no tool that leaves
one site out of a wave, and a bad spot check stops the block (D151).

### S11 Backup and restore drill of the day

Read the state: `ssh ancientnerds 'tail -1 /var/www/ancientnerds/backups/$(date +%F)_remediation/DRILL_REPORT.txt'`.
It must print `VERDICT: dump is restorable and matches production row-for-row.` The nightly backup
of that directory runs without the drill, so the directory alone proves nothing. If the file is
missing:

```bash
ssh ancientnerds "cd /var/www/ancientnerds/scripts/remediation && DO_DRILL=1 ./00_backup_and_drill.sh"
```

Done: exit 0 and the VERDICT line. Any other end: no write today. The drill belongs to the UTC day
of the write: after midnight UTC, read the state again.

### S12 Select the wave

Choose the label once and keep it in a file:

```bash
C=$(date -u +%F)
test ! -e output/remediation/mechanical_scope_window/$C && test ! -e $LANE/waves/$C && echo free
ssh ancientnerds "docker exec ancient_nerds_db psql -U ancient_map -d ancient_map -At -c \"SELECT count(*) FROM remediation_change_log WHERE run_stamp = '${C}_mechanical-scope-window'\""
```

`free` and `0`: that is the label. Otherwise run the two checks again with `C=` the date with `b`
(then `c`) appended. `2026-11-07` is used. Then, with the label typed in:

```bash
C=YYYY-MM-DD                     # type the label that printed free and 0
echo $C > $DRV/WAVE_LABEL        # the header reads it into W from now on; a later wave overwrites it
$PY $I/run.py --lane scope-window wave --wave $C > $DRV/wave_$C.json; echo "exit=$?"; cat $DRV/wave_$C.json
```

Writes `$LANE/waves/$C/WAVE.json` with every `kept` and `confirmed` site (at most 100; the
population fits one wave). A wave is selected once, and a site belongs to the wave that took it.
Refused with `no site is left for a new wave`: nothing is kept or confirmed; go to S20.

### S13 Plan the wave

Run S13 to S15 in one go, within minutes: the plan holds the entry as production has it now. Ask the
orchestrator that no lane that writes a name, a type, a point, a country or a period (D14 B, the
field and period lanes) applies a step in that time.

Before the `plan` of any wave (read-only):

```bash
$PY scripts/remediation/mechanical/period_fix.py wave --help 2>/dev/null | grep -q -- '--d20' && echo d20-present
```

No `d20-present`: stop here and ask the orchestrator for the merge of build/track-b. S13 can wait:
the answers are imported and nothing is written before S14. A `plan` on code without the merge
writes `PERIOD_WRONG.jsonl` without the answer's stamp, and `period_fix.py wave --d20` refuses such
a file whole (S18). While the wave has no `APPLY.sql`, running S13 again on merged code writes the
hand-off with the stamp. Once S14 has emitted `APPLY.sql`, `plan` is refused and no command writes
the hand-off again: every corrected start of that wave goes to the owner list. Plan without the
merge only on the orchestrator's word, and name that in the report.

```bash
$PY $I/run.py --lane scope-window plan --wave $W > $DRV/plan_$W.json; echo "exit=$?"; cat $DRV/plan_$W.json
```

Reads production read-only. Writes `output/remediation/mechanical_scope_window/$W/PLAN.jsonl`,
`PLAN.md`, `ROLLBACK.sql`, `SKIPPED.jsonl`, and `$LANE/waves/$W/PERIOD_WRONG.jsonl` (the corrected
starts, section S18). It prints `sites`, `cells` (2 per site), one counter per transition
(`NULL->retired`, `NULL->in_scope`, `pending->in_scope`, `pending->retired`, `in_scope->retired`),
`skipped`, `period_wrong_handoffs`. Refused when `APPLY.sql` exists: an emitted plan is never
planned again.

Check:
- `cells` = 2 x `sites`.
- `skipped`: read `SKIPPED.jsonl`. `already-decided` (the 16 museums already `in_scope`) and
  `already-retired` are normal. `entry-moved` means another lane changed the site since S1: the
  site is not written by this wave. Available after the merge of build/track-b: step S16a asks it
  again and a later wave writes it. On code without the merge no tool asks it again and it goes to
  the owner list. The skip `label-open-question` does not exist after the merge (X13: an
  OUT_OF_WINDOW answer for a site of Spain, Portugal, Malta or Sicily is written like any other).
- The dangerous transitions, one line each; read their reasons in `PLAN.md` (the line of the site
  shows the old and the new `scope_reason`):

```bash
$PY -c "
import json
for l in open('output/remediation/mechanical_scope_window/$W/PLAN.jsonl', encoding='utf-8'):
    r = json.loads(l)
    if r['column'] == 'scope_status' and r['new_value'] == 'retired' and r['old_value'] in ('in_scope', 'pending'):
        print(r['old_value'], '-> retired |', r['site_name'], '|', r['site_id'])"
```

No `PLAN.jsonl` (every site skipped): nothing to write; go to S16.

### S14 The write: lane `scope-window-$W`

The lane has no step numbers: one wave is one lane, run stamp `${W}_mechanical-scope-window`,
journal test id `D20/scope-window`, cells `scope_status` and `scope_reason`. Save this script once
as `$DRV/tools/write_wave.sh` and run `bash $DRV/tools/write_wave.sh $W`. It refuses to start once
its log shows that the apply was started; a run that stopped before the apply may be started again
(its log is kept under a time suffix).

```bash
#!/bin/bash
# D20 scope-window write of one wave. Stops at the first non-zero exit. The apply is sent once.
set -u
W=$1
cd /c/PythonProjects/AncientMap
export PYTHONIOENCODING=utf-8
PY=.venv/Scripts/python.exe
A="$PY scripts/remediation/mechanical/apply.py"
L=scope-window-$W
LOG=output/remediation/final-2026-10-08/drivers/d20-scope/write_$W.log
if [ -e "$LOG" ]; then
  grep -q -- "--lane $L --apply" "$LOG" && { echo "REFUSED: $LOG shows the apply was started - read it, then S15"; exit 1; }
  mv "$LOG" "$LOG.$(date -u +%H%M%S)"
fi
run() { echo "== $*" >> "$LOG"; "$@" >> "$LOG" 2>&1; rc=$?; echo "exit $rc" >> "$LOG"; [ $rc -eq 0 ] || { echo "FAILED: $* (exit $rc)"; exit $rc; }; }
for s in check-primitive verify interests emit rehearse probe-guards apply verify rehearse-rollback; do
  run $A --lane $L --$s
done
run $PY scripts/remediation/identity/run.py --lane scope-window verify --wave $W
grep -E "APPLY OK|guard=False|\"accepted\"|\"deviations\"" "$LOG"
```

What each gate proves:

| gate | proof in the log |
| --- | --- |
| `--verify` (before) | the scope counts and the residual before the write |
| `--emit` | `wrote ...APPLY.sql (N rows)`, pinned to `PLAN.jsonl` |
| `--rehearse` | `N of N planned cell(s) changed and journalled`, then `ROLLBACK`, `journal rows for this run stamp \| 0` |
| `--probe-guards` | seven probes (guards 1 to 5 and the D50 invariant), each `refused by its own guard=True`. Exit 7 when one is not |
| `--apply` | `APPLY OK: the read-back matches the plan, row for row` |
| `--verify` (after) | the planned deltas: NULL and pending fall, `in_scope` and `retired` rise by the plan's transition counters; `curated rows with a scope_status but no scope_reason` 0 |
| `--rehearse-rollback` | `planned rows still holding the written value \| N` |
| `run.py verify` | `"accepted": true, "deviations": 0, "planned_cells": N` |

A stop before `--apply` (the script prints `FAILED` for a gate before it): nothing was written. Read
the end of the log. A failed connection (ssh, psql timeout on a read): run the script again. A
refusal of the rehearsal by guard 3 or 5 means a site changed after the plan: stop and report;
`APPLY.sql` exists now, so the tool will not plan this wave again. A probe that prints
`guard=False` (exit 7): stop and report.

Exit codes of `--apply`: 0 written and read back; 1 refused, nothing sent; 3 not committed (the
journal holds no row of the stamp: nothing was written; stop and report as above); 4 committed, psql
ended unclean; 5 outcome unknown; 6 committed but not confirmed. After 4, 5 or 6 do not run
`--apply` again: run the recount of S15 first. N rows: it landed, continue by hand, one call each,
with `$PY $A --lane scope-window-$W --verify`, `--rehearse-rollback` and
`$PY $I/run.py --lane scope-window verify --wave $W`. 0 rows after exit 5: recount again after
5 minutes, then report; the orchestrator decides the retry.

### S15 Journal recount

```bash
ssh ancientnerds "docker exec ancient_nerds_db psql -U ancient_map -d ancient_map -At -c \"SELECT column_name, count(*), count(DISTINCT row_pk) FROM remediation_change_log WHERE run_stamp = '${W}_mechanical-scope-window' GROUP BY 1 ORDER BY 1\""
```

Expected: `scope_reason|S|S` and `scope_status|S|S` with S = the plan's `sites`. The wave is
accepted with `run.py verify` at 0 deviations and this recount.

### S16 Result after the wave

```bash
$PY $I/run.py --lane scope-window result > $DRV/result_after_wave.json; echo "exit=$?"; cat $DRV/result_after_wave.json
```

`WAVE_SKIPS.jsonl` and `OWNER_LIST.jsonl` now carry the wave's skips.

### S16a Ask again the sites skipped `entry-moved` (available after the merge of build/track-b)

Run it after S17 of the wave that skipped them. Read the state:

```bash
grep -c '"reason": "entry-moved"' output/remediation/mechanical_scope_window/$W/SKIPPED.jsonl
$PY $I/run.py --lane scope-window export-moved --help >/dev/null 2>&1 && echo command-present
```

0: skip this step. No `command-present`: the merge has not landed; the sites stay on the owner list.

1. A discovery read after the plan that skipped the sites (S13 of that wave: the skip row carries
   that plan's read time, `read_at`). `export.py` under the three conditions of S1 (it replaces the
   export every identity lane reads), then `scope_window.py`:

```bash
$PY $I/export.py
$PY $I/scope_window.py
```

2. The web round. `N` is the next round number of the web stage (`status` lists the rounds):

```bash
N=4
$PY $I/run.py --lane scope-window export-moved --stage scope-window-web --handoff $HO-web-r$N > $DRV/web_moved_r$N.json; echo "exit=$?"; cat $DRV/web_moved_r$N.json
```

   Done: `exit=0` and `"round": "rN", "sites": n, "batches": b, "left_population": [...]`. It asks
   every site a wave's `SKIPPED.jsonl` lists as `entry-moved` that no imported round asked again for
   that wave, on its entry as the discovery holds it now; the prompt is the plain question, with no
   word of the earlier answer. `left_population` lists skipped sites the discovery no longer holds
   (retired by another lane, or back inside the window with no decision open): not asked; name them
   in the report. A site whose move was undone since (the other lane's write rolled back) reads as
   it was asked again; it is asked like the others, because only an imported moved round opens it
   for a new wave. Refusals (exit 1, nothing written):
   - `build the discovery again first`: the discovery was not read after the plan that found the
     move (the message names both times). Run step 1; that always clears this refusal.
   - `no decided site is to be asked again`: nothing is open (with `(n left the population: ...)`:
     only such sites were skipped). Go to S20.
   - `round rK is exported but not imported`: import that round first.
3. Answer and import the round as S3 and S4 (`--round r$N`, batch ids `r$N-b01 ...`, the prompt
   probe of S2 with `ROUND=r$N`). A held answer: S5, while one of the stage's two re-ask rounds is
   left (a moved round uses up none of them). Until the import, the answer that stands for such a
   site is the earlier one, about the earlier entry: a `plan` of the wave that skipped it made
   again (S13, a wave without `APPLY.sql`) skips it `entry-moved` again and writes nothing for it.
4. The re-check. A new answer that retires waits for a re-check of its own: `result` prints it as
   `<VERDICT>:waiting-for-recheck`, because a re-check answered before the web answer it would
   stand for confirms nothing. Two commands, each a round of its own. Run the first, and if it
   exported a round, answer and import it (S7) before the second. `M` is the next round number of
   the re-check stage at the time of each command (`status` lists the rounds):

```bash
M=4   # the next re-check round number now
$PY $I/run.py --lane scope-window export --stage scope-window-recheck --handoff $HO-recheck-r$M          # retirements never re-checked
M=5   # again the next number: 5 if the command above exported r4, else still 4
$PY $I/run.py --lane scope-window export-moved --stage scope-window-recheck --handoff $HO-recheck-r$M    # retirements re-checked before the move
```

   Each is refused with `no question to ask` or `no decided site is to be asked again` when it has
   nothing to ask; that is no fault, and a refusal has written nothing (the handoff directory is
   not created). Answer and import as S7.
5. S9 (no key ends in `:waiting-for-recheck`), S10 for the new retirements, S11, then S12 with a
   new wave label: the wave takes the sites asked again (the wave that skipped them no longer holds
   them once the moved round is imported) and S13 to S17 write them. Then S18 for that wave: it has
   a `PERIOD_WRONG.jsonl` of its own. S12 overwrites `$DRV/WAVE_LABEL`, so S18 of the earlier wave
   names its wave itself (`SW`). `plan` of the earlier wave is refused with `holds no site any
   more` when every site of it was asked again.

### S17 After the write

Do not start while a deploy restarts the API containers
(`ssh ancientnerds "docker ps --format '{{.Names}} {{.Status}}' | grep ancient_nerds_api"`).

```bash
ssh ancientnerds "docker exec ancient_nerds_api python -m api.services.rebuild_static"
scp scripts/remediation/static_export_check.py ancientnerds:/tmp/static_export_check.py
ssh ancientnerds "docker cp /tmp/static_export_check.py ancient_nerds_api:/tmp/x.py && docker exec ancient_nerds_api python /tmp/x.py"
ssh ancientnerds "docker exec ancient_nerds_api python -c 'from pipeline.indexnow import submit_recent; print(submit_recent())'"
```

- `rebuild_static`: about 5 minutes, exit 0.
- `static_export_check.py`: exit 0 and 0 differing sites. A retired site still listed counts as a
  difference. Exit 1 or 2 (2: the file is unusable): run `rebuild_static` again, then the check.
  The same exit twice: report.
- `submit_recent` announces the pages changed or retired in the last 2 hours and prints their
  number. The hourly Lyra cycle runs the same function, so 0 after more than 2 hours is no fault.
- Live check, three retired and three kept sites of the wave (ids from `PLAN.jsonl`):
  `curl -s -o /dev/null -w '%{http_code}\n' -L "https://ancientnerds.com/site.html?id=<uuid>"`
  prints 410 for a retired site and 200 for a kept one.
- The vector search drops the retired sites with the API's nightly reindex at 03:00 UTC
  (`scripts/build_lyra_index.py`, `delete_retired_points`). No command of this lane.

The scope wave needs no card_stats wave (it writes no card input) and no `wiki_thumbs` run.

### S18 The corrected starts (available after the merge of build/track-b)

`$LANE/waves/<wave>/PERIOD_WRONG.jsonl` lists every site of that scope wave whose sourced start
differs from the stored one: `site_id`, `stored_period_start`, `period_start`, the found quotes and
the answer's stamp (`why`, `answered_by`, `model`, `answered_at`, `label_borderline`). D20 asks for
these corrections. The period lane reads the file with `period_fix.py wave --d20` (gap G2, closed on
build/track-b) and writes each start under the rule `d20-sourced`; the journal evidence is the D20
decision row, the answer's found quotes, its agent and its model. Never feed the file to
`period_fix.py --cited`: that input stamps every row as owner decision D124. No model answers.

**One S18 per scope wave.** Every wave of the lane has a hand-off of its own: the first wave and
each follow-on wave (S16a, S19). `period_fix.py wave` reads one hand-off and a period label is
planned once (`WAVE.json exists: a wave is planned once`), so each scope wave gets labels `PW` and
`CW` of its own. `$W` is the wave S12 chose last, which need not be the wave whose starts are due:
S18 names its scope wave itself, as `SW`. The waves, their corrected starts and the labels S18 gave
them:

```bash
for d in $LANE/waves/*/; do w=$(basename $d); echo "$w starts=$(wc -l < $d/PERIOD_WRONG.jsonl 2>/dev/null) labels=$(cat $DRV/STARTS_LABELS_$w 2>/dev/null)"; done
```

`starts=` empty: the wave is not planned (S13). `starts=0`: nothing to correct, no S18 for that
wave (a period wave of nothing would use up a label). `starts` above 0 and `labels=` empty: S18 is
due for that wave. The lane is not finished while one is due.

Run S18 for `SW` only after S14, S15 and S17 of that wave (applied, accepted, recounted, exported).
The scope wave's premise is the stored period: a start written before S14 makes the scope apply
refuse (guard 5). Never run it between S13 and S15 of another wave (S13: no period lane applies a
step in that time).

Preconditions (read-only):

```bash
SW=YYYY-MM-DD                    # the scope wave whose starts are written now
M=scripts/remediation/mechanical
$PY $M/period_fix.py wave --help 2>/dev/null | grep -q -- '--d20' && echo d20-present   # the merge is in this checkout
wc -l < $LANE/waves/$SW/PERIOD_WRONG.jsonl                             # the corrected starts
grep -c '"answered_by"' $LANE/waves/$SW/PERIOD_WRONG.jsonl             # the same number: S13 ran on code with the merge
ls output/remediation/mechanical_period_fix output/remediation/mechanical_card_stats   # the labels used
```

- No `d20-present`: the merge has not landed. Count the lines, name the file in the report, stop
  here. The sites are `in_scope` and keep their stored start on the page.
- The third number is smaller than the second: S13 planned the wave on code without the merge (the
  check of S13 was skipped), the rows lack the answer's stamp, and `wave --d20` refuses the whole
  file (`REFUSED: ... exactly the keys`). The wave has `APPLY.sql`, so no command writes its
  hand-off again. Report the file; its sites keep their stored start and go to the owner list.

Choose labels `PW` and `CW` neither lane used (`2026-11-07` to `2026-11-07d` are used in both; a
second scope wave takes two further labels), and write them once for this scope wave:
`echo "<PW> <CW>" > $DRV/STARTS_LABELS_$SW`.

```bash
SW=YYYY-MM-DD
M=scripts/remediation/mechanical
read PW CW < $DRV/STARTS_LABELS_$SW
$PY $M/period_fix.py wave --wave $PW --no-d113 --d20 $LANE/waves/$SW/PERIOD_WRONG.jsonl > $DRV/period_wave_$PW.json; echo "exit=$?"; cat $DRV/period_wave_$PW.json
```

Reads production read-only. Writes `output/remediation/mechanical_period_fix/$PW/WAVE.json` (a
label is planned once). It prints `sites`, `steps`, `rule:d20-sourced` and one `skip:<reason>` per
refusal. The refused sites are in `WAVE.json` under `refused` (site, name, reason, note): they keep
their stored start, and each goes into the report.

| `skip:` reason | meaning | what the driver does |
| --- | --- | --- |
| `d20-scope-not-written` | the site is not `in_scope` in production | S14 of wave `$SW` has not landed, or another lane retired the site since: check S15, report |
| `moved-since-answer` | production no longer holds the start the answer judged | report (another lane wrote the period) |
| `d20-no-quote-states-year` | no found quote states the year itself, its century or its millennium as a date; a measure ("300 metres"), a count ("Population 1200") or a bare number with no date word before it ("Page 450", also "founded 1200") states none: the year is the answer's reading | report; owner list |
| `d58-window` | the start would leave the window, or make the site label-borderline although its answer was not asked the label question | report; owner list |
| `period-end-set`, `journal-disagrees`, `journal-chain-broken`, `site-gone`, `row-not-in-curated-source` | the lane's checks for every rule | report |

`sites` 0: there is no step and no card wave. Report the refusals; S18 of this wave is done.
`steps` is 1 (the population fits one step of 100); `steps` above 1: stop and report, the script
below writes step 1 only.

```bash
$PY $M/period_fix.py step --wave $PW --step 1          # read-only; PLAN.md, PLAN.jsonl, ROLLBACK.sql, SKIPPED.jsonl
cat output/remediation/mechanical_period_fix/$PW/s001/PLAN.md
```

It prints `lane`, `sites`, `cells` (the start, and the label where the band changes) and
`skip:moved-since-wave` for a site written between the wave and the step. Spot check before the
write (D151): read every `old -> new` line of `PLAN.md` and, in `PLAN.jsonl`, the quote of each
site's evidence that states the year. The gate proves only that a quoted page states the year as a
date; any found quote of the answer may be the one, also one that supports only the keep verdict.
The quote must date the beginning of THIS site, not a later phase, a namesake or the modern town.
One bad row: stop and report. Never edit the plan.

The write. Save this script once as `$DRV/tools/write_starts.sh` and run
`bash $DRV/tools/write_starts.sh $PW $CW`. It stops at the first command that exits non-zero:
nothing after a failed gate runs, the card wave least of all. It refuses to start once its log
shows that the period apply was started; a run that stopped before that apply may be started again
(its log is kept under a time suffix).

```bash
#!/bin/bash
# D20 corrected starts: step 1 of period wave PW, then card wave CW. Stops at the first non-zero
# exit. Each apply is sent once.
set -u
PW=$1; CW=$2
cd /c/PythonProjects/AncientMap
export PYTHONIOENCODING=utf-8
PY=.venv/Scripts/python.exe
M=scripts/remediation/mechanical
A="$PY $M/apply.py"
P=period-fix-$PW-s001
C=card-stats-$CW
LOG=output/remediation/final-2026-10-08/drivers/d20-scope/write_starts_$PW.log
if [ -e "$LOG" ]; then
  grep -q -- "--lane $P --apply" "$LOG" && { echo "REFUSED: $LOG shows the period apply was started - read it, recount, go on by hand"; exit 1; }
  mv "$LOG" "$LOG.$(date -u +%H%M%S)"
fi
run() { echo "== $*" >> "$LOG"; "$@" >> "$LOG" 2>&1; rc=$?; echo "exit $rc" >> "$LOG"; [ $rc -eq 0 ] || { echo "FAILED: $* (exit $rc)"; exit $rc; }; }
for s in emit verify rehearse probe-guards apply verify rehearse-rollback; do
  run $A --lane $P --$s
done
run $PY $M/period_fix.py accept --wave $PW --step 1
echo "period step accepted: $P"
run $PY $M/card_stats.py --wave $CW --export
run $PY $M/card_stats.py --wave $CW --write
[ -s output/remediation/mechanical_card_stats/$CW/PLAN.jsonl ] || { echo "$C plans 0 cells: no card number changed, nothing to write"; exit 0; }
for s in emit rehearse probe-guards apply verify rehearse-rollback; do
  run $A --lane $C --$s
done
grep -E "APPLY OK|guard=False|ACCEPT_EXIT|\"deviations\"" "$LOG"
echo "written: $P and $C"
```

Where the script stopped (`FAILED: <command> (exit N)`; the end of the log says why):

- At a gate before the period `--apply`: nothing was written. A failed connection (ssh, psql
  timeout on a read): run the script again. Anything else: stop and report.
- At the period `--apply`: the exit codes are those of S14. 1 or 3: nothing was written; stop and
  report. 4, 5 or 6: never run `--apply` again, and the script refuses to start again. Recount
  first (the query of S15 with the stamp `${PW}_mechanical-period-fix-s001`). Rows: it landed; go
  on by hand, one call each and each only after the one before exited 0: `$PY $A --lane
  period-fix-$PW-s001 --verify`, `--rehearse-rollback`, `$PY $M/period_fix.py accept --wave $PW
  --step 1`, then the card commands of the script in its order. 0 rows after exit 5: recount again
  after 5 minutes, then report.
- After the period `--apply` and before `period step accepted`: the starts are written and not
  accepted. Stop and report; no card wave.
- After `period step accepted`: the starts are written and accepted, the card numbers of their
  sites are not recomputed yet. A stop before the card `--apply` wrote no card: report, the
  orchestrator decides the card wave. At the card `--apply`: the exit codes of S14, recount with
  the stamp `${CW}_mechanical-card-stats`.

Run stamps `${PW}_mechanical-period-fix-s001` and `${CW}_mechanical-card-stats`; recount both as in
S15 (the period step: `period_start` one row per site, `period_name` one row per site whose band
changed); then S17 again.

Undo of a landed step is its `ROLLBACK.sql`, the orchestrator's decision. **The order of an undo
changes with S18.** The scope wave's `ROLLBACK.sql` carries guard 5 like its write, over every
planned site, and the premise holds the stored period. Once one start of wave `$SW` is written,
`output/remediation/mechanical_scope_window/$SW/ROLLBACK.sql` refuses as a whole, its retirements
included (`planned row(s) no longer hold the premise the plan derived its value from`). To undo
scope wave `$SW` after its S18: first `output/remediation/mechanical_period_fix/$PW/s001/ROLLBACK.sql`
(the stored starts are back), then the scope wave's `ROLLBACK.sql`, then a new card_stats wave (the
cards are recomputed, a card wave is not undone from its file once a period label moved). Name
this order in the report of every wave whose S18 wrote a start.

### S19 The five sites of X13 (available after the merge of build/track-b)

G1 and G5 are closed on build/track-b. Merged before S1 (O15: X13 is built into the lane before
its first round): the five are in r1 and this step falls away. S1 tells which it is: no key
`held_label_open_question` and `population` 74 means the merge is in the code that ran.

On code without the merge the five held sites are in no round. When the merge lands after the first
wave, a new discovery is needed; after the merge `scope_window.py` builds one also once Hadrian's
Wall Path is retired. Run S1 again, then

```bash
N=4                                  # the next round number of the web stage (status lists the rounds)
$PY $I/run.py --lane scope-window export --stage scope-window-web --handoff $HO-web-r$N
```

A further `export` asks only the sites never asked (expected 5, 1 batch). It is refused while the
newest round is not imported. Then S3 and S4 for that round, a further `export` of the re-check
stage for its retirements with S7, then S9 to S17 with a new wave label (S12 overwrites
`$DRV/WAVE_LABEL`), then S18 for that wave. A stage has two re-ask rounds in all: when the first 69 used both, a held answer of the
follow-on round cannot be asked again and goes to the owner list. The first wave does not wait for
this.

### S20 Report to the orchestrator

- `by_verdict_and_state` of `result_after_wave.json`; the plan's transition counters; the recount.
- The retired site ids (from `PLAN.jsonl`, `new_value` `retired`): the image, description, card,
  D13 and D23 populations drop them. Name the retired town records of S10 for the D13 driver.
- `PERIOD_WRONG.jsonl` of every wave: path and line count (S18). `OWNER_LIST.jsonl`: path and
  line count.
- Answers spent: `find output/remediation/handoff -path '*d20-scope-window*' -name '*.answer.json' | wc -l`.
- Files for the orchestrator's commit: `output/remediation/mechanical_scope_window/$W/` and
  `$DRV/`. `PLAN.jsonl` and the two SQL files carry quoted page text and URLs; gitleaks may report
  one, and the orchestrator triages it in `.gitleaksignore` before any push to `main` (as commit
  7f86afe did for card_stats).
- Sites skipped `entry-moved`: how many S16a asked again and wrote, and the `left_population` ids
  it printed (on code without build/track-b: the skipped sites, which stay on the owner list).
- S18, per scope wave: the labels `PW` and `CW`, the wave's counters (`rule:d20-sourced`, every
  `skip:`), the refused sites of `WAVE.json` with their reasons, the two recounts, and the undo
  order (the period step's `ROLLBACK.sql` before the scope wave's). A wave with corrected starts
  and no S18: name it.
- Not covered by this lane: the five X13 sites only if the run was on code without build/track-b
  and S19 was not run, the corrected starts only where S18 could not run (code without the merge,
  or a `PERIOD_WRONG.jsonl` planned before it) or refused a site, the four retired
  label-borderline sites (Fortress of Niha, Dara Fortress, Çem Kalesi, Belenkeşlik Castle) and Mount
  Livadiyskaya (no lane asks a retired site), Pilares do Lena (`1ac14890`, its not-a-site answer
  never counted).

## 5. The write in one table

| what | lane | run stamp | unit | accept |
| --- | --- | --- | --- | --- |
| scope decision (S14) | `scope-window-<W>` | `<W>_mechanical-scope-window` | one wave, no step number, at most 100 sites | `identity/run.py --lane scope-window verify --wave <W>` |
| corrected start (S18, after the merge of build/track-b) | `period-fix-<PW>-s001` | `<PW>_mechanical-period-fix-s001` | one period wave per scope wave, steps of at most 100 sites | `mechanical/period_fix.py accept --wave <PW> --step 1` |
| card numbers after a period write (S18) | `card-stats-<CW>` | `<CW>_mechanical-card-stats` | one wave per period wave | `apply.py --lane card-stats-<CW> --verify` after the apply |

Order of every write: backup and drill of the day, plan, emit, rehearse, probe-guards, apply,
read-back (`--verify`), rehearse-rollback, accept with 0 deviations, journal recount. After a scope
or period wave: `rebuild_static`, `static_export_check.py`, IndexNow.

The reasons the lane writes: `E3: period_start N is past the cutoff; <quote>` (OUT_OF_WINDOW),
`E3: not an archaeological site (<kind>): <why>` (NOT_A_SITE), `D58: a medieval Old World subject
(<kind>): <why>; <quote>` (MEDIEVAL_SUBJECT), `E3 museum rule: the museum exhibits ancient material;
<quote>` (MUSEUM_KEEP), `E3: period_start N is past the cutoff, but a source dates the start at M;
<quote>` or `E3: kept in scope, a source dates the start at M; <quote>` (PERIOD_WRONG).

Undo of a landed wave is `ROLLBACK.sql`, rehearsed in S14. Running it is a decision of the
orchestrator, never the driver's. After S18 wrote a start of the wave, that file refuses as a whole
(guard 5: its premise holds the stored period) until the period step's `ROLLBACK.sql` has been run:
the period step is undone first, then the scope wave, then the cards are recomputed by a new
card_stats wave (S18).

## 6. Verdicts

| stage | verdict | what follows |
| --- | --- | --- |
| web | `PERIOD_WRONG` (a sourced start at or before the cutoff, or the stored one confirmed) | `in_scope`; a different year goes to `PERIOD_WRONG.jsonl` |
| web | `MUSEUM_KEEP` (type Museum only) | `in_scope` |
| web | `OUT_OF_WINDOW` (sourced start past the cutoff) | re-check, then `retired` |
| web | `NOT_A_SITE` (quotes from 2 websites; Wikimedia counts as one) | re-check, then `retired` |
| web | `MEDIEVAL_SUBJECT` (the 2 borderline sites only; byzantine, crusader, norse) | re-check, then `retired` |
| re-check | `CONFIRM` (with a quote) / `REJECT` | the retirement is written / the site stays and is listed |

## 7. Code gaps

G1, G4 and G5 are built on branch `build/track-b` (commit `9fc0fb0`, 2026-11-11) and are available
after its merge into the checkout this playbook runs in. Proof that the merge is in:
`$PY $I/run.py --lane scope-window export-moved --help` exits 0, and S1 prints no key
`held_label_open_question`. G2 is built on the same branch (commits `13c8b27` and, after its review, `a969cc4`, 2026-11-11); proof
that it is in: `$PY scripts/remediation/mechanical/period_fix.py wave --help | grep -q -- '--d20'`
exits 0. G3 is not part of these commits.

| # | gap | files | size | blocks |
| --- | --- | --- | --- | --- |
| G1 | **Closed, available after the merge of build/track-b.** X13 is in the lane: `$PY $I/scope_window.py` puts the sites of Spain, Portugal, Malta and Sicily dated 500-1500 into the population like any European site past 500 AD (no count `held_label_open_question`), and `$PY $I/run.py --lane scope-window plan --wave $W` writes a confirmed OUT_OF_WINDOW for them (no skip `label-open-question`). No new command. `docs/procedures/WD2_SERVED_IMAGE_AND_SCOPE.md` 1b records X13. Not changed: `pipeline/normalizers/dates.py` (`label_open_question`, `label_scope`) and the un-retire still hold or skip such a record, which keeps it out as X13 asks. | `scripts/remediation/identity/scope_window.py`, `scope_judge.py`, `tests/remediation/test_identity_b_scope.py`, `test_identity_scope_parents.py`, cases `x13` in `scripts/remediation/mechanical/mutation_sweep.py`, the runbook | M | nothing once merged before S1; S19 when merged later |
| G2 | **Closed, available after the merge of build/track-b.** `$PY scripts/remediation/mechanical/period_fix.py wave --wave PW --no-d113 --d20 $LANE/waves/$W/PERIOD_WRONG.jsonl` reads the hand-off (rule `d20-sourced`), then `step`, the gates of `apply.py --lane period-fix-PW-s001` and `accept` as for every period-fix wave, then a card_stats wave (S18). Journal evidence: the D20 decision row, the answer's found quotes, its agent, model and reasoning; never D124. Listed and not written: a site that is not `in_scope` yet (`d20-scope-not-written`), a start that moved since the answer (`moved-since-answer`), a year no found quote states as a date (`d20-no-quote-states-year`: the fields lanes' `states_year`, read as the dating extractor reads a number, so a measure, a count or a bare number states none), a start outside the window or label-borderline without the label question (`d58-window`). The scope `plan` (S13) writes the answer's stamp into each row; a file planned on code without the merge is refused whole (S13 checks for the merge before it plans). Each scope wave is a period wave of its own. The scope wave's `ROLLBACK.sql` refuses once a start of it is written: the period step is undone first (S18). | `scripts/remediation/mechanical/period_fix.py`, `scripts/remediation/identity/scope_judge.py` (`build`), `tests/remediation/test_mechanical_period_fix.py`, `test_identity_b_scope.py`, cases `d20 start:` in `scripts/remediation/mechanical/mutation_sweep.py`, the runbook (WD2 1b) | M | nothing once merged before S13; merged after S13 the file of that wave is refused and its starts go to the owner list |
| G3 | The Fable switch of the import gate is in the working tree, uncommitted: `import` without `--calibration` for a role that stands by D153. Another agent is building it. S0 proves it is present. | `scripts/remediation/roles.py`, `scripts/remediation/opus_handoff.py`, `scripts/remediation/identity/rounds.py`, `scripts/remediation/identity/run.py` | S | S3, S4, S7 |
| G4 | **Closed, available after the merge of build/track-b.** `$PY $I/run.py --lane scope-window export-moved --stage scope-window-web --handoff DIR` asks again every site a wave's plan skipped `entry-moved`, on its entry as a discovery built after the move holds it; `$PY $I/run.py --lane scope-window export-moved --stage scope-window-recheck --handoff DIR` asks again the retirements whose re-check was answered before the new web answer (such a re-check confirms nothing: `result` shows `waiting-for-recheck`, `plan` refuses it). Once the moved round is imported the wave that skipped the site no longer holds it: the next `wave` takes it, and its skip row leaves `OWNER_LIST.jsonl`. Step S16a. | `scripts/remediation/identity/run.py`, `rounds.py`, `scope_judge.py`, `waves.py`, their tests, cases `moved` in `scripts/remediation/identity/mutation_sweep_b.py`, the runbook (WD2 1b) | S | nothing once merged; before the merge a site skipped `entry-moved` goes to the owner list |
| G5 | **Closed, available after the merge of build/track-b** (built with G4, which needs a discovery after a wave). `$PY $I/scope_window.py` builds the discovery also when no shown site carries the prefix `360a4afb`: Hadrian's Wall Path retired. It still refuses two sites of that prefix or one under another name. | `scripts/remediation/identity/scope_window.py` (`build`), `tests/remediation/test_identity_scope_parents.py`, cases `footpath` in `scripts/remediation/identity/mutation_sweep.py` | S | nothing once merged; before the merge S19 and any S1 after the first wave |

## 8. What can go wrong

| risk | the check that catches it |
| --- | --- |
| The stale 130-row list is exported | S2: `discovery-fresh`, the line count and the `label_borderline` count |
| `export.py` breaks an open round of another lane or D14 B's frozen basis | S1: the three conditions before `export.py` |
| The prompt code changes between an export and its import | the prompt probe of S2, before the agents and before every import |
| Wikimedia throttles at 4 fetchers | at most 3 web agents over all lanes, an import counts as one; the curl before an import |
| A quote on a throttled or blocked page | the status count after the import; the answer is held and asked again (S5, S8); the kept failed fetch is not retried, so the re-ask must cite another page |
| An answer under the wrong role or model | `import` refuses and names the files |
| An agent stops mid-batch | `opus_handoff.py validate` lists `missing` |
| A wave is selected while a retirement waits for its re-check | S9: no key ends in `:waiting-for-recheck` |
| A site changes between S1 and S13 | `SKIPPED.jsonl` reason `entry-moved`; keep S1 to S15 within one run of the lane. After the merge of build/track-b: S16a asks the site again and a later wave writes it |
| A confirmation of an earlier answer is taken for the new one (S16a) | after the merge: `result` shows the site `waiting-for-recheck` and `plan` refuses it until the re-check stage has answered after the new web answer |
| A site changes between S13 and the apply | guard 3 or 5 refuses in the rehearsal; run S13 to S15 in one go |
| A wrong retirement | the adversarial re-check; S10; the dangerous transitions of S13 |
| A corrected start (S18) is written before the scope wave, on a start that moved, or on a year no quote states | the `skip:` counters of `period_fix.py wave --d20` (`d20-scope-not-written`, `moved-since-answer`, `d20-no-quote-states-year`); the read of `PLAN.md` before the write |
| The hand-off was planned on code without the merge | S13: `d20-present` before the plan (a wave without `APPLY.sql` is planned again on merged code). S18: the count of `"answered_by"` against the line count; `wave --d20` refuses the file whole |
| A gate of S18 fails and the commands after it run anyway (the card wave on a period state nobody recounted) | `write_starts.sh` exits at the first non-zero exit; nothing of S18's write is pasted as a loose loop |
| A follow-on wave's corrected starts are never written, or S18 reads the wrong wave's hand-off | S18 runs per scope wave under `SW`; the list of waves with `starts` and `labels` at the top of S18 |
| A scope wave is to be undone after S18 wrote one of its starts | its `ROLLBACK.sql` refuses as a whole (guard 5); the period step's `ROLLBACK.sql` first (S18, section 5) |
| A number in a quote that is no date passes for the year (a measure, a count, a page number) | the gate reads an unmarked number as the dating extractor does (`d20-no-quote-states-year`); whether the stated date is the start of this site is the spot check of S18 |
| A town record that D13 would re-target is retired | S10: the town records are read twice |
| The write's outcome is unknown | the exit code of `--apply` and the recount of S15 before any retry |
| The write script runs twice | it refuses once its log shows that the apply was started; `--apply` itself refuses a stamp that already journals rows |
| The wave label changes at midnight UTC | `$DRV/WAVE_LABEL`, written once in S12 |
| The served export still lists a retired site | `static_export_check.py` exit 1 |
| The five X13 sites are forgotten | S1: after the merge of build/track-b `population` 74 and no key `held_label_open_question`; before it `held_label_open_question` 5, then S19 and the report |
| The block costs too much | count the answer files after each round; past 156 (25 % above this playbook's 125) stop and report (D151). D146's figure of about 230 came from the old count of 131 sites and is no budget |
| Disk C: runs low | `df -h /c` in S0; below 10 GB stop and report (D135) |
| A cp1252 crash on a site name | `PYTHONIOENCODING=utf-8` in the header |

## 9. What the driver never does

- Never edits by hand: code, a prompt file, an answer file, a file under `$RUN` (the `pages/`
  directories included), `PLAN.jsonl`, `APPLY.sql` or `ROLLBACK.sql`. An answer file a refusal names
  is deleted and answered again, never changed.
- Never runs a calibration, seal, verdict or release command (D154), and never passes `--calibration`.
- Never answers a question itself and never launches an answering agent on a model other than
  `claude-fable-5-2`.
- Never runs more than 3 web agents over all lanes together.
- Never exports into a handoff directory that exists and holds files.
- Never runs `identity/export.py` while another identity lane has an open round or D14 B holds the
  export frozen.
- Never selects the wave before every round of both stages is imported and S10 is done.
- Never reuses a wave label; never uses `2026-11-07`.
- Never runs `--apply` twice; never runs `ROLLBACK.sql`.
- Never writes `scope_status` with psql, and never uses `mechanical/scope_owner.py` here (it is
  pinned to the two sites of D138).
- Never feeds `PERIOD_WRONG.jsonl` to `period_fix.py --cited`.
- Never un-retires anything: the four retired borderline sites and Mount Livadiyskaya stay retired.
- Never counts a 403 or 429 as a finding.
- Never writes without the passed backup drill of the day.
- Never commits or pushes; the orchestrator does.

## 10. Population and cost

| stage | role | questions | batches |
| --- | --- | --- | --- |
| web r1 | `web_verifier` | 69 | 14 |
| web re-asks r2, r3 | `web_verifier` | about 12 | 3 |
| re-check r1 | `adversarial` | about 30 | 6 |
| re-check re-asks | `adversarial` | about 4 | 1 |
| **the run as the code stands** | | **about 115 (100 to 135)** | **about 24** |
| X13 (the five sites): in r1 after the merge of build/track-b (web r1 then 74 questions in 15 batches), else the follow-on of S19; web and re-check | both | about 10 | 2 to 3 |
| S16a, per site skipped `entry-moved` (after the merge): web and, for a retirement, re-check | both | 1 to 2 | 1 to 2 rounds of 1 batch |
| **total** | | **about 125 (105 to 145)** | **about 27** |

Expected outcome of the 69: about 21 museums kept, about 15 to 20 corrected or confirmed starts,
about 28 to 32 retirements, a few held or rejected for the owner list. Wall time with all three web
slots: about 3 to 4 hours of answers, 30 minutes for the write, 10 minutes after it.
