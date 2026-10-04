# Goal: perfect Theo's research with the 24 paused topics

Supersedes `theo-paper-loop-2026-10-04.md` as the active goal. That goal asked the
**studio writer** to pass the **paper gate** in two check iterations, on a legacy
draft. This one runs **Theo's research** itself, on the owner's own material, and
changes the chain until the papers are right without a human repairing them.

## Objective

(copy into the goal, verbatim)

> Nutze die 24 von mir am 05.07.2026 pausierten Research-Themen, um Theo's
> Research-Kette zu perfektionieren. Jedes Thema läuft einmal durch die Kette, das
> Ergebnis wird bis `paper bundle` durchgeprüft, und die Kette wird nach jedem Lauf an
> genau den Befunden geändert, die dieser Lauf erzeugt hat - bis die Kette von selbst
> Papers liefert, die alle Gates in höchstens zwei Check-Iterationen bestehen.
> Vollspeed: `MiniMax-M3.1-Flash-Preview`, effort max, zwei Läufe parallel, über
> `python -m pipeline.studio mcode` und `mcode exec`.
>
> DONE WHEN: mindestens 8 der 24 Themen als `paper bundle` mit grünem
> `check_report.json` vorliegen, jeder in höchstens 2 Check-Iterationen, je mit einem
> Ledger-Eintrag und je mit einer gemessenen Ketten-Änderung, die den nächsten Lauf
> messbar billiger macht. Ein Thema, das eine dritte Iteration braucht, ist ein
> **Ketten**-Fehler: die Kette wird geändert und das Thema neu gefahren, nicht das
> Paper von Hand repariert.
>
> NEVER: kein `paper publish`, kein Push auf main, kein Deploy, kein Schreibzugriff
> auf `unified_sites`, kein Ändern eines veröffentlichten Papers. Das Fortsetzen der
> Runs ist der eine Produktionsschreibzugriff und ist am 2026-10-04 vom Owner
> ausdrücklich angewiesen.

## The material, measured on production 2026-10-04 (read-only)

24 rows in `research_requests`, all created 2026-07-05, all `is_batch = true`,
`user_id = 442000112756064260`, all `status = 'paused'`, all paused by the owner.

| | |
| --- | --- |
| rows | 24 |
| `is_public` / `slug` / `result_json` | 0 / 0 / 0 |
| ever started | **1** (`afe7c26a`, 2026-09-26, 345 llm_calls, 33 881 072 tokens) |
| never started | **23** (`total_tokens = 0`) |
| `error_message` | none on any of the 24 |

Same batch, for contrast: 27 `completed` (26 public with slugs) and 1 `failed`. The
completed ones are the ancientnerds.com paper topics; the paused ones are two-sided,
citation-heavy science briefings for a cosmological mystery novel - Zeno effect against
esoteric doctrine, delayed-choice, Schumann resonances against brainwave entrainment,
megalithic stone chambers as tuned resonators, Younger Dryas impact against airburst,
and so on. They are the hardest kind of prompt: contested, two-sided, and dense with
numbers.

They are the right instrument for this goal precisely because they are hard. A chain
that survives these has no easy case left.

## Why the chain is the thing to fix, measured

Paper 1 (`95fa3798`, the only workspace with a complete archive) was checked with the
new gate for the first time on 2026-10-04 and reported 118 support findings. Two code
fixes took that to 88. The claim check then found, over its first 42 answered tasks,
26 `partly` and 1 `unsupported` against 15 `supported`.

Of the fixes where the verifier named the offending phrase in quotes, **8 of 8** name a
phrase that `brief.md` already states - and `brief.md` is the dossier's **moderated
claims**, at high confidence, with markers already attached:

> (high) The Department of Defense officially released three Navy forward-looking
> infrared (FLIR/ATFLIR) gun-camera videos in April 2020 ...

The chain is `dossier -> brief -> draft -> gate`, and the gate blames the draft. The
writer received claims already carrying markers their sources do not support, and
following them faithfully was the only available behaviour. Fixing the paper repairs
that paper; it does nothing for the next one, which gets the same brief.

## The chain changes, in the order they should be tried

