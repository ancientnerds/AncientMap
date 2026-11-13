# PLAYBOOK: lane WN (a sourced text for the shown sites without a description) and the disputes (D21, D50, D84, D149)

Measured read-only on 2026-11-10, 20:00 UTC (a fresh production read, the tools' sources and `--help`,
the state on disk). Binding: `output/remediation/OWNER_DECISIONS_2026-10-08.md` D21, D22, D50, D81, D84,
D145, D147, D149, D151, D153-D156; runbook `docs/procedures/SENTENCE_CHECK.md` sections 11, 12, 14, 15.5,
15.7, 15.8, 15.10 and `docs/procedures/WD2_SERVED_IMAGE_AND_SCOPE.md` section 2.2.

The lane has five parts, in this order: **WN** (texts for empty sites), **DS** (the dispute screen),
**RP** (the repair pass that drops sentences stating one side as fact), **EN** (lane E: both positions
appended), **UR** (the six D50 sites shown again). WN has no code gap. DS to UR had five (section 12).
**G1, G2 and G3 are built** (commits `d008775` and its review `5abf8da` on `build/track-b`, 2026-11-11): their commands stand at
DS-3, DS-4, EN-2, EN-3, EN-6 and EN-9 and are **available after the merge of build/track-b** (P-8 tells
whether the tree has it). **G4 and G5 are built** too (commit `1eb2f73` and its review `158a9d9` on `build/track-b`, 2026-11-11):
their commands stand at UR-1, UR-2 and UR-3 and are **available after the merge of build/track-b**
(P-9 tells whether the tree has them).

Every model answer is `claude-fable-5-2` (D153). No calibration, seal, verdict or release step exists
any more (D154). What stays, because code enforces it: the judged 20-site pilot before a WN plan and
before a lane-E plan is written (`wc/cli.py pilot_approval`), and the journalled write path. The dispute
screen's `recall` (DS-4) is a check of code against 17 known names: no model answers it.

Stop rule (D151, D156): a part that projects more than 25 % above the owner's estimate (D145: WN about
200 answers, D21 about 360) is reported before its first answer and goes on only on the orchestrator's
word. The two checkpoints are WN-2 (250) and DS-5 (450).

---

## 1. Where the lane stands (measured 2026-11-10)

**Production.** 4,907 shown curated sites (`source_id='ancient_nerds'`, `scope_status` not `retired`).
**40 have no description** (all `description IS NULL`, none blank; 1 more is retired and not this lane's).
17 lane-N texts are live (the WN pilot of 2026-10-06, batch `p4wc-4325`); **0 lane-E texts**: lane E has
never written to production.

**Disk.** No WN run, no dispute run and no enrichment run exists (`output/remediation/wc_runner/runs/`
holds only `pilot-2026-09-27*`, `mass-2026-09-27-01..05`, `defects-2026-10-02`, `defects-a1-2026-11-06`,
`enrich-cal-2026-10-24`). The old WN run `wn-2026-10-06` is lost; its batch is closed by record
(`final-2026-10-08/reconstructed/p4wc-4325.closed.json`) and approves nothing.

**Lane WC's apply root** `output/remediation/logs/_write_apply_p4wc`: last accepted step **13**
(batches `p4wc-4400..4403`, run `defects-a1-2026-11-06`), no pending `STEP.json`, no `STOPPED.json`.
Next step number 14, next free plan batch 4404, **as of today**: the D57 lane (its own WN runs
`wn-d57-*`) and the WC-finish lane (`mass-03/-04/-05`, `defects-2026-10-02`, all four not built) run before
this lane (D151) and take numbers first. Always read both from disk (`last_batch`, `chain`, section 3).

**The live API** runs `5877741e`; it contains lane N (`7d7a1f00b758`, `NO_LICENCE_LANES`) and lane E
(`9bdda00e8469`, `ENRICHMENT_LANE`).

### 1.1 The 40 sites

All 40 were **cleared by lane WC**: the last journal row of each one's `description` is
`WC/description-clear`. None lacks a journal row, none "never had a text".

| cleared by | when | sites |
| --- | --- | --- |
| `mass-2026-09-27-01` (`p4wc-42xx`) | 2026-10-03 | 9 |
| `mass-2026-09-27-02` (`p4wc-43xx`) | 2026-10-06 | 19 |
| `defects-a1-2026-11-06` (`p4wc-4401`, `-4402`; Phase-4 Wikipedia texts a card wave found contradicted, D81) | 2026-11-07 | 12 |

By source situation: **23 have an English Wikipedia title** (all 23 articles are in the shared cache),
**1 has only a Wikidata item**, **16 have neither**. Of the 16, 8 have a stored source of another kind
(Spanish or Italian Wikipedia, a travel or local page) and 8 have no stored source at all (six Turkish
place names, Cuatro Cienegas Footprints, House of the Knight): expect most of those 8 to end empty.
None of the 40 carries a WC key in `raw_data` (no `stale-keys`); the 12 defects-a1 sites carry only
`_card_provenance`.

| id | name | country | Wikipedia / Wikidata | also in |
| --- | --- | --- | --- | --- |
| 036346d9-313c-4fcd-9649-1aaba368e72e | Kyaneai Tarihi Sarnıç | Türkiye | none | D14 open cluster, D20 list; empty in the old WN pilot |
| 0f654bf4-86b7-4602-8bee-c8da00f3edee | Roman Temple Qsarnaba | Lebanon | Qasr el Banat, Lebanon | |
| 11ac5108-ad13-4b42-babc-ed1e298bebe3 | Templo del Sol | Peru | none (source: es.wikipedia) | empty in the old WN pilot |
| 1c0b4493-7302-4c4b-a126-a91e9b27305e | Capler Camp | England | Capler Camp | |
| 1d6c490a-ef60-42ae-85d8-4ba27c1b8d3e | Trajan's Bridge | Serbia | Trajan's Bridge | |
| 217b6292-d8ee-403b-a8ad-236304ac481d | Cuatro Cienegas Footprints | Mexico | none | |
| 221d4702-9626-4430-a71f-d5b70bcb9d4e | Naveta Biniac | Spain | Naveta (the monument type, not this site) | **D13 funnel**, D14 open cluster |
| 24de1fb5-935c-4fc0-89d0-00539a0ce610 | Te Pito Kura | Chile | none | empty in the old WN pilot |
| 34d5b282-ab84-430a-90eb-6347f007fd2e | Ligures Baebiani | Italy | Ligures Baebiani | |
| 3f793103-342f-40ca-a0fa-96b1065ad986 | Temple of Thutmose III | Egypt | Festival Hall of Thutmose III | |
| 40acede4-eb32-4515-9ca4-b44145280678 | Karabal Belören Demre Antalya | Türkiye | none | D20 list |
| 417b5d77-c70a-40ad-adad-7f92ef1a0544 | Roma Dönemi Agora Harabeleri | Türkiye | none | D20 list |
| 45c293d7-6d69-47e5-adec-68b8e1ce6ec0 | Çatalat Viranşehir Antik Kent | Türkiye | Viranşehir (the modern town) | **D13 funnel** (tier A) |
| 48e08ccf-7661-47c1-9a0e-ff9e205530e0 | Jannusan Burial Mound Field | Bahrain | none | |
| 4c5103a2-0ae8-443d-9203-f3a4bf4bbd6f | The Ancient Lycian Mezarı2 | Türkiye | none | |
| 4cab063f-a1a1-4e24-a46a-d609f2f87f53 | Quillcay Machay | Peru | Quillcay Machay | |
| 52827c54-91cb-4902-99fb-7b0860a71e36 | Tlalpan | Mexico | Tlalpan (the borough) | |
| 54dc63d1-d88f-4d40-976b-460b203a07ef | House of Orpheus | Cyprus | none | D14 open cluster (part of Paphos) |
| 58a5a5b2-735a-4fda-bf2d-52e723fd86bc | House of the Knight | Morocco | none | D14 open cluster, D20 list |
| 5ac30362-6c6f-412b-857b-3ec51df81f66 | Home Tombs | Türkiye | none | |
| 67215100-355e-4586-ae41-00838c8e1566 | Temple of Diana, Cefalù, Sicily | Italy | none | |
| 673332a5-3a27-4045-a929-ddbf7ff7e824 | The Acropolis of Ancient Thasos | Greece | none | |
| 68859b06-2135-4711-a160-da003d18ccca | Saoba Stone Pillars | Taiwan | Saoba Stone Pillars | |
| 6a43a3e7-66c7-4133-a91c-58a52cc5e0dc | The Roman Bridge (Elguentra) | Algeria | Wikidata Q101243536 only | |
| 6b0c9ab6-58dd-4989-a937-b83a957ef665 | Maltepe Tumulus | Türkiye | none | |
| 6e6a831d-bdce-400c-86af-9238e6af3e89 | Valley of the Thracian Rulers | Bulgaria | Valley of the Thracian Rulers | |
| 70466849-1cf9-4af9-a442-7a4ffa6e24c9 | Karabölücülü Harabeleri | Türkiye | none | |
| 77c8e01e-c8c8-4667-99f2-e36c81d6c0f8 | Roman Walls | Italy | none (source: it.wikipedia, Mura di Aosta) | |
| 5a91fe47-3207-443c-9eff-a1afd9e47481 | Maiden Way | England | Maiden Way | holds a WB card |
| 79484b17-4db6-454c-aacb-a3cb5eafaec9 | Scutchamer Knob | England | Scutchamer Knob | holds a WB card |
| 7c097275-ba5b-44f8-852b-77f450b7b813 | Welsh Way | England | Welsh Way | holds a WB card |
| 82f2d8e5-e3fa-4782-b580-a7eca3ecad45 | Main Limes | Germany | Main Limes | holds a WB card |
| 904babe6-e678-4a59-be5f-89228d5cbb59 | Stoa Basileios | Greece | Stoa Basileios | holds a WB card |
| 9190f012-5a73-4f94-9f39-9c870a7bdf4c | Shap Stone Avenue | England | Shap Stone Avenue | holds a WB card |
| 94cf34a3-2cf8-41e9-adf3-80c288b4f972 | Aston Valley Barrow Cemetery | England | Aston Valley Barrow Cemetery | holds a WB card |
| 9ca635c0-2df8-4a4a-ba1e-815f1fd7796b | Dun Vulan | Scotland | Dun Vulan | holds a WB card |
| a0736505-9ca5-4361-bc0a-f0a47b6fed7e | S'Argamassa Roman Fish Farm | Spain | S'Argamassa Roman Fish Farm | holds a WB card |
| a1428be8-db83-4d05-be49-9ee85ed77689 | Menir da Cabeça do Rochedo | Portugal | Menir da Cabeça do Rochedo | holds a WB card |
| bdbf1e68-32c8-4571-90c0-ef154d458704 | Kutikina Cave | Australia | Kutikina Cave | holds a WB card |
| cd2e38bd-c70e-4813-8ccd-0a567ab6a7ca | Markahirka | Peru | Markahirka | holds a WB card |

The first 9 rows are the mass-01 clears, the next 19 the mass-02 clears, the last 12 the defects-a1 clears.
The population the lane really asks is whatever the fresh read gives when WN starts: these 40, plus the
sites the WC-finish lane clears before (forecast 60-70), minus the sites D14 part B and D20 retire.
Six of the 40 wait for an identity decision ("also in": D14 open cluster or D20 list); WN-2 leaves them
out while D14 part B or D20 is not done.

With today's 38 askable sites and seed 20261110 the pilot draws 11 sites with an English article, 5 with
another stored source and 4 with none; it needs 10 judged texts to count (WN-8).

Not this lane's: the 37 sites of D57. The D57 lane writes their texts itself (runs `wn-d57-*`, on rows it
inserts as `retired`). Today `wc/cli.py hidden` asks no retired row; WN-2 leaves out any that the D57 lane's
code change lets into the population. If a `wn-d57-*-pilot` was written before this lane starts, it stands
first among the WN plans of the chain; this lane still runs its own pilot.

### 1.2 The dispute population

No dispute run exists. Measured in memory (no file written) on a fresh read of 2026-11-10 with the screen's
own code, the shared Wikipedia cache (4,520 English texts) and today's categories (90 API queries, 66 s,
4,527 titled sites, no missing title): **235 candidates** (signals: description 114, Wikipedia text 104,
category 21, site type 17; 14 are candidates by their category alone). Without the categories: 221.

`recall` flags **16 of the 17** known positives (0.9412, bar 0.9): it passes by exactly one name, and only
with the categories (10 of 17 without). The miss is **Pantelleria Vecchia Bank Megalith
(`daa1ea4b-c002-4552-a4ef-45d996c6cea6`), the site D21 names**: its description, its article (0 pattern
hits) and its categories carry no signal. It is asked by name: `candidates --include` (DS-3, available
after the merge of build/track-b; measured on a fresh read of 2026-11-11 in a temp directory, without the
categories: 221 candidates without the list, 222 with it, Pantelleria a candidate with 3 sentences and the
one signal `named`). `recall` still counts it as missed and lists it under `named`: the screen's own
recall stays 16 of 17.

The candidate count by `--wiki-min-hits` (the screen's own option; recall stays 16 of 17 for each):

| `--wiki-min-hits` | candidates `C` | projected answers `2.2 C + 20` |
| --- | --- | --- |
| 2 (default) | 235 | 537 |
| 3 | 184 | 425 |
| 4 | 157 | 365 |

Lane-E class of the 235 today: 191 enrichable, 43 `unchecked-text`, 1 `no-provenance`.

The six D50 sites (`mechanical/lane.py D50_DISPUTED_SITES`), all `retired`, all with a card text:

| id | name | country | text | lane-E class today |
| --- | --- | --- | --- | --- |
| c8d2c13e-fd9a-466c-9fdc-fc26ee798ded | Baltic Sea Anomaly | `Baltic Sea` | lane W | enrichable |
| 84b456ff-0b44-4d75-92a4-5cbe22026b95 | Richat Structure | Mauritania | lane W | enrichable |
| 01296632-a2a1-4610-a4a9-d0c3be77b788 | Yonaguni Monument | Japan | lane L, checked | enrichable |
| 3c466fde-b751-4065-8de2-bd5c9280afe5 | Bosnian Pyramid of the Sun | Bosnia and Herzegovina | lane L, checked | enrichable |
| 0fd636ac-1a80-4a77-b9d0-a065ae811656 | Bosnian Pyramid of the Moon | Bosnia and Herzegovina | lane L, checked | enrichable |
| 8df8659c-49be-4a66-b25a-ecbf96541515 | Bosnian Pyramid of Love | Bosnia and Herzegovina | lane L, **unchecked** (in `mass-2026-09-27-03`) | `unchecked-text` until WC finish writes it |

The 43 `unchecked-text` candidates are unchecked March texts (in `mass-03/-04`; Pantelleria's text is one of
that kind too): they become enrichable only when the WC-finish lane has written them. That, and the shared
apply root, is why this lane runs after WC finish.

---

## 2. What a driver must never do

1. Never edit code, never `git checkout`/`stash`/`reset` anything, never commit. A step that needs code that
   is not there stops the part and is reported with the gap's number (section 12).
2. Never run more than **3 web agents at once over all lanes together** (Wikimedia throttles this IP). Every
   answering stage of this lane is a web stage. `disputes.py fetch-categories` and every `import` fetch pages
   too: run them while at most 2 web agents are active.
3. Never reuse an agent: one new agent per batch per stage. A verifier or judge whose name wrote, checked or
   verified a site of the run is refused by the import.
4. Never run a `read`, an export, an import, a `build` or a `judge-export` twice for one run or round: each
   is done once (`read` and `build` overwrite their files without asking; a plan built again after its
   judge is no longer the judged one). Never run `disputes.py candidates` or `fetch-categories` again once
   DS-6 has exported: the research prompts are built from `CANDIDATES.jsonl`, and the import no longer
   rebuilds them from a changed file. Never hand-edit `ROUNDS.jsonl`, `ANSWERS.jsonl`, `VERIFIED.jsonl`,
   `DRAFTS.jsonl`, `FINAL.jsonl`, `WC4.jsonl`, `CANDIDATES.jsonl`, `DISPUTES.jsonl`,
   `DISPUTE_DEFECTS.jsonl` or a recorded answer.
5. Never write without the day's backup and restore drill (W-1). Never accept a step with a deviation.
   Never add an `--allow-stamp` pattern that covers `phase4wc:` stamps. Never delete a `STOPPED.json`.
6. Never run `write_gate4.py --group WC` (its dry run included: it renders the plan's batch directories into
   the apply root) between another lane's first gate run and its `--accept`: the apply root is one, and
   `--apply` writes every open batch of every named plan. From this lane's W-4 to its W-8 no other lane
   runs the WC gate either. Never run a lane that writes `unified_sites.raw_data` (a WB card step, a
   field-provenance step) on the same sites while a WC step is being applied.
7. Never name `pilot-2026-09-27` or `pilot-2026-09-27b` in `--wc-plan` (failed pilots), never a pilot of this
   lane whose `judge/RESULT.json` says `passed: false`, never a run whose batches are not in the apply root
   except the one being written.
8. Never fill a site by hand. A site the writer leaves without sentences, or whose text verification empties,
   stays without a description (D22): no card, no Short.
9. Never treat HTTP 403 or 429 as a finding. `web.archive.org` answers 429 to this network (AS-level block):
   no agent quotes an archived page.
10. Never un-retire a D50 site before its lane-E dispute text exists and its card is cleared (UR-1; no card
    run and no new card for the six: O17, D147), never give the Baltic
    Sea Anomaly a country or a `/sites/` route (D84, D149), never force a D50 site the adjudicator did not
    confirm as a dispute.
11. Never start an export when `df -h /c` shows less than 10 GB free (D135): stop and report.
12. No MiniMax, no mcode, no calibration run, no seal, no `calibrate_claude.py` command.

---

## 3. Variables, files, roles

Shell state does not persist between tool calls. Create this file once and start **every** call with
`cd /c/PythonProjects/AncientMap && . output/remediation/final-2026-10-08/drivers/wn-and-disputes/env.sh`:

```bash
# output/remediation/final-2026-10-08/drivers/wn-and-disputes/env.sh
PY=./.venv/Scripts/python.exe
M=output/remediation
RUNS=$M/wc_runner/runs
DSR=$M/wc_runner/dispute_runs/disputes-2026-11     # the dispute screen's run: NOT under $RUNS (its SUMMARY.json has no "plan")
H=$M/handoff
L=$M/logs/p4wc
ROOT=$M/logs/_write_apply_p4wc
DRV=$M/final-2026-10-08/drivers/wn-and-disputes
WIKI=$M/final-2026-10-08/wiki_cache
C="$PY scripts/remediation/wc/cli.py"
D="$PY scripts/remediation/wc/disputes.py"
OH="$PY scripts/remediation/opus_handoff.py"
G="$PY $M/tools/write_gate4.py --group WC"
V="$PY $M/tools/verify_writes4.py --lane p4wc --allow-stamp wb-teaser-prov-% --allow-stamp wb-card-exact-s%"
U="$PY scripts/remediation/mechanical/scope_unretire.py"
A="$PY scripts/remediation/mechanical/apply.py"
MW="$PY scripts/remediation/mechanical/teaser.py"        # part UR, after the merge of build/track-b
CY="$PY scripts/remediation/mechanical/country_d84.py"   # part UR, after the merge of build/track-b
last_batch() { $PY -c "
import glob, json, os
last = 0
for f in glob.glob('output/remediation/wc_runner/runs/*/SUMMARY.json'):
    plan = json.load(open(f, encoding='utf-8')).get('plan') or {}
    if plan.get('last'):
        last = max(last, int(plan['last'][3:]))
for d in glob.glob('output/remediation/logs/_write_apply_p4wc/p4wc-*'):
    last = max(last, int(os.path.basename(d)[5:]))
print(last)"; }
chain() { $PY -c "
import glob, json, os, sys
root = 'output/remediation/logs/_write_apply_p4wc'
found = []
for s in glob.glob('output/remediation/wc_runner/runs/*/SUMMARY.json'):
    plan = json.load(open(s, encoding='utf-8')).get('plan') or {}
    if not plan.get('first'):
        continue
    n = int(plan['first'][3:])
    run = os.path.dirname(s).replace(os.sep, '/')
    if os.path.isdir(f'{root}/p4wc-{n:04d}') or os.path.basename(run) in sys.argv[1:]:
        found.append((n, run))
print(' '.join(f'--wc-plan {run}/WC4.jsonl' for n, run in sorted(found)))" "$@"; }
mkdir -p $DRV/briefs $DRV/logs $DRV/voided $L
```

`chain <run>` prints the `--wc-plan` arguments: every run whose first write batch is in the apply root, in
batch order, plus the named run. Tested today: it prints `pilot-2026-09-27c`, `mass-2026-09-27-01`,
`mass-2026-09-27-02`, `defects-a1-2026-11-06` and leaves the two failed pilots out; `last_batch` prints
4403. Later the chain also holds the runs other lanes wrote in between (`wn-d57-*`, `mass-03/-04/-05`,
the defect runs): that is right, the gate wants every plan of the apply root named. A run whose plan is
empty (`SUMMARY.json` `plan.batches` 0) is never in the chain, even when named: it has nothing to write.

`last_batch` is read immediately before every `build`, and no two builds of any lane run at the same time:
the batch numbers are one space for all WC plans.

Do not put Python with backslashes into a heredoc in this shell (the heredoc eats them); the snippets below
use none.

**Runs and handoffs of this lane** (fixed names, so the state is read from disk by `ls`):

| part | run directory | handoff directories under `$H` |
| --- | --- | --- |
| WN pilot | `$RUNS/wn-2026-11-pilot` | `wn-2026-11-pilot-w`, `-verify`, `-verify2`, `-judge` |
| WN rest | `$RUNS/wn-2026-11-rest` | `wn-2026-11-rest-w`, `-verify`, `-verify2` |
| WN sweep | `$RUNS/wn-2026-11-sweep` | `wn-2026-11-sweep-w`, `-verify`, `-verify2` |
| dispute screen | `$DSR` | `dispute-2026-11-r`, `dispute-2026-11-a` |
| repair pass | `$RUNS/disputes-repair-2026-11` | `disputes-repair-2026-11-r1`, `-r2`, `-verify`, `-verify2` |
| second check | `$RUNS/disputes-adv-2026-11` | `disputes-adv-2026-11-r1`, `-r2`, `-verify`, `-verify2` |
| lane-E pilot | `$RUNS/enrich-disputes-2026-11-pilot` | `enrich-disputes-2026-11-pilot-w`, `-verify`, `-verify2`, `-judge` |
| lane-E rest | `$RUNS/enrich-disputes-2026-11-rest` | `enrich-disputes-2026-11-rest-w`, `-verify`, `-verify2` |

**Roles** (`scripts/remediation/roles.py`, read 2026-11-10; all `claude-fable-5-2`, standing by owner
decision D153/D154):

| stage | role | effort | web | agent name the brief prints |
| --- | --- | --- | --- | --- |
| WN write round | `fact_checker` | high | yes | `fable-write-wn-000N` |
| list-run check round (RP) | `fact_checker` | high | yes | `fable-check-r1-wc-000N` (re-ask round: `-r2-`) |
| verify, verify2 of WN and list runs | `wc_web_verifier` | high | yes | `fable-wc-verify-000N`, `fable-wc-verify2-000N` |
| judge of a pilot | `pilot_judge` | xhigh | yes | `fable-wc-judge-judge-000N` |
| dispute research | `field_researcher` | high | yes | `fable-dispute-ds-000N` |
| dispute adjudication | `adversarial` | high | yes | `fable-adjudicate-da-000N` |
| second check of a kept asserting sentence | `wc_adversarial` | high | yes | `fable-check-r1-wc-000N` |
| lane-E write round | `enrich_writer` | high | yes | `fable-enrich-we-000N` |
| lane-E verify, verify2 | `web_verifier` (the shared one) | high | yes | `fable-wc-verify-000N` |

---

## 4. Preflight (run all of it before WN-1; P-3 to P-5 again before every export and every write, P-6 before every import)

| # | command | pass |
| --- | --- | --- |
| P-1 | `$C read --help >/dev/null && $D candidates --help >/dev/null && echo ok` | prints `ok`. A traceback means the Fable switch of `roles.py`/`opus_handoff.py` is mid-edit: note it, wait, try again. |
| P-2 | `$PY -c "import sys; sys.path[:0]=['scripts/remediation','.']; import roles as R; from wc import enrich as E; print({n: R.role(n).model for n in ('fact_checker','wc_web_verifier','pilot_judge','field_researcher','adversarial','wc_adversarial','enrich_writer','web_verifier')}); print(E.writer_standing(E.CALIBRATION_ROOT))"` | every role `claude-fable-5-2`; the last line names `owner decision D153`. (`enrich.require_writer_calibration` alone refuses: its Sonnet verdict is void. `writer_standing` is in the working tree, uncommitted, on 2026-11-10.) |
| P-3 | `df -h /c` | at least 10 GB free (D135). Today it moved between 13 and 39 GB. This lane needs about 3 GB (about 10 MB per asked site, run and handoff together, measured on `defects-a1`: 660 MB for 64 sites; 23 MB per `read`). |
| P-4 | `test -f $WIKI/INDEX.jsonl && echo ok` | `ok` (a brief refuses to print without it). |
| P-5 | the state snippet below | `pending step: False`, `stopped: []`, and every run of another lane `accepted` or `empty plan` (today `mass-2026-09-27-03`, `-04`, `-05` and `defects-2026-10-02` are `NOT BUILT`). A run of another lane that is `NOT BUILT` or `BUILT, NOT ACCEPTED` and that its own driver's `NOTES.md` does not name as failed or abandoned: that lane is not done. Stop and report `blocked: <lane>` (D151 order; shared apply root; for the WC-finish runs `blocked: WC finish`). `pilot-2026-09-27` and `-27b` always show `BUILT, NOT ACCEPTED`: failed pilots, ignore. This lane's own runs show their own state (a failed pilot of this lane stays `BUILT, NOT ACCEPTED`: say so in `$DRV/NOTES.md`). |
| P-6 | `curl -s -o /dev/null -w '%{http_code}' https://en.wikipedia.org/wiki/Special:BlankPage` | `200`. A `429` means Wikimedia throttles: start no agent and no import. |
| P-7 | `grep -e '^. 8 ' -e '^. 9 ' -e '^. 10 ' output/remediation/final-2026-10-08/drivers/STATUS.md` | blocks 8 (D14 part B), 9 (D20) and 10 (WC finish) `done`. Block 10 not `done`: `blocked: WC finish`. Block 8 or 9 not `done` and the orchestrator starts WN anyway: create `$DRV/wn-hold-identity.txt` first with the six ids of section 1.1 that wait for D14 or D20, one per line (`036346d9-313c-4fcd-9649-1aaba368e72e`, `221d4702-9626-4430-a71f-d5b70bcb9d4e`, `40acede4-eb32-4515-9ca4-b44145280678`, `417b5d77-c70a-40ad-adad-7f92ef1a0544`, `54dc63d1-d88f-4d40-976b-460b203a07ef`, `58a5a5b2-735a-4fda-bf2d-52e723fd86bc`); WN-2 leaves them out and the sweep (WN-13) asks them later. |
| P-8 | before DS-3 and before EN-1: `grep -c 'NAMED_SIGNAL = ' scripts/remediation/wc/disputes.py; grep -c 'def cmd_briefs' scripts/remediation/wc/disputes.py; grep -c 'dispute-one-position' scripts/remediation/wc/cli.py; grep -c 'MAX_APPENDED' scripts/remediation/mechanical/identity_lanes.py; grep -c 'DISPUTE_UNWRITTEN' scripts/remediation/wc/cli.py; $D briefs --help >/dev/null && echo briefs` | `1`, `1`, `3`, `2`, `4`, `briefs` (measured on `build/track-b` at `5abf8da`, the review of `d008775`; the five greps printed `0`, `0`, `0`, `0`, `0` in the main checkout on 2026-11-11, before the merge, where `briefs` is no command yet): the tree holds the merge of build/track-b (G1, G2, G3 and their review). A `0` in any line: the merge is not in the tree (a `0` in the fifth line only: the tree holds `d008775` without its review `5abf8da` - part EN does not start on it either: that build writes a dispute site that kept neither position, which locks the site out of its dispute text). DS can then run only without the named site (DS-3 says how), and part EN does not start: report `blocked: merge of build/track-b`. |
| P-9 | before UR-1: `grep -c 'D50_CLEAR_REASON = ' scripts/remediation/mechanical/teaser.py; grep -c 'def country_d84_lane' scripts/remediation/mechanical/identity_lanes.py; grep -c 'd84-country-not-cleared' scripts/remediation/mechanical/scope_unretire.py; grep -c 'def card_judged_sql' scripts/remediation/mechanical/identity_lanes.py; grep -c 'row-not-retired' scripts/remediation/mechanical/country_d84.py; $MW d50-clear --help >/dev/null && $CY --help >/dev/null && echo ur` | `1`, `1`, `2`, `1`, `3`, `ur` (measured on `build/track-b` at `158a9d9`, the review of `1eb2f73`; the greps printed `0` in the main checkout on 2026-11-11, before the merge, where `d50-clear` is no command and `country_d84.py` no file yet): the tree holds G4 and G5 and their review. A `0` in any line or no `ur`: part UR does not start, report `blocked: merge of build/track-b` (a `0` in the second, fourth or fifth line only: the tree holds `1eb2f73` without its review - part UR does not start on it either: that build shows a D50 site with a card an undone clear put back, and its country lane has one fixed stamp and a reversal that does not ask whether the site is retired). |

```bash
$PY - <<'EOF'
import json, glob, os
root = 'output/remediation/logs/_write_apply_p4wc'
acc = {b for f in glob.glob(root + '/ACCEPTED/step-*.json') for b in json.load(open(f, encoding='utf-8'))['batches']}
print('pending step:', os.path.exists(root + '/STEP.json'))
print('stopped:', glob.glob(root + '/p4wc-*/STOPPED.json'))
print('last accepted step:', os.path.basename(sorted(glob.glob(root + '/ACCEPTED/step-*.json'))[-1]))
for run in sorted(glob.glob('output/remediation/wc_runner/runs/*/POPULATION.json')):
    run = os.path.dirname(run)
    name = os.path.basename(run)
    if not os.path.exists(run + '/SUMMARY.json'):
        print(name + ': NOT BUILT'); continue
    ids = [json.loads(l)['batch_id'].replace('p4-', 'p4wc-') for l in open(run + '/WC4.jsonl', encoding='utf-8')]
    state = 'empty plan' if not ids else 'accepted' if all(i in acc for i in ids) else 'BUILT, NOT ACCEPTED'
    print(name + ':', (ids[0] + '..' + ids[-1]) if ids else None, state)
EOF
```

---

## 5. The stage loop (SL): how every answering stage is driven

A lane command exports a stage into a handoff directory `HO` (new, empty); the export prints `questions` and
`batches`. The lane has no `agents` command: the driver prints one brief per batch.

1. **Batches**: `ls $HO` (directories `wn-0001`, `verify-0001`, `judge-0001`, `ds-0001`, `da-0001`,
   `wc-0001`, `we-0001`, ...). A batch is answered when `$HO/<batch>/<stage>/` holds as many `*.answer.json`
   as `*.prompt.txt`.
2. **Brief** per open batch, saved to `$DRV/briefs/<run>-<batch>.md`, with the stage's brief command:
   `$C brief | verify-brief | judge-brief --run-dir RUN --handoff HO --batch-id B`, or
   `$D brief | adjudicate-brief --run-dir $DSR --handoff HO --batch-id B`.
3. **One new agent per batch**: model `claude-fable-5-2`, the role's effort (section 3), web tools on. Its whole
   prompt is this head plus the brief:

   > Working directory: C:/PythonProjects/AncientMap (run every command from there, bash). Python:
   > ./.venv/Scripts/python.exe. You are an answering agent of the Ancient Nerds remediation, run RUN,
   > stage STAGE, role ROLE, model claude-fable-5-2. Follow the brief below exactly; it is the lane's own
   > brief for this batch. Write only into your batch's scratch directory and record through
   > opus_handoff.py as the brief says; touch no other file; no git command. web.archive.org answers HTTP
   > 429 to this network: quote no archived page. At the end report how many answers you recorded and any
   > problem. --- BRIEF --- (the brief) --- END BRIEF ---

   At most 3 web agents at once over all lanes.
4. **Validate**: `$OH validate --dir $HO` prints `{"ok": true, "questions": n, "answered": n, "missing": [],
   "stale": [], "malformed": [], "orphans": []}` and exits 0 (exit 1 while `ok` is false).
   - `missing` not empty (an agent stopped): a **new** agent gets the same brief plus one line: "Answer only
     the labels X, Y. Record with `--answered-by <the brief's name>b` and use the scratch directory
     `<the brief's scratch>b`."
   - `malformed` or `stale`, or an import that names an answer as malformed ("delete the answer file and
     have the batch agent answer it again"): move that `*.answer.json` to `$DRV/voided/` (never delete it)
     and re-ask the label the same way. An answer is written once: a second, different answer is refused
     while the first file is still there.
   - `orphans` (an answer file no question asks for, e.g. recorded under a wrong label): move it to
     `$DRV/voided/`.
5. **Import** with the stage's import command. It prints one JSON object and `WC_EXIT=0`, `JUDGE_EXIT=0` or
   `DISPUTE_EXIT=0`. `REFUSED: ...` with exit 1 names the cause; nothing was recorded.
6. Append one line to `$DRV/NOTES.md`: UTC time, the stage, questions, answers, the import's counts.

Count the lane's answers at any time: `find $H/wn-2026-11-* $H/dispute-2026-11-* $H/disputes-*-2026-11-* $H/enrich-disputes-2026-11-* -name '*.answer.json' | wc -l`.

---

## 6. Part WN: texts for the sites without a description

Kind `wn`: round 1 is a **write** round (2 to 6 sentences per site, each on verbatim quotes, or no sentence),
then WC's verification, build, the pilot's judge, the write. Start only when the preflight passes.

**WN-1 Read.** Done when `$RUNS/wn-2026-11-pilot/READ.json` exists.
`$C read --run-dir $RUNS/wn-2026-11-pilot` : one read-only production SELECT; writes `ROWS.jsonl` (about
23 MB) and `READ.json`; prints `{"read_at", "rows": 5004-ish, "sha256"}`.

**WN-2 Population, exclusion, pilot size, cost checkpoint.** Done when `$DRV/wn-exclude.txt` exists. Left
out: the sites of the D13 modern-town funnel (D13 asks every funnel site after this lane and rewrites its
text; today Çatalat Viranşehir Antik Kent and Naveta Biniac), any `retired` row the code would ask (a row the
D57 lane inserted and writes itself), and the ids of `$DRV/wn-hold-identity.txt` when P-7 made that file.
Sites D14 part B or D20 retired are out by themselves.

Create the helper once (a driver file, not repository code), then run it:

```bash
cat > $DRV/wn_population.py <<'EOF'
import json, os, sys
from pathlib import Path
sys.path[:0] = ['scripts/remediation', '.']
from wc import cli
from phase3.run import read_jsonl
run = Path('output/remediation/wc_runner/runs') / os.environ['RUN']
drv = Path('output/remediation/final-2026-10-08/drivers/wn-and-disputes')
sweep = os.environ.get('SWEEP') == '1'   # the sweep leaves out retired rows only
rows = read_jsonl(run / 'ROWS.jsonl')
asked, listed = cli.population(rows, excluded=set(), earlier=set(), kind='wn')
pop = {e['site_id'] for e in asked}
status = {r['id']: r['scope_status'] for r in rows}
funnel = {json.loads(l)['id'] for l in open('output/remediation/final-2026-10-08/identity/IDENTITY_FUNNEL.jsonl', encoding='utf-8') if l.strip()}
hold = drv / 'wn-hold-identity.txt'
held = {l.strip() for l in hold.read_text(encoding='utf-8').splitlines() if l.strip()} if hold.exists() else set()
staged = {i for i in pop if status[i] == 'retired'}
d13 = set() if sweep else pop & funnel
other = set() if sweep else (pop & held) - d13 - staged
excl = sorted(d13 | staged | other)
out = drv / ('wn-exclude-sweep.txt' if sweep else 'wn-exclude.txt')
out.write_text(''.join(i + chr(10) for i in excl), encoding='utf-8', newline=chr(10))
n = len(pop) - len(excl)
print('empty sites the code asks:', len(pop), '| left out: D13 funnel', len(d13), '- retired', len(staged), '- identity hold', len(other),
      '| population N:', n, '| pilot size P:', min(20, n), '| stale-keys:', len(listed.get('stale-keys', [])),
      '| projected answers:', round(2.15 * n + 17))
EOF
RUN=wn-2026-11-pilot $PY $DRV/wn_population.py
```

Today it prints `empty sites the code asks: 40 | left out: D13 funnel 2 - retired 0 - identity hold 0 |
population N: 38 | pilot size P: 20 | stale-keys: 0 | projected answers: 99` (with the hold file: N 33, 88).
Read `N` and `P` from the line. `N` = 0: nothing to do, go to section 9. `stale-keys` above 0: a site carries
a WC key without a text (another lane's broken state); it is never asked; report its id.
**Checkpoint:** `projected answers` above 250 (D145's 200 plus 25 %; reached from `N` = 109): report `N` and
the projection to the orchestrator and export only on its word.

**WN-3 Export the pilot.** Done when `$RUNS/wn-2026-11-pilot/SITES.jsonl` exists.
`$C export --run-dir $RUNS/wn-2026-11-pilot --handoff $H/wn-2026-11-pilot-w --wn --pilot P --seed 20261110 --exclude $DRV/wn-exclude.txt --batch-size 5`
Prints `{"round": 1, "questions": P, "batches": ceil(P/5), "population": N, ...}`; `listed` shows `excluded`
with the number WN-2 left out. Refused "a WN pilot draws ... sites": `P` is not `min(20, N)`; use the number
the message names. The 5 sites a batch of this export hold for every later round of the run (verify, judge).

**WN-4 Write round.** SL with `$C brief --run-dir $RUNS/wn-2026-11-pilot --handoff $H/wn-2026-11-pilot-w --batch-id wn-000N`.
Role `fact_checker`, high, web, 5 sites a batch, `P` answers (4 batches for 20). Each agent checks its own
answers with `cli.py check-answer` (the brief says how) and records them.
Import: `$C import --run-dir $RUNS/wn-2026-11-pilot --handoff $H/wn-2026-11-pilot-w` : fetches every
quoted page itself into `$RUNS/wn-2026-11-pilot/pages/`, writes `round-1/ANSWERS.jsonl` and `DRAFTS.jsonl`,
prints `answers`, `sentences`, `verdicts`, `sites_without_sentences`. Done when `round-1/ANSWERS.jsonl`
exists. No re-ask exists in a write round: a sentence whose quote the import does not find is dropped.

**WN-5 Verify.** `$C verify-export --run-dir $RUNS/wn-2026-11-pilot --handoff $H/wn-2026-11-pilot-verify`
prints `questions` = the sites that kept a sentence. SL with `$C verify-brief ... --batch-id verify-000N`,
role `wc_web_verifier`, high, web, new agents. Import: `$C verify-import --run-dir $RUNS/wn-2026-11-pilot --handoff $H/wn-2026-11-pilot-verify`
prints `verdicts`, `outcomes`, `to_verify2`. Done when `verify/round-1/VERIFIED.jsonl` exists.
Refused "nothing to verify at verify - no site's check kept a sentence; build": every site ended empty. In
the pilot: it measured nothing; treat it as a failed pilot (WN-8, last case). In the rest or the sweep: go to
WN-7; the build records the empty sites and plans nothing.

**WN-6 Verify2**, only when `to_verify2` > 0, once: the same two commands with `--handoff $H/wn-2026-11-pilot-verify2`,
briefs `--batch-id verify2-000N`, new agents again. Done when `verify/round-2/VERIFIED.jsonl` exists.

**WN-7 Build.** `$C build --run-dir $RUNS/wn-2026-11-pilot --first-batch $(( $(last_batch) + 1 ))`
writes `FINAL.jsonl`, `SUMMARY.json`, `WC4.jsonl` (20 sites a plan batch: one batch). Prints the summary;
`not_planned.empty` lists the sites that stay without a text. Done when `SUMMARY.json` exists. Refused
"verification round N is due": WN-5 or WN-6 is open.

**WN-8 Judge the pilot (whole, never `--sample`).** `$C judge-export --run-dir $RUNS/wn-2026-11-pilot --handoff $H/wn-2026-11-pilot-judge`
(one question per site with at least one written sentence). SL with `$C judge-brief ... --batch-id judge-000N`,
role `pilot_judge`, **xhigh**, web, fresh agents. Import: `$C judge-import --run-dir $RUNS/wn-2026-11-pilot --handoff $H/wn-2026-11-pilot-judge`
writes `judge/RESULT.json` and prints it; the last line is `JUDGE_EXIT=0` (passed) or `JUDGE_EXIT=1`.
Pass marks (code, `J_THRESHOLDS`): 0 kept sentences WRONG with a found quote, at most 5 % UNSUPPORTED, 0
incoherent texts, and at least half of the drawn sites (10 of 20) judged, with at least as many kept
sentences. Never build again after `judge-export`: the verdict is tied to the plan's sha256.
- `JUDGE_EXIT=0`: go on.
- `JUDGE_EXIT=1` with a `REFUSED:` line and no `judge/RESULT.json`: the import was refused (an answer
  missing or malformed, SL step 4), not the pilot. Repair and run `judge-import` again.
- `JUDGE_EXIT=1` with `"passed": false`: read `failures`. The pilot's plan is never written and never named.
  Run **one** new pilot from WN-1 with the names `wn-2026-11-pilot2` (`RUN=wn-2026-11-pilot2` in WN-2) and
  `--seed 20261111` (a fresh read; no `--after`). If that fails too: stop the part and report both
  `RESULT.json` `failures`. Wherever this playbook says `wn-2026-11-pilot` afterwards, the passed pilot's
  name is meant.

**WN-9 Write the pilot**: section 7 with `RUN=wn-2026-11-pilot`. Then section 8.

**WN-10 The rest, one chunk** (no judge of its own). Start it only after the pilot is accepted.
`$C read --run-dir $RUNS/wn-2026-11-rest`
`$C export --run-dir $RUNS/wn-2026-11-rest --handoff $H/wn-2026-11-rest-w --wn --after $RUNS/wn-2026-11-pilot --exclude $DRV/wn-exclude.txt --batch-size 5`
(`--after` names the passed pilot: its sites, the empty ones too, are not asked again. The sites of a failed
first pilot that the second did not draw are asked here.)
Refused "nothing to ask - the population is empty": the pilot was the whole population; skip to WN-12.
Otherwise WN-4 to WN-7 with the rest's names (`N - P` write answers), then section 7 with
`RUN=wn-2026-11-rest`, then section 8. A build that plans nothing (`plan.batches` 0: every site ended
empty) has no write: go to WN-12.

**WN-11** (only if the rest plans more than 100 sites) `--apply --step 100` writes one step of at most
100 sites; accept it (W-7, W-8), recount (W-9), and run W-5 to W-9 again for the next step. Section 8 runs
once, after the last step.

**WN-12 Lists.** Done when the two files exist.

```bash
$PY - <<'EOF'
import json, glob, os
empty, written = [], []
for f in sorted(glob.glob('output/remediation/wc_runner/runs/wn-2026-11-*/FINAL.jsonl')):
    result = f.replace('FINAL.jsonl', 'judge/RESULT.json')
    if os.path.exists(result) and not json.load(open(result, encoding='utf-8'))['passed']:
        continue  # a failed pilot: nothing of it was written, its sites were asked again
    for line in open(f, encoding='utf-8'):
        row = json.loads(line)
        (written if row['planned'] else empty).append(row['site_id'] + ' ' + row['name'])
drv = 'output/remediation/final-2026-10-08/drivers/wn-and-disputes/'
open(drv + 'WN_WRITTEN.txt', 'w', encoding='utf-8', newline=chr(10)).write(chr(10).join(written) + chr(10))
open(drv + 'WN_EMPTY.txt', 'w', encoding='utf-8', newline=chr(10)).write(chr(10).join(empty) + chr(10))
print('written', len(written), 'stay empty', len(empty))
EOF
```

`WN_EMPTY.txt` is final (D22). `WN_WRITTEN.txt` goes to the card lane: a new text has no card (D147: none now),
except the 12 sites that hold a WB card of wave a1 (section 1.1): D81 says "then rewrite the card", so those
12 are the card lane's next `teaser/run.py select --sites` list.

**WN-13 Sweep, after D13 has written** (and after D14 part B and D20, if WN-2 held sites for them). It asks
the sites WN-2 left out that are still shown and empty, and every site another lane cleared since (the
repair pass of section 10 among them); only `retired` rows stay out.
`$C read --run-dir $RUNS/wn-2026-11-sweep`
`RUN=wn-2026-11-sweep SWEEP=1 $PY $DRV/wn_population.py` (writes `$DRV/wn-exclude-sweep.txt`; its `N` does
not know `--after`: the number asked is the export's `questions`)
`$C export --run-dir $RUNS/wn-2026-11-sweep --handoff $H/wn-2026-11-sweep-w --wn --after $RUNS/wn-2026-11-pilot --after $RUNS/wn-2026-11-rest --exclude $DRV/wn-exclude-sweep.txt --batch-size 5`
(`--after` is given once per run; leave out a run that does not exist.) Then WN-4 to WN-7, section 7 with
`RUN=wn-2026-11-sweep`, section 8, and WN-12 again. "nothing to ask" ends the part.

---

## 7. The write procedure (lane WC, group `WC`; used by WN, RP and EN)

Lane names: writer group `WC`, apply root `$ROOT`, acceptance lane `p4wc`, run stamps
`phase4wc:p4wc-NNNN:chunk-0001`, journal `test_id` `WC/description` and `WC/raw_data` (two journal rows per
site; a text the repair pass empties is journalled `WC/description-clear` and `WC/raw_data-clear`). Step
numbers are the apply root's: `ls $ROOT/ACCEPTED | tail -1` is the last accepted one (13 today).

The generic sequence "plan, emit, rehearse, probe-guards, apply, read-back, rehearse-rollback, accept" maps
here to: `build` (the plan), the gate's dry run (renders the statements), `--rehearse`, `--apply --step 100`
(preflight, write, per-row read-back, and the inverse proof: `ROLLBACK.sql` run ending in ROLLBACK),
`verify_writes4.py` (the acceptance), `--accept`. The WC gate has no `--probe-guards` command.

`RUN` is the run being written. Shell state does not persist: begin every call of this section with
`RUN=<run>; PLANS=$(chain $RUN)`. A run whose `SUMMARY.json` says `plan.batches` 0 has nothing to write:
skip sections 7 and 8 for it (`chain` does not print its plan).

| # | command | done / pass | refused or failed |
| --- | --- | --- | --- |
| W-1 | `ssh ancientnerds 'grep VERDICT /var/www/ancientnerds/backups/$(date +%F)_remediation/DRILL_REPORT.txt'`; if it prints nothing: `ssh ancientnerds "cd /var/www/ancientnerds/scripts/remediation && DO_DRILL=1 ./00_backup_and_drill.sh"` | `VERDICT: dump is restorable and matches production row-for-row.` (the script ends `drill PASSED`, exit 0) | non-zero exit: no write today; report |
| W-2 | P-3, P-5 again | no pending step, nothing stopped, no other lane between its first gate run and its `--accept` | stop |
| W-3 | `echo $PLANS` | starts with `.../pilot-2026-09-27c/WC4.jsonl`, ends with `.../$RUN/WC4.jsonl`; a WN rest or sweep has this lane's WN pilot before it, a lane-E rest the lane-E pilot; runs of other lanes written in between are in it | a failed pilot in the list: it must not be there. The list does not end with `$RUN`'s plan: the plan is empty, nothing to write. |
| W-4 | `$G $PLANS > $DRV/logs/$RUN-gate-dry.log 2>&1; tail -4 $DRV/logs/$RUN-gate-dry.log; grep -e '^pilot passed' -e '^lane [NE]:' $DRV/logs/$RUN-gate-dry.log` | last line `WRITE_EXIT=0`; the line `pilot passed: ...` names `pilot-2026-09-27c` and, for a WN plan, this lane's WN pilot (for a lane-E plan the lane-E pilot); `lane N: the live API runs ..., which contains 7d7a1f00b758 (NO_LICENCE_LANES)`; for a plan that appends to a W or S text also `lane E: ... contains 9bdda00e8469 (ENRICHMENT_LANE)`; `open batches:` is the number of batches this run plans (`plan.batches` of its `SUMMARY.json`, less a batch whose every site the gate refused) and never more. The dry run renders the run's batch directories into `$ROOT`: from here to W-8 the plan is named by every WC gate run. | `open batches:` above this run's: another run has unwritten batches in the chain; `--apply` would write them too: stop, report. `holds write batches of a WC plan not named here`: a plan `chain` cannot see is in the root: stop (rule 6). `the first WN plan named is the pilot's`: the pilot is missing from `$PLANS`. `does not contain ...: Deploy first`: stop, report. `git cannot relate the live API's commit`: this checkout does not know the deployed commit: `git fetch origin`, then W-4 again. `refused by rule: {'moved-since-check': n}`: n sites moved since the read and are not written (the sweep asks an empty one again); go on. |
| W-5 | `$G $PLANS --rehearse > $DRV/logs/$RUN-gate-rehearse.log 2>&1; tail -3 $DRV/logs/$RUN-gate-rehearse.log` | one JSON line per open batch with `"rehearsed": true, "blocked": []`, then `every open batch rehearsed`, `WRITE_EXIT=0` | `break the provenance or clear invariant`, or any `WRITE_EXIT=1`: stop, report the log. Nothing was written; the run's batch directories stay rendered in `$ROOT` (say so: every other lane's WC gate must name this plan until the orchestrator decides). |
| W-6 | `$G $PLANS --apply --step 100 > $DRV/logs/$RUN-gate-apply.log 2>&1; tail -3 $DRV/logs/$RUN-gate-apply.log` | per batch `rows_written` = `rows_planned`, `read_back` and `inverse` both "N/N row(s) hold the planned value, N journal row(s)", `rollback_rows_left: 0`; `STEP COMPLETE: s site(s) written in k batch(es)`; `WRITE_EXIT=0` | `STOPPED.json` in a batch directory: a row moved between the gate's read and the transaction; nothing of that batch was written. Read the file, report; a person reads it before any next run. |
| W-7 | `ACC=$L/accept-$RUN.log` (a later step of the same run: `accept-$RUN-2.log`, ...); `$V --plan $ROOT/LANE_PLAN.jsonl > $ACC; tail -2 $ACC` (stdout only: no `2>&1`, the file must start with the lane line) | `RESULT: 0 deviation(s)` and `ACCEPT_EXIT=0` | any deviation: do not accept. `CHANGED LATER ... <stamp>` by a documented one-key lane other than the two allowed patterns: report the stamp; a new `--allow-stamp` is added only where a runbook names it (as `CARD_DESCRIPTIONS.md` 5.9 did for `wb-card-exact-s%`). Checked today: since 2026-11-01 only `phase4wc:` and `wb-teaser-prov-` wrote `description` or `raw_data`; the lanes that run before this one (D57, D14 part B, D20) may add stamps. |
| W-8 | `$G --accept $L/accept-$RUN.log` (the file W-7 wrote for this step) | `ACCEPTED step NN: s site(s) in k batch(es)`; `$ROOT/ACCEPTED/step-00NN.json` exists, `STEP.json` is gone | it names what the log lacks |
| W-9 | the journal recount below, once per written batch `NNNN` | per batch one `description` and one `raw_data` line, each count = the batch's sites (the gate log's `sites`) | a count that differs: report; never repair by hand |

```bash
ssh ancientnerds "docker exec ancient_nerds_db psql -U ancient_map -d ancient_map -At -c \"SELECT run_stamp, column_name, count(*), count(DISTINCT site_id_ref) FROM remediation_change_log WHERE run_stamp LIKE 'phase4wc:p4wc-NNNN:%' GROUP BY 1,2 ORDER BY 1,2\""
```

More open batches than 100 sites: W-6 writes the batches that fit into 100 sites and stops; after W-9 run
W-5 to W-9 again (the next step, its own acceptance file).

**Undo** (the orchestrator's call after a reported deviation, never a driver's reflex):
`$PY scripts/remediation/phase4/revert4.py --stamp-like 'phase4wc:p4wc-NNNN:%' --rehearse`, then the same
with `--apply` (`--site <id>` limits it to one site); a step reverted before its acceptance is closed with
`$G --close-reverted`.

## 8. After every accepted write (content wave)

| # | command | pass |
| --- | --- | --- |
| X-1 | `ssh ancientnerds "docker exec ancient_nerds_api python -m api.services.rebuild_static"` (about 5 minutes) | exit 0 |
| X-2 | `scp scripts/remediation/static_export_check.py ancientnerds:/tmp/static_export_check.py && ssh ancientnerds "docker cp /tmp/static_export_check.py ancient_nerds_api:/tmp/x.py && docker exec ancient_nerds_api python /tmp/x.py"` | exit 0, 0 differing sites. Exit 1: run X-1 again once, then report. |
| X-3 | IndexNow: Lyra's hourly `indexnow` step announces every site whose journal changed. To send at once: `ssh ancientnerds "docker exec ancient_nerds_api python -c \"from pipeline.indexnow import submit_recent; print(submit_recent())\""` | a number of URLs |
| X-4 | three written sites of the step: `curl -s https://ancientnerds.com/api/sites/<id>` and `curl -s -o /dev/null -L -w '%{http_code} %{url_effective}' "https://ancientnerds.com/site.html?id=<id>"` | the JSON has the new `description` (measured on a lane-N site today: `"descriptionAi": "generated"`, `descriptionCitations` listing the quoted pages); the page answers `200` at `/sites/<country>/<slug>`. This is the first write whose disclosure names Fable: look at one page. |
| X-5 | one line in `$DRV/NOTES.md`: step number, batches, sites, journal counts, the export's time | |

Run it once per written run, after its last step. For X-4 take shown sites: a retired D50 site answers 410
until part UR. The search index (Qdrant) follows by itself: the API reindexes every night at 03:00 UTC.

---

## 9. Part DS: the dispute screen (`scripts/remediation/wc/disputes.py`)

Start after WN-10 is accepted (D151: WC finish, WN, D21). Code screens; a researcher answers per candidate;
an independent adjudicator looks for the reasons it is **not** a dispute; only `dispute` reaches the outputs.

**DS-1** `$C read --run-dir $DSR` . Done when `$DSR/READ.json` exists.

**DS-2** `$D fetch-categories --run-dir $DSR` : about 90 MediaWiki queries (50 titles each, serial; 66 s
when measured), writes `CATEGORIES.json`, prints `{"sites": ~4527, "with_categories": ~4527}` and
`DISPUTE_EXIT=0`. Counts as one web slot. An HTTP error: wait, run again (the file is written only at the
end). `REFUSED: the article '<title>' does not exist`: a stored English title is dead and no option skips
it: stop the part and report the title (measured today: none is missing).

**DS-3** (available after the merge of build/track-b, P-8) The named site first, once:
`printf 'daa1ea4b-c002-4552-a4ef-45d996c6cea6\n' > $DRV/dispute-include.txt` (Pantelleria Vecchia Bank
Megalith, the site D21 names; a driver file, one site id per line). Then
`$D candidates --run-dir $DSR --wiki-cache $WIKI --include $DRV/dispute-include.txt` : writes
`CANDIDATES.jsonl`, prints `candidates` (call it `C`), `by_signal`, `listed`, `categories`,
`wikipedia_texts`, `wiki_min_hits`, `include`. Check before going on: `categories` is the `sites` number of
DS-2 and `wikipedia_texts` is about 4,520 (0 means DS-2 did not run or `--wiki-cache` was left out: the
screen would miss six more of the known names), `by_signal` holds `category`, `by_signal.named` is 1 and
`include.sites` is 1. The named site is a candidate whatever it carries and is researched like any other;
`C` counts it (236 with today's 235).
- `REFUSED: ... cannot be asked (retired | no-description | not-splittable)` or `... is no curated row of
  the read`: the named site cannot be asked on this read (its text was cleared: then it is WN's, or the
  row was retired). Nothing was written. Run the command again **without `--include`** and report the site
  as not asked, with the reason.
- P-8 says the merge is not in the tree: run it without `--include` (the old command) and report
  Pantelleria as not asked (`blocked: merge of build/track-b`).

**DS-4** `$D recall --run-dir $DSR` : the screen against its 17 known names (code only, no model answer);
prints `recall`, `missed`, `named`, `passed`, then `DISPUTE_EXIT=0` for `"passed": true`. Expected today: 16
of 17, `missed` = Pantelleria alone and `named` = Pantelleria (after the merge of build/track-b: a site
asked by name through DS-3's list is no hit of the screen, so it stays in `missed`; `named` says it is
asked all the same). `DISPUTE_EXIT=1` (15 or fewer: one more known name lost its signal, for
example because a lane rewrote its description): the export does not enforce this check, so report `missed`
to the orchestrator and go on only on its word (a missed name is asked only when DS-3's list names it;
adding a name to `$DRV/dispute-include.txt` is the orchestrator's word, never the driver's own repair, and
widening the signals is a code change).

**DS-5 Cost checkpoint, before any answer.** Projected answers of DS to EN = `2.2 * C + 20`. The owner's
estimate for D21 is about 360 (D145); 25 % above it is 450 (D151), which `C` up to 195 keeps. At today's
`C` = 235 the projection is 537: **the checkpoint triggers.** Report to the orchestrator: `C`, `by_signal`,
the projection, the lane's answers so far (section 5), and the measured alternatives of section 1.2
(`--wiki-min-hits 3`: 184 candidates, 425 answers; `4`: 157, 365; the 51 or 78 sites that drop out are
flagged by nothing but two or three controversy words in their Wikipedia article). Go on only on its word:

- "go on as it is": DS-6.
- "narrow to N hits": run DS-3's command again with `--wiki-min-hits N` and the same `--include` (allowed
  until DS-6 exports; it overwrites `CANDIDATES.jsonl`; the named site stays a candidate at every N), then
  DS-4 again, then DS-6.

A line `DS-5 decision: ...` that the orchestrator wrote into `$DRV/NOTES.md` beforehand is that word. Do not
narrow the screen yourself.

**DS-6 Research.** `$D export --run-dir $DSR --handoff $H/dispute-2026-11-r` (5 a batch; prints `questions`
= `C`). SL with `$D brief --run-dir $DSR --handoff $H/dispute-2026-11-r --batch-id ds-000N`, role
`field_researcher`, high, web. Import: `$D import --run-dir $DSR --handoff $H/dispute-2026-11-r` : fetches
every quoted page, checks every quote, writes `RESEARCH.jsonl`, prints the counts of `not-disputed`,
`researched`, `unverified`. Done when `RESEARCH.jsonl` exists.

**DS-7 Adjudication.** `$D adjudicate-export --run-dir $DSR --handoff $H/dispute-2026-11-a` (one question per
`researched` site). SL with `$D adjudicate-brief ... --batch-id da-000N`, role `adversarial`, high, web, new
agents. Import: `$D adjudicate-import --run-dir $DSR --handoff $H/dispute-2026-11-a` prints
`{"dispute": n, "not-a-dispute": m}`, writes `ADJUDICATED.jsonl`. Refused "researched this site": that batch
is answered again by a new agent. Refused "nothing to ask at adjudicate": no site was researched as disputed;
the dispute parts end here with 0 disputes; report.

**DS-8** `$D outputs --run-dir $DSR` : writes `DISPUTES.jsonl` (the briefs), `DISPUTE_DEFECTS.jsonl` (one line
per sentence that states one side as fact) and `SUMMARY.json`; prints `disputes`, `sentences_to_repair`,
`sites_to_repair`.

**DS-9 Report now**: the confirmed disputes by name; each of the six D50 sites with its status (`dispute`,
`not-a-dispute`, `unverified`, `not-disputed`). A D50 site without a `dispute` verdict gets no dispute text
and stays retired (the un-retire skips it `d50-no-dispute-text`). Never force it.

## 10. Part RP: the repair pass (a site-list run, kind `wc-list`)

Only when `sites_to_repair` > 0. The dispute enters the check question as a reported claim; the sentence that
states one side as fact is dropped.

**RP-1** `$C read --run-dir $RUNS/disputes-repair-2026-11`
**RP-2** `$C defect-sites --run-dir $RUNS/disputes-repair-2026-11 --defects $DSR/DISPUTE_DEFECTS.jsonl --out $RUNS/disputes-repair-2026-11/DEFECT_SITES.txt`
prints `sites` and `skipped` (`text-changed-since`: the text moved after DS-1; the asserting sentence of such
a brief is looked for again in EN-2). `sites` 0: nothing to repair, go to section 11.
**RP-3** `$C export --run-dir $RUNS/disputes-repair-2026-11 --handoff $H/disputes-repair-2026-11-r1 --sites $RUNS/disputes-repair-2026-11/DEFECT_SITES.txt --defects $RUNS/disputes-repair-2026-11/DEFECT_SITES.txt.report.json`
(10 a batch, no `--pilot`). The D50 sites are asked although retired.
**RP-4** Check round: SL with `$C brief ... --batch-id wc-000N`, role `fact_checker`, high, web. Import
`$C import --run-dir $RUNS/disputes-repair-2026-11 --handoff $H/disputes-repair-2026-11-r1` prints `to_reask`.
**RP-5** `to_reask` > 0, once: `$C export-reask --run-dir $RUNS/disputes-repair-2026-11 --handoff $H/disputes-repair-2026-11-r2`,
SL, import.
**RP-6** Verify and verify2 as WN-5 and WN-6 (role `wc_web_verifier`), handoffs `disputes-repair-2026-11-verify`, `-verify2`.
**RP-7** `$C build --run-dir $RUNS/disputes-repair-2026-11 --first-batch $(( $(last_batch) + 1 ))` .
`SUMMARY.json` `not_planned` lists `unchanged` and `defect-kept`; `defects_kept` names the asserting sentences
the check kept.
**RP-8** Section 7 with `RUN=disputes-repair-2026-11`, then section 8. (An empty plan, every site
`defect-kept`: nothing to write; go to RP-9.)
**RP-9 Second check of a kept asserting sentence**, only when `defects_kept` of RP-7's `SUMMARY.json` is not
empty, and after RP-8 is accepted (the read must hold the written texts; straight after RP-7 when it
planned nothing):
`$C read --run-dir $RUNS/disputes-adv-2026-11`
`$C defect-kept-sites --run-dir $RUNS/disputes-adv-2026-11 --from $RUNS/disputes-repair-2026-11 --out $RUNS/disputes-adv-2026-11/KEPT.txt`
prints `sites` and `skipped`. `sites` 0 (`KEPT.txt` is empty): no claim stands, the second check is done.
`$C export --run-dir $RUNS/disputes-adv-2026-11 --handoff $H/disputes-adv-2026-11-r1 --sites $RUNS/disputes-adv-2026-11/KEPT.txt --defects $RUNS/disputes-adv-2026-11/KEPT.txt.report.json --adversarial`
(no `--after`, no `--pilot`). Then as RP-4 to RP-8 with this run's names: the check round by the role
`wc_adversarial` (high, web; the brief prints it), the re-ask once when `to_reask` > 0 (handoff
`disputes-adv-2026-11-r2`), verify and verify2 by `wc_web_verifier`, build, section 7 and section 8 when the
build plans a batch (a KEEP of a whole text writes nothing). Last, once:

```bash
$C defect-closure --run-dir $RUNS/disputes-adv-2026-11 > $DRV/logs/disputes-adv.closure.txt   # writes CLOSURE.json; a second run is refused
sed -n '/^### Adversarial second check/,$p' $DRV/logs/disputes-adv.closure.txt | sed '/^WC_EXIT=/d' >> $M/AUDIT_LOG.md
```

`RESOLVED` lines are drops that were written, `REFUTED` lines close the claim on the adversary's quotes.
`AUDIT_LOG.md` is a tracked file: the orchestrator commits it. A site whose asserting sentence both checks
kept cannot take its brief (EN-2 lists it): it goes on the report, unchanged.

## 11. Part EN: both positions appended (lane E, kind `wn-enrich`)

Only when DS-8 printed `disputes` > 0. The commands of EN-2, EN-3, EN-6 and EN-9 are those of the closed
gaps G2 and G3: **available after the merge of build/track-b**. P-8 again before EN-1; a tree without the
merge: do not start this part, report `blocked: merge of build/track-b`. Lane E has never written to
production: W-5 is the first run of its invariants against real data, unless the enrichment lane
(`enrich-d3-*`) wrote before.

**EN-1** `$C read --run-dir $RUNS/enrich-disputes-2026-11-pilot` (a fresh read, after the RP writes).

**EN-2 Which briefs this run can take** (G2's command; it reads only, and writes three driver files).
`$D briefs --run-dir $DSR --for-run $RUNS/enrich-disputes-2026-11-pilot --out $DRV/enrich-pilot.briefs.jsonl`
It decides on the read of EN-1 exactly as the export of EN-3 will (a lane-E run asks the site, and none of
the brief's asserting sentences stands in the text) and writes
- `$DRV/enrich-pilot.briefs.jsonl`: the briefs the run takes, unchanged, in the order of `DISPUTES.jsonl`;
- `$DRV/enrich-pilot.briefs.jsonl.sites.txt`: their site ids, one per line;
- `$DRV/enrich-pilot.briefs.jsonl.held.json`: every other brief with `reason` and `asserting_in_text`.

It prints `briefs`, `usable`, `pilot_size` (call it `P`), `held` (counts by reason), then `DISPUTE_EXIT=0`.
The held file is the report list: `unchecked-text` (WC finish has not written the text), `no-description`
(the repair emptied it: it is WN's next sweep), `no-provenance`, `enriched-before`, `base-not-enrichable`,
`retired`, `no-curated-row`, or `asserting-in-text` (a sentence that states one side as fact still stands;
`asserting_in_text` holds its numbers). `usable` 0: part EN ends here; report. Measured 2026-11-11 on a
fresh read in a temp directory with made-up briefs of the six D50 sites and Pantelleria: 5 usable, 2 held
`unchecked-text` (Bosnian Pyramid of Love, Pantelleria: both wait for WC finish).
`REFUSED: ... has two dispute briefs` or a malformed brief: `DISPUTES.jsonl` is broken; stop, report.
Never cut `DISPUTES.jsonl` by hand, never edit the three files. A dispute site this run must leave out (the
orchestrator names it: a D13 funnel site, an identity-hold site): write its id into `$DRV/enrich-exclude.txt`
(one id per line) and give **both** commands the file - `--exclude $DRV/enrich-exclude.txt` here and at
EN-3 (and at EN-9). Its brief is then held `excluded`. No step of this playbook needs it as written.

**EN-3 Export the lane-E pilot.** `P` is the `pilot_size` EN-2 printed.
`$C export --run-dir $RUNS/enrich-disputes-2026-11-pilot --handoff $H/enrich-disputes-2026-11-pilot-w --enrich --sites $DRV/enrich-pilot.briefs.jsonl.sites.txt --disputes $DRV/enrich-pilot.briefs.jsonl --pilot P --seed 20261110 --batch-size 5`
Prints `questions` = `P`. Refused "... is no site this run asks - disputes.py briefs --for-run writes the
briefs of the sites it does": `--disputes` was given `$DSR/DISPUTES.jsonl` or a subset of another read;
EN-2 again on this run's read (it overwrites its three files), then this command. Refused "sentence(s) ...
are still in the text": the same cause.

**EN-4 Write round.** SL with `$C brief ... --batch-id we-000N`, role `enrich_writer`, high, web, 5 a batch.
Each dispute site gets both positions (`dispute_a`, `dispute_b`) or no sentence; a thin text may take up to 3
facts, any text at most one sourced open question. Import: `$C import --run-dir $RUNS/enrich-disputes-2026-11-pilot --handoff $H/enrich-disputes-2026-11-pilot-w` .

**EN-5 Verify, verify2** as WN-5, WN-6; the role is the shared **`web_verifier`** (the brief prints it), high.

**EN-6 Build; the positions kept** (G3's rule, available after the merge of build/track-b).
`$C build --run-dir $RUNS/enrich-disputes-2026-11-pilot --first-batch $(( $(last_batch) + 1 ))`
The build itself holds D21 now ("the description names both positions"): a site with a dispute brief is
planned only with **both** positions kept. A site whose verification or import left **one** position
without the other is listed in the printed summary's `not_planned` under `dispute-one-position`, one that
kept **neither** position but another new sentence under `dispute-no-position` (beside `unchanged`: no
sentence kept); `FINAL.jsonl` shows each with `planned: false`. Nothing of such a site is written, its open
question included (a write would make the text an enriched one, `enriched-before`, which no later run
asks: the site could never take its dispute text). The plan holds the sites with both positions kept, and
nothing else. Then list both kinds for the report (read-only):

```bash
RUN=enrich-disputes-2026-11-pilot $PY - <<'EOF'
import json, os, sys
sys.stdout.reconfigure(encoding='utf-8')   # site names: the console's own encoding refuses some
one, neither = [], []
for line in open('output/remediation/wc_runner/runs/' + os.environ['RUN'] + '/FINAL.jsonl', encoding='utf-8'):
    row = json.loads(line)
    detail = row['evidence'].get('enrichment') or {}
    if not detail.get('dispute') or row['description'] is None:
        continue
    kept = {detail['classes'][str(d['n'])] for d in row['decisions'] if d['text'] is not None} & {'dispute_a', 'dispute_b'}
    if len(kept) == 1:
        one.append((row['site_id'], row['name'], sorted(kept), 'planned' if row['planned'] else 'not planned'))
    elif not kept:
        neither.append((row['site_id'], row['name'], 'planned' if row['planned'] else 'not planned'))
print('one position kept (must all say not planned):', one)
print('neither position kept (must all say not planned):', neither)
EOF
```

Every site of both lists must say `not planned`. One that says `planned`: the tree does not hold G3 and
its review (P-8); do not judge, do not write this plan; report. Otherwise go on: the plan is judged and
written as it was built. Both lists go on the report and into `$DRV/NOTES.md`: a site of either list has
no dispute text and keeps its text as it is. A D50 site among them stays retired (UR-3 skips it
`d50-no-dispute-text`: the text it holds is no lane-E dispute enrichment; the D50 gate also reads the
positions kept, whatever wrote a text). Such a site is in this run's `SITES.jsonl`, so EN-9's `--after`
does not ask it again: asking it again is a new run on the orchestrator's word (the site is unwritten, so
a new run's `briefs` takes its brief). (With about 40 dispute sentences in a pilot and a verifier that
drops 6-10 % of sentences, expect a few such sites.) The pilot's judge (EN-7) is **not** asked about a
site of either list: its sentences are written nowhere, so they neither count toward the pilot's minimum
nor fail it.

**EN-7 Judge the pilot whole.** As WN-8 (`judge-export`, `judge-brief`, `judge-import`, role `pilot_judge`,
xhigh), handoff `enrich-disputes-2026-11-pilot-judge`. `judge-export` prints `questions`: the sites with a
written sentence less the sites of EN-6's two lists. `REFUSED: ... the pilot measured nothing`: no site is
left to judge (nothing was recorded); that is a failed pilot, go on as for `"passed": false`. Pass marks
`ENRICH_THRESHOLDS`: WN's (the minimum is half of the sites drawn, counted over the judged sites: a pilot
most of whose sites lost a position fails as "measured too little") and **0 open questions the judge finds
INVENTED**. `"passed": false`: one new pilot
`enrich-disputes-2026-11-pilot2` from EN-1 (EN-2 with `--for-run $RUNS/enrich-disputes-2026-11-pilot2
--out $DRV/enrich-pilot2.briefs.jsonl`, those files in EN-3, `RUN=enrich-disputes-2026-11-pilot2` in
EN-6), `--seed 20261111`; a second failure stops the part.

**EN-8 Write**: section 7 with `RUN=enrich-disputes-2026-11-pilot` (W-4 must print a `pilot passed:` line
naming this pilot and, when the plan appends to a W or S text, the `lane E:` line), then section 8. A lane-E
pilot of the enrichment lane (`enrich-d3-*`) written before this one stands before it in the chain and is
named with it; a later one names this pilot.

**EN-9 The rest** (only when EN-2 printed more than 20 `usable`; available after the merge of
build/track-b), after the pilot is accepted:
`$C read --run-dir $RUNS/enrich-disputes-2026-11-rest`
`$D briefs --run-dir $DSR --for-run $RUNS/enrich-disputes-2026-11-rest --after $RUNS/enrich-disputes-2026-11-pilot --out $DRV/enrich-rest.briefs.jsonl`
(the briefs of the sites the pilot did not ask: the pilot's sites are held `earlier-run` or, once written,
`enriched-before`; `usable` 0: nothing is left, go to EN-10)
`$C export --run-dir $RUNS/enrich-disputes-2026-11-rest --handoff $H/enrich-disputes-2026-11-rest-w --enrich --sites $DRV/enrich-rest.briefs.jsonl.sites.txt --disputes $DRV/enrich-rest.briefs.jsonl --after $RUNS/enrich-disputes-2026-11-pilot --batch-size 5`
(no `--pilot`), then EN-4 to EN-6 with the rest's names (`RUN=enrich-disputes-2026-11-rest` in EN-6's
snippet), section 7, section 8. No judge of its own.

**EN-10 Hand-off.** The sites RP and EN wrote (the sites of the accepted plan batches of the repair, the
second check and the lane-E runs) go on the report as `$DRV/DISPUTE_WRITTEN.txt` for the card lane:

```bash
$PY - <<'EOF'
import json, glob, os
runs = 'output/remediation/wc_runner/runs/'
root = 'output/remediation/logs/_write_apply_p4wc'
acc = {b for f in glob.glob(root + '/ACCEPTED/step-*.json') for b in json.load(open(f, encoding='utf-8'))['batches']}
rows = set()
for f in sorted(glob.glob(runs + 'disputes-*-2026-11/WC4.jsonl') + glob.glob(runs + 'enrich-disputes-2026-11-*/WC4.jsonl')):
    for line in open(f, encoding='utf-8'):
        batch = json.loads(line)
        if batch['batch_id'].replace('p4-', 'p4wc-') in acc:   # only what was written and accepted
            rows.update(site['site_id'] + ' ' + site['name'] for site in batch['sites'])
out = 'output/remediation/final-2026-10-08/drivers/wn-and-disputes/DISPUTE_WRITTEN.txt'
open(out, 'w', encoding='utf-8', newline=chr(10)).write(chr(10).join(sorted(rows)) + chr(10))
print('sites written by RP and EN:', len(rows))
EOF
```

(A site the gate refused as `moved-since-check` in W-4 is on the list although unwritten; the card lane's own
read sorts it out.) Every such site's WB card is stale (the `desc_sha256` tie), and D21 says the card asserts
neither side. No card wave runs for them from this lane (D147): whether a card that asserts a side is cleared
or rewritten is the orchestrator's decision, taken on this list.

## 11a. Part UR: the six D50 sites shown again (`scope-unretire-<wave>`)

Per site the un-retire needs, in this order: its lane-E dispute text (EN), its card cleared (UR-1; O17:
"the six cards are cleared the D47 way, so the un-retire needs no new card"), and for the Baltic Sea
Anomaly a `country` of NULL (UR-2; D84, D149: globe only). The commands of UR-1 and UR-2 and the
un-retire's D84 gate are **available after the merge of build/track-b** (commit `1eb2f73`, code gaps G4
and G5; P-9 tells whether the tree has them). A tree without them: do not start this part, report
`blocked: merge of build/track-b`.

Part UR starts when the write step of the last lane-E run that holds a D50 site is accepted and section
8 ran for it (EN-8, and EN-11 if a D50 site is in the rest run) - never between a `read` of the six by
lane E or WC and the acceptance of that run's write (rule 6: a card step writes `raw_data` on the same
sites, and the clear's premise is the description). W-1 (the day's backup and restore drill) before
UR-1's first apply. No agent answers anything in this part.

**UR-1 The six cards are cleared** (lane WB, an owner run the D47 way; runbook
`docs/procedures/CARD_DESCRIPTIONS.md` 5.11 and 5.4). All six, also a D50 site that stays retired (O17).
No card run, no new card (D147). The WB step numbers are one sequence shared with the cards lane:
`$MW plan` refuses while the last WB step is not closed (`step N-1 has no acceptance`) - then wait for
the cards lane's driver, never close its step.

```bash
WAVE=2026-11-NN        # the day's date, fixed once, written into $DRV/NOTES.md; set it literally in every call
CR=d50-card-clear-$WAVE
$MW d50-clear --run $CR 2>&1 | tee $DRV/logs/ur1-d50-clear.log
N=$($PY -c "import json; print(max(json.loads(l)['step'] for l in open('output/remediation/mechanical_teaser/STEPS.jsonl', encoding='utf-8')) + 1)")
S=$(printf 's%03d' $N); echo "$N $S"        # today: 46 s046; write both into $DRV/NOTES.md and set them literally afterwards
$MW plan --run $CR --step $N 2>&1 | tee $DRV/logs/ur1-plan.log
```

Pass of `d50-clear`: `WRITE_EXIT=0`; `"cleared"` names the D50 sites that hold a card text (six today),
`"without_card"` the others (none today). It is read-only on production and writes
`$M/teaser/runs/$CR/EXPORT.jsonl` and `OUTCOMES.jsonl` (reason `owner-o17-d50-disputed`). `REFUSED: ...
exists - a run is written once`: the label is taken, use `${WAVE}b`. `REFUSED: no D50 site holds a card
text`: UR-1 is done already, go to UR-2.
Pass of `plan`: `WRITE_EXIT=0`; read `$M/mechanical_teaser/$S/PLAN.md`. Measured 2026-11-11 on a fresh
read in a temp directory: `6 site(s): 1 provenance cell(s) (...), 6 card cell(s) (...); 0 listed` (the one
provenance cell is Richat's teaser provenance; the other five cards were written by no teaser run). A
listed site (`stale-description`: its description moved since `d50-clear` read it; `card-changed`;
`journal-disagrees`; `raw-data-not-reprinted`): report it with its line of `SKIPPED.jsonl`; the step
writes the others, and the listed site stays retired (UR-3 skips it `d50-card-not-cleared`) until a new
`d50-clear` run under the next label clears it in a later step. `REFUSED: ... clears the card of a D50
site and names the card it clears`: the outcomes file was edited; stop.

Then, each exit 0, in this order (a lane whose plan has 0 cells is skipped: it has no `ROLLBACK.sql`):
`$A --lane teaser-prov-$S --emit`, `--rehearse`, `--probe-guards` (every guard refuses), `--apply`
(`APPLY OK: the read-back matches the plan, row for row`), `--verify`; the same five for
`teaser-card-$S`; then `$A --lane teaser-card-$S --rehearse-rollback` and `$A --lane teaser-prov-$S
--rehearse-rollback`; then `$MW accept --step $N` : `ACCEPT_EXIT=0` and `RESULT: 0 deviation(s)`.
Journal recount: `run_stamp = 'wb-teaser-prov-<S>'` 1 row and `'wb-teaser-card-<S>'` 6 rows (the plan's
cell counts). Guard 5 refusing at `--rehearse` or `--apply` (`no longer hold the premise`): a description
moved after the plan, and that lane wrote nothing. Stop and report; on the orchestrator's word: if the
provenance lane of the step was applied before, undo it first (`CARD_DESCRIPTIONS.md` 5.6: its
`ROLLBACK.sql`), then `$MW close-reverted --step $N` (`RESULT: 0 write(s) still standing`), then UR-1
again under `${WAVE}b`. The step's trail (`$M/mechanical_teaser/STEPS.jsonl`, `ACCEPTED/`, `$S/`) is
committed by the orchestrator (rule 1): name the step in the report.

**UR-2 The Baltic Sea Anomaly holds no country** (`c8d2c13e-fd9a-466c-9fdc-fc26ee798ded`: `country`
`Baltic Sea` -> NULL; a wave lane `country-d84-<wave>`, runbook
`docs/procedures/WD2_SERVED_IMAGE_AND_SCOPE.md` 2.2, "The D50 wave since 2026-11-11"). The site is
written **while it is retired** - the planner lists a shown row `row-not-retired`, and the premise
holds the status, so the lane's apply and its `ROLLBACK.sql` both refuse a shown site (guard 5); run it
whether or not the site gets its dispute text (D84 is the country's own decision).

```bash
CW=$WAVE               # the country wave's label: the day's date; set it literally in every call
LC=country-d84-$CW
$CY --write --wave $CW 2>&1 | tee $DRV/logs/ur2-country-d84-plan.log
```

Pass: exit 0 and `"changes": 1, "skipped": 0`, `"lane": "country-d84-<CW>"`;
`$M/mechanical_country_d84/$CW/PLAN.md` shows one row,
`Baltic Sea` -> NULL, premise `Baltic Sea Anomaly | 61.37676947509479 | 18.448311841356542 | retired`
(name, point and scope status; the row measured 2026-11-11 on a fresh read). `REFUSED: the read leaves
nothing to write - Baltic Sea Anomaly: already-empty`: the country is NULL already, UR-2 is done.
`REFUSED: ... holds a plan already` or `... a wave that has written is never re-planned`: the label is
taken (a stamp is applied once) - a write that was undone is planned again under `${WAVE}b`, on the
orchestrator's word. Any other refusal (`name-moved`, `stored-value-moved`, `row-not-retired`,
`journal-disagrees`): stop and report it; the site stays out of UR-3.
Then, each exit 0, in this order: `$A --lane $LC --check-primitive`, `--verify` (keep the
output: `curated rows D84 leaves without a country that still hold one` is 1), `--emit`, `--rehearse`,
`--probe-guards` (every guard refuses, `site invariant - planned site(s) keep a country, or are none D84
leaves without one` among them), `--apply` (`APPLY OK: ...`), `--verify` (that metric 0, `curated rows
without a country` 1, `curated shown rows without a country that D84 does not name` 0; `card_stats rows
whose civilization differs from the site country` one higher than before: no lane empties
`card_stats.civilization`, report the number), `--rehearse-rollback` (now, while the site is retired:
after UR-3 guard 5 refuses it). Journal recount: `run_stamp =
'<CW>_mechanical-country-d84'`, 1 row. Never un-retire the site with `Baltic Sea` (it would get
`/sites/baltic-sea/...` and a country hub): UR-3 refuses it (`d84-country-not-cleared`).

**UR-3 The wave.** `WAVE` is the day's date (`date +%F`), fixed once and written into `$DRV/NOTES.md`; if
`output/remediation/mechanical_scope_unretire/$WAVE/` exists already, another un-retire wave used the label:
take `${WAVE}b` (a stamp is applied once; `2026-10-24` is taken). `LN=scope-unretire-$WAVE`. Set both
again, literally, in every call.
`$U export` (read-only snapshot into `output/remediation/mechanical_scope_unretire/export/export.jsonl`;
after UR-1 and UR-2 landed: the premise holds the md5 of the card text and the country)
`$U write --wave $WAVE` : `PLAN.jsonl`, `SKIPPED.jsonl`, `PLAN.md`, `ROLLBACK.sql` in
`output/remediation/mechanical_scope_unretire/$WAVE/`. Read `PLAN.md`: only D50 sites with a dispute text,
without a card text and - the Baltic Sea Anomaly - without a country are planned; the others are in
`SKIPPED.jsonl` as `d50-no-dispute-text`, `d50-card-not-cleared` or `d84-country-not-cleared`. A card
text counts whatever journal row wrote it: a site whose card clear was undone holds its old card again
and is skipped `d50-card-not-cleared` ("a clear that was undone put the old card back"; the lane's
invariant refuses it inside the transaction too) - UR-1 again under the next label. A dispute
text is one that **kept** both positions: a D50 site of EN-6's two lists is skipped `d50-no-dispute-text`
with "kept no dispute_a sentence" or "kept no dispute_b sentence", and the lane's invariant refuses it
inside the transaction too (as it refuses a D84 site that holds a country).
Run `$U export` on the merged code before `$U write`: an export file of older code has no `record`, and
`$U write` fails on it (`KeyError: 'record'`) for a D50 site whose text lane E wrote. A planned site
that is none of the six (a D58 date un-retire the tool found on its own): report it before the apply.
`REFUSED: the export leaves nothing to un-retire - SKIPPED reasons: ...`: no D50 site is ready (the reasons
say why); UR ends, report them.
Then, each exit 0, in this order (W-1 first):
`$A --lane $LN --check-primitive`, `$A --lane $LN --verify` (keep the output), `$A --lane $LN --interests`,
`$A --lane $LN --emit`, `$A --lane $LN --rehearse`, `$A --lane $LN --probe-guards` (every guard refuses),
`$A --lane $LN --apply` (`APPLY OK: the read-back matches the plan, row for row`), `$A --lane $LN --verify`
(the planned deltas, 0 deviations; "shown without a dispute-enriched description", "shown with a card
not judged against their dispute text" and "curated sites D84 leaves without a country shown with one"
all 0), `$A --lane $LN --rehearse-rollback`.
Journal recount: `run_stamp = '<WAVE>_mechanical-scope-unretire'`, two rows per site (`scope_status`,
`scope_reason`).
Undo, only on the orchestrator's word and in this order: the wave's `ROLLBACK.sql` (the sites are retired
again), then `$M/mechanical_country_d84/$CW/ROLLBACK.sql`, then the card step (`CARD_DESCRIPTIONS.md` 5.6).
The order is guarded where a lane can guard it: the country lane's `ROLLBACK.sql` run before the wave's
is refused by its guard 5 (`no longer hold the premise`: the site is not retired) and writes nothing -
run the wave's first, then it again. The card step's `ROLLBACK.sql` has no such guard: never run it
while a D50 site of the step is shown (the wave's `--verify` would then count "shown with a card not
judged against their dispute text"). After a complete undo the part can be made again, each step under
a new label: UR-1 with `d50-card-clear-${WAVE}b`, UR-2 with `--wave ${WAVE}b`, UR-3 with the next
un-retire label; no stamp is used twice.
**UR-4** Section 8, then: `curl -s -o /dev/null -w '%{http_code}' https://ancientnerds.com/api/sites/<id>` is
200 for each un-retired site (410 today). For the Baltic Sea Anomaly
`curl -s -o /dev/null -w '%{http_code} %{redirect_url}' "https://ancientnerds.com/site.html?id=c8d2c13e-fd9a-466c-9fdc-fc26ee798ded"`
must not redirect to a `/sites/` path (the popup's link for a curated site without a country is this id URL;
it answers 301 to `/globe.html#focus=<id>`), and
`curl -s -L -o /dev/null -w '%{http_code}' https://ancientnerds.com/sites/baltic-sea` stays `404` (it is
404 today).

## 11b. Close

1. `$V --plan $ROOT/LANE_PLAN.jsonl --complete` : `RESULT: 0 deviation(s)` when no other lane has an open WC
   batch (not gating; report the output).
2. Report: sites written by WN, `WN_EMPTY.txt`; candidates (and whether the named site was asked),
   disputes, the held briefs (`$DRV/enrich-*.briefs.jsonl.held.json`), the dispute sites that kept one
   position or neither (EN-6's two lists); the card clear's WB step with its journal counts (UR-1) and
   the country lane's journal row (UR-2); D50 sites shown
   again and those that stay retired with the reason; answers recorded (the `find` of section 5) against the
   estimate; every refused step with its message.

---

## 12. Code gaps (nothing here is the driver's to write)

**Closed: G1 to G5**, all on `build/track-b`. G4 and G5: commit `1eb2f73` and its review `158a9d9` (2026-11-11), **available
after the merge of build/track-b** (P-9 checks the tree); runbook `docs/procedures/CARD_DESCRIPTIONS.md`
5.11 and `docs/procedures/WD2_SERVED_IMAGE_AND_SCOPE.md` 2.2 ("The D50 wave since 2026-11-11").
G1, G2, G3 - commit `d008775` on `build/track-b` (2026-11-11) and its review `5abf8da` (a
dispute site that kept neither position is not written either; `briefs --exclude`; the pilot's judge is
not asked about a dispute site the plan does not write), **available after the merge of
build/track-b** (P-8 checks the tree). Runbook: `docs/procedures/SENTENCE_CHECK.md` 14.3, 14.5, 14.7, 14.8
and `docs/procedures/WD2_SERVED_IMAGE_AND_SCOPE.md` section 4.

| # | what was missing | the command or rule now | used at |
| --- | --- | --- | --- |
| G1 | The screen could not be told to ask a named site (Pantelleria Vecchia Bank Megalith, `daa1ea4b`, named in D21, carries no signal). | `$D candidates --run-dir $DSR --wiki-cache $WIKI --include $DRV/dispute-include.txt` : each listed site is a candidate with the signal `named`, researched like any other; a listed site that cannot be asked refuses the command; `recall` keeps it in `missed` and lists it under `named`. | DS-3, DS-4, DS-5 |
| G2 | `export --enrich --disputes` refuses the whole file when one brief's site is not asked, and no command wrote a subset. | `$D briefs --run-dir $DSR --for-run <enrichment run, read> [--after <pilot run>] [--exclude <ids file>] --out B` : writes `B` (the export's `--disputes`), `B.sites.txt` (its `--sites`), `B.held.json` (the others, with reasons); prints `usable` and `pilot_size`. `--after` and `--exclude` are given exactly as to the export. | EN-2, EN-3, EN-9 |
| G3 | One of the two dispute sentences can be dropped after it was written; the build planned the site all the same, and the D50 gate read the classes written. | No new command. `$C build` plans a site with a dispute brief only with both positions kept: one kept is `not_planned.dispute-one-position`, neither kept beside another new sentence `not_planned.dispute-no-position` (`FINAL.jsonl` `planned: false`; nothing of the site is written, a new run asks it again), and `$C judge-export` does not ask the pilot's judge about such a site; the un-retire (`$U write`, the lane's invariant and its read-back) reads the positions **kept** from the enrichment record of the site and skips a D50 site without both (`d50-no-dispute-text`: "kept no dispute_a sentence"). `$U export` must be run with the merged code before `$U write`. | EN-6, UR-3 |
| G4 | The card lane refuses a retired site, the un-retire refuses a D50 site whose card was not written or cleared after its dispute text: a deadlock for all six. | O17 decides it: the six cards are cleared the D47 way, no card run and no new card. `$MW d50-clear --run d50-card-clear-<wave>` builds the owner run (read-only on production; `$M/teaser/runs/<run>/OUTCOMES.jsonl`: per D50 site that holds a card text one `cleared` outcome, reason `owner-o17-d50-disputed`, the card named by its hash); `$MW plan --run d50-card-clear-<wave> --step N` plans it as a WB step although the sites are retired - the one outcome of a retired site the planner plans, and only for the six; every other outcome of a retired site stays listed `retired`, and no card run asks a retired site - then the step's two lanes through `$A` and `$MW accept --step N`. A site without a card text passes the un-retire's card test (`d50-card-not-cleared` no more); a card that an undone clear put back does not (the test asks no journal order: no card text, or one whose teaser provenance hashes it and the description the site holds). | UR-1, UR-3 |
| G5 | D84: no journalled lane wrote `country` NULL for the Baltic Sea Anomaly. | `$CY --write --wave <wave>` plans the one cell (`Baltic Sea` -> NULL; read-only on production; `$M/mechanical_country_d84/<wave>/`), `$A --lane country-d84-<wave> --check-primitive` ... `--apply` writes it while the site is retired (a wave lane that empties its column; premise: name, point and the retired status, so its `ROLLBACK.sql` refuses a shown site; invariant: a planned site holds no country and is the one D84 names; a write that was undone is planned again under the next label). The un-retire skips the site `d84-country-not-cleared` while it holds a country, its invariant refuses it inside the transaction, and its read-back counts `curated sites D84 leaves without a country shown with one` (0). No route code was needed: site pages, country hubs, sitemap and IndexNow read `curated_page` (with a country). | UR-2, UR-3 |

Not built, because O17 rules it out: a card run for retired sites (`teaser/run.py classify` and
`seed_reason` leave a retired site out, as before).

Not a gap, but a dependency: the Fable switch (`roles.py`, `opus_handoff.py`, `phase4/model4.py`,
`wc/cli.py`, `wc/enrich.py` with `writer_standing`) is uncommitted in the working tree on 2026-11-10. The lane
runs from the tree in which P-1 and P-2 pass.

## 13. What can go wrong, and the check that catches it

| what | the check | what then |
| --- | --- | --- |
| Wikimedia throttles (429), a host is down while an `import` runs: its pages are fetched once per run and a failed quote drops its sentence for good | P-6 before every import; the import's `verdicts` against the agents' own `check-answer` results (a sudden share of dropped sentences) | no repair inside the run; the sites end empty or thinner; a later sweep run asks the empty ones again |
| An agent stops mid-batch or records a malformed answer | `$OH validate` `missing`/`malformed`; the import's `REFUSED` | SL step 4 |
| The pilot measured too little (most sites empty) or the judge finds a WRONG kept sentence | `JUDGE_EXIT=1`, `RESULT.json` `failures` | one new pilot, then stop |
| The gate's chain names a wrong plan | W-3, the gate's `pilot passed:` line and its refusals | fix `$PLANS` by the rule of W-3, never by naming a failed pilot |
| A site's text or description state moved since the read (another lane wrote it) | the gate's `refused by rule: {'moved-since-check': n}` in W-4 | the site is not written; the sweep asks it again |
| A row moves between the gate's read and the transaction | `STOPPED.json`, `WRITE_EXIT=1` | stop; a person reads it |
| A later lane's stamp on WC rows | W-7 deviations `CHANGED LATER` | never accept; report the stamp |
| The lane-N or lane-E API is not live | the gate's `lane N:` / `lane E:` line | deploy first; not this lane's |
| The dispute screen is too broad for the estimate (it is, at today's 235 candidates) | DS-5 | stop and report before any answer; the orchestrator's word, or its `DS-5 decision:` line, decides |
| A known disputed site lost its signal (a lane rewrote its text), `recall` fails | DS-4 `DISPUTE_EXIT=1`, `missed` | report; go on only on the orchestrator's word |
| A stored English Wikipedia title is dead | DS-2 `REFUSED: the article ... does not exist` | stop the part, report the title |
| WN starts while D14 part B, D20 or the D57 lane is still open | P-7; WN-2's `retired` and `identity hold` counts | those sites are left out and wait for the sweep |
| Another lane's unwritten batches are in the chain | W-4 `open batches:` above this run's | stop before `--apply`; report |
| A science-side sentence of a D50 text is listed as "asserting" and both checks keep it | `SUMMARY.json` `defects_kept`, `defect-closure`, EN-2's held file (`reason: asserting-in-text`, `asserting_in_text`) | the site cannot take its brief and stays retired; report |
| The adjudicator rules a D50 claim "merely mentioned in order to dismiss it" (`not-a-dispute`) | DS-9 | the site stays retired; report |
| One position of a dispute dropped by the verifier or lost at the import | the build's `not_planned.dispute-one-position` and EN-6's first list (after the merge of build/track-b) | that site is not written and is reported; the rest of the plan is judged and written. A D50 site among them stays retired |
| Both positions of a dispute dropped, another new sentence kept | the build's `not_planned.dispute-no-position` and EN-6's second list | that site is not written (a write would lock it out of its dispute text) and is reported; a D50 site among them stays retired |
| So many dispute sites lost a position that the pilot has too few judged texts | EN-7: `"passed": false` with "measured too little", or `REFUSED: ... the pilot measured nothing` at `judge-export` | one new pilot (EN-7), then stop |
| A dispute site must be left out of an enrichment run | EN-2's `--exclude` | the same file to `briefs` and to the export; the brief is held `excluded` |
| The named site of DS-3 cannot be asked on this read (its text was cleared, or it was retired) | DS-3 `REFUSED: ... cannot be asked (...)` | the command again without `--include`; report the site as not asked |
| The tree does not hold the merge of build/track-b | P-8 | DS without the named site; part EN does not start: `blocked: merge of build/track-b` |
| A WN text written for a site D13 re-targets later | WN-2's exclusion | none: D13 rewrites the text |
| The static export is stale | X-2 | X-1 again |
| Disk | P-3 | stop below 10 GB |
| The tree does not hold G4 and G5 | P-9 | part UR does not start: `blocked: merge of build/track-b` |
| A WB step of the cards lane is open when UR-1 plans | `$MW plan`: `REFUSED: step N-1 has no acceptance` (or `the next step is M, not N`) | wait for the cards lane's driver, read `N` again; never close another lane's step |
| A description of the six moves between `d50-clear` and the card step's apply | `stale-description` in the step's `SKIPPED.jsonl`, or guard 5 at `--rehearse`/`--apply` | a listed site is not written, the step writes the others; a refused lane wrote nothing: stop, report, then as UR-1 says (`close-reverted`, a new `d50-clear` run under the next label) |
| The Baltic Sea Anomaly's row is not as D84 was decided on it (renamed, another country, shown, a broken `country` journal) | `$CY --write`: `REFUSED: the read leaves nothing to write - ...` | report the reason; the site stays retired (`d84-country-not-cleared`) |
| The country is emptied but the site never gets its dispute text | UR-3 `d50-no-dispute-text` | none: D84 is the country's own decision; the site stays retired without a country |

## 14. Population and estimate

**WN** (owner's estimate about 200, checkpoint 250). Per asked site about 1 write answer, 0.9 verify, 0.25
verify2 (the first WN run measured 20, 19 and 5), and in the pilot about 17 judge answers:
`2.15 N + 17`. Today `N` = 38 (40 less the 2 D13 sites): **about 95-100 answers in about 21 batches**
(pilot: 20 + 17 + 4 + 17 = 58 in 13 batches; rest of 18: 18 + 15 + 4 = 37 in 8). If the WC-finish lane clears its
forecast 60-70 sites before, `N` is about 100-108: **about 230-250 answers in about 50 batches**, at the
checkpoint. The 8 sites without any stored source will mostly end empty. The sweep after D13 is at most
15 answers.

**Disputes** (owner's estimate about 360, checkpoint 450). With `C` candidates: research `C` answers (5 a
batch), adjudication about `0.3 C`, repair about `0.35 C` (check, re-ask, verify, verify2, the second check),
enrichment about `0.55 C + 20` (write, verify, verify2, the pilot's judge): `2.2 C + 20`. Measured today
`C` = 235: research 235 in 47 batches, adjudication about 70 in 14, repair about 82 in 10, enrichment about
150 in 28: **about 537 answers in about 100 batches**, 49 % above the owner's 360 (DS-5 stops first). With
`--wiki-min-hits 3` (`C` = 184): about 425 in about 80 batches; with 4 (`C` = 157): about 365 in about 68.
Only the research count is measured; every share after it is an assumption: no dispute run has ever been
answered.

**Lane total** at today's population: about **635 answers in about 120 agent batches** (owner's estimates
together: 560); about 780 with the WC-finish clears; about 525 and 670 with `--wiki-min-hits 3`. Wall time
at web width 3 and about 15-20 minutes a batch: WN about 5 hours, the dispute parts about 12-14 hours, plus
four to six write steps of about 30-45 minutes each including the export check.