1. **Gate the moderated claims at dossier assembly.** The check is not new work:
   `claim_support.locate_support` already answers "does this source carry this
   sentence", and `paper_claim_gate` already applies it to the numbered paper. What is
   missing is the same call on the moderated claims, before they are promoted into the
   brief. `pipeline/lyra/archive_completion.py:377` already archives the full text of
   every source a moderated claim cites and returns its coverage, so by the time
   `pipeline/studio/paper/brief_template.md:385` fills `{{moderated}}` the texts that
   such a gate needs are on disk and keyed to exactly those claims. A moderated claim
   whose own cited source does not carry it should be rewritten, dropped, or re-sourced
   there - not discovered by a writer two stages later.
2. **Free gates before the expensive ones.** Done, `76f4af0`: the brief now runs
   `paper check` right after `paper number`, before `claims-export`, with the measured
   reason in the text. Its `support` gate costs no model calls and named a replacement
   marker for 47 of paper 1's 82 wrong markers.
3. **Marker placement.** Done, `776a9a7`: a marker that follows a full stop moves to
   before it, and stripping a marker no longer leaves its space behind
   (`normalize_anchor_text`, which had been silently breaking every anchor written on
   the house form).

Change 1 is the one the 24 runs are for. It must be measured on them, not assumed from
paper 1.

## The loop, per topic

1. **Resume** the run to `researched`: the `DossierHandler` writes the dossier as
   `research_artifacts` rows, runs archive completion, writes the `dossier` manifest
   last, and ends the row as `status = 'researched'` with
   `result_json = {"dossier": <summary>, "title": null}`. The row is invisible to every
   public reader until a paper exists - that is the intended state, not a fault.
2. **`paper pull`** into the studio workspace: `brief.md` plus `texts/`.
3. **`paper check`** - the free gates. Fix the citation layer until it is sound. The
   `claims`, `images`, `coherence` and `hero` gates are expected red here because their
   steps have not run.
4. **Claim check**: `paper claims-export`, `mcode claim-check`, `paper claims-import`,
   then apply every `fix_suggestion` to `draft.md`. Only the changed paragraphs are
   re-checked.
5. **Images**: `paper images-export`, `mcode image-check`, `paper images-import`; a
   hero image, one per section.
6. **`paper number` -> `paper check` -> `paper bundle`.**
7. **Ledger** for this run: what the gate said, what the writer changed, and **what the
   chain changed** - with the measurement that says the next run will be cheaper.

Count the check iterations honestly. Step 3 is iteration 1, step 6 iteration 2. A third
means the chain, not the writer, is at fault.

## Cost and pace

Nothing is billed for MiniMax quota before 07.10.2026, so this goal runs at full speed:
effort max, two runs at a time, no artificial limit, and the whole 24 if the chain
holds. The driver's own guards stay on unchanged - the 10 % weekly-plan stop, the 429
backoff, and the `git status` guard that voids a batch whose runs wrote into the
checkout. That guard is real: it voided a batch on 2026-10-04 because the session
edited a tracked file mid-run, and it will void another one if that happens again.

## The one production write

Resuming a run writes to `research_requests` (status, `started_at`, tokens) and, on
completion, `research_artifacts` and `thinking_log`. That is authorised. Nothing else
touches production: no `paper publish`, no `unified_sites` write, no DELETE or TRUNCATE,
no change to a published paper. The VPS has not seen this branch, so the code that runs
the chain is the local checkout.

## Still open from the superseded goal

1. The claim check on paper 1 stands at **42 of 85** answered (26 `partly`, 15
   `supported`, 1 `unsupported`). It was cut by the harness's one-hour background-task
   cap, not by a failure, and `_pending()` skips what `verdicts.jsonl` already holds, so
   it resumes with `mcode claim-check 95fa3798-...`. It is **not** a prerequisite: paper
   1 is a legacy draft written on 02.10. against a gate that landed on 04.10., and its
   iteration count cannot measure the new chain.
2. `docs/reports/theo-paper-loop-2026-10-04.md` carries a wrong figure: it says
   "compliance with an explicit, exemplified rule was about 12 %". The defensible
   numbers are 87 of 169 citations for the one-claim rule and 134 of 169 for marker
   placement, and the two sets overlap by at least 5, so it is not a compliance rate at
   all. To be corrected and committed.
3. The dossier finding (section above) is to be appended to the loop report's ledger and
   committed, so the superseded goal closes with its measurement intact.
