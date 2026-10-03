---
name: theo-write
description: Use when the owner runs /theo-write for the weekly Theo paper session, when a researched Theo dossier waits for its paper, when a published Theo paper needs a correction, a legacy rewrite or a video registration, or when a paper publish or correct call timed out, exited 3 or 4, or raised RemoteOutcomeUnknown.
---

# Theo write: the weekly paper session

## Overview

Theo (MiniMax M3 on the VPS) only researches: a run ends as `researched` with a dossier. This
session writes the paper with the model of this session (MiniMax M3.1 Flash in MiniMax Code,
owner decision 2026-10-03), has it fact-checked claim by claim and image by image, and
publishes it through the gated VPS CLI `theo_publish`. **Publishing is automatic once every gate
passes (spec §0): there is no owner approval step.** The apply itself sends the owner notice.

Core rule: the code validates, the model judges. Every judgement is made in this session or by
`studio mcode …` (one `mcode exec` per task, model `MiniMax-M3.1-Flash-Preview`, effort max).
A red gate is fixed in the paper, never in a derived file or a handoff answer.

Run every command from the checkout root as `./.venv/Scripts/python.exe -m pipeline.studio …`;
below it is written `studio …`. Exit 0 = ok, 1 = a check failed (`paper check`), 2 = a
`StudioError` (`error: …` on stderr). Every refusal below reaches you as that exit 2 of the
studio, whichever `theo_publish` exit code (1-4) its message names. The workspace is
`<STUDIO_ASSETS>/papers/<request_id>/` (default `<main checkout>/video-assets/studio`, also from
a worktree). `<id>` is always the research request id (a lowercase uuid), never the slug.

## The session

1. **Pick the dossier.** `studio paper list` prints the researched runs as JSON, oldest first.
   Take the id the owner passed to `/theo-write`; with none, the oldest row. An empty list ends
   the session: nothing to write.
2. **Pull and write.** `studio paper pull <id>` writes `dossier.json.gz`, `texts/<source_id>.txt`
   and `brief.md`. Read `brief.md` in full: it holds the house format (editorial spec sections
   1-9), the rules the checker enforces and the dossier. Write `draft.md`, `paper_meta.json`
   and `evidence.json` exactly as its "What you hand in" says. Cite only with
   `[S:<source_id>]`. Every evidence entry is `"verdict": "supported"`.
3. **Claim check.** `studio paper number <id>`, `studio paper claims-export <id>`, then
   `studio mcode claim-check <id>` (below), then `studio paper claims-import <id>`.
   - The import prints only `{"accepted": N}`, and refuses while a current task has no accepted
     answer (it names the first eight as `kind:ref`): run the check and the import again.
   - Where the verdicts are: `studio paper check <id>` (step 5), gate `claims` of
     `check_report.json`: `details.status.not_supported[]` holds `ref`, `verdict`, `explanation`
     and `fix_suggestion` of every task whose answer is not `supported`, `missing` the tasks
     without one. The accepted answers themselves are `claims_check/accepted.json`.
   - `partly` or `unsupported`: fix the paragraph (see `fix_suggestion`) or the evidence entry.
   - `source_missing`: re-source the claim or drop it.
   - An evidence `quote` from a `tdm_reserved` source cannot be checked before the check has
     saved that source's live text, `claims_check/live/<source_id>.txt`: copy the quote verbatim
     from that file, and `paper check` (gate `evidence`) holds it to the file.
4. **Images.** Write `images/opportunities.json` (4-10 entries, `brief.md` item 4), then
   `studio paper images-export <id>`, `studio mcode image-check <id>`, and
   `studio paper images-import <id>`.
5. **Check.** `studio paper check <id>`. On exit 1 read the failing gates in `check_report.json`,
   fix `draft.md`, `paper_meta.json`, `evidence.json` or `opportunities.json`, and repeat from
   step 3 (`number` → claims → images → `check`). Unchanged paragraphs keep their accepted
   answers; only changed ones become new tasks.
6. **Publish.** `studio paper bundle <id>`, then `studio paper publish <id> --dry-run`, then
   `studio paper publish <id>`. Every `paper publish` first uploads the bundle's selected images
   to production's `research-images/<id>/` (verified byte for byte, safe to repeat) and dry-runs;
   `--dry-run` stops there and records the dry run in `publish_outcome.json`. The apply then
   applies and writes `publish_outcome.json` and `published_bundle.json`. A `bundle.json` older
   than the paper is refused (`bundle.json is stale`): run `paper bundle` again.
7. **Report** the printed `slug`, `url` and `side_effects` to the owner. The `paper_published`
   notice (`side_effects.notify`) goes to `thinking_log` automatically; Discord stays unset
   (owner #5). A failed side effect does not undo the publish: name it in the report.

## The checks (the handoff seam)

`studio mcode claim-check <id>` and `studio mcode image-check <id>` read the pending tasks, run
one `mcode exec` per task and append the answers to `verdicts.jsonl`; the import step validates
them by machine and refuses the whole file on any problem, listing each as
`answer N (<task_id>): <problem>`. A refused `verdicts.jsonl` stays in place, and a check
answers only the tasks it holds no line for: delete the lines the error names (deleting the
whole file answers every pending task again), then run the check again. Never write or edit an
answer by hand.

| Command | Answers | Then |
|---|---|---|
| `studio mcode claim-check <id>` | `claims_check/pending.jsonl`: one verifier per task, an adversarial skeptic in its own independent run (`skeptic_by`) for every `supported`, a live read of every cited `tdm_reserved` source into `claims_check/live/<id>.txt` | `paper claims-import` |
| `studio mcode image-check <id>` | `images/pending.jsonl`: `meaningful\|weak\|misleading\|off_topic`, `depicts`, `subject_box`, caption ≤ 120 chars | `paper images-import` |

What the driver does and does not decide:

- Every run writes its answer to `mcode_runs/<task_id>.json` and validates it with
  `studio mcode validate`; the driver validates the file again itself, with the same code the
  import uses. An answer that counts in the check counts on import.
- `answered_by` and `skeptic_by` name the model the run's exec JSON reported and its run id.
- After the batch the driver checks that no tracked file changed (`git status`): a run that
  wrote into the checkout instead of its answer file voids the batch and says so.
- Two runs at a time, more while no 429 appears, half on the first one. The weekly MiniMax plan
  at 10 % or less stops the batch (exit 3, `stopped` names the line): wait for the reset and run
  again - the pending tasks are exactly the unanswered ones. `studio mcode probe` prints the CLI,
  the model and the remaining plan.
- Exit 1 means at least one task is unanswered; `not_answered[]` names every one with its
  reason. A task the model did not finish is normal: run the check again.
- A batch that only fails on 429 or the quota stop is not a paper problem. Never paper over it.

When an import still reports pending tasks, run the check again and import again.

## Corrections and legacy rewrites

Every correction dry-runs first, applies only when the dry run passes, is journalled, and is
recorded in `corrections/<UTC stamp>.json`. `--text` (one entry) or `--entries FILE`
(`[{text, evidence_id?}]`) is always required; `--date YYYY-MM-DD` defaults to today (UTC).
Slug, `published_at`, the publisher and the stored corrections log stay.

| Case | Command |
|---|---|
| Log entry only | `studio paper correct <id> --text '<entry>' [--evidence-id ev-NN]` |
| Text fix of a studio paper (same images, title, card description) | fix `draft.md`, steps 3-5, then `studio paper correct <id> --text '<entry>' --with-report` |
| New title, card or images; full rewrite of a studio paper | edit its workspace files, steps 3-5, `paper bundle`, then `studio paper correct <id> --text '<entry>' --republish` |
| Legacy paper, small fix (e.g. the Roswell date, owner #6) | `content` of `GET https://ancientnerds.com/api/v1/research/<slug>` (its `id` is `<id>`), fixed, saved as FILE: `studio paper correct <id> --text '<entry>' --report-file FILE`. Keeps the stored writer, sends no notice |
| Legacy paper, full rewrite of its stored text by this session | the same plus `--rewrite`: the page shows the writer's disclosure line and the `paper_published` notice goes out |
| Legacy paper, rewrite from a fresh Theo run RUN on its question (#17, #18) | `studio paper pull <id> --dossier-from <RUN>` (RUN must be `researched`), write as in step 2, steps 3-5, `paper bundle`, then `studio paper correct <id> --text '<entry>' --republish`. **Never `paper publish`**: it refuses this workspace. The first republish sends RUN as `dossier_request_id` and theo_publish closes RUN as `cancelled` |

- Legacy rewrites run only when the owner asks; the owner picks the basis per paper (#18).
- An evidence id is never renumbered or reused; it is retired only by an entry that names it
  (`--evidence-id`). The studio never fills `result.corrections` (it is always `[]`).
- A log-only correction re-runs the quality gate on the stored text. 9 legacy papers fail it
  there: send their entry with a `--report-file` text that passes `validate_paper_artifact`.
  `mogollon-pithouse-sites-across-the-upper-gila` changes only through a full `--republish`.

## When theo_publish refuses or the outcome is unknown

The studio prints each of these as `error: …` and exits 2; the `theo_publish` exit code (1-4) is
the one the message names, not the studio's.

| Message | Meaning | Do |
|---|---|---|
| "refused: failing gates [...]" (theo_publish exit 1) | a gate failed, nothing written | fix the paper, `paper check`, run again |
| "the paper is already public: change it with `paper correct`" | the row is public | this is a correction, not a publish |
| "theo_publish refused the input: …" (exit 2) | the payload broke the contract, or names a row that does not exist | `research request <id> does not exist` is a wrong id: fix it. Anything else is a bug in the studio or theo_publish: stop and report |
| "the row changed underneath" (exit 3) | nothing committed | read the journal row (below) to see what changed it, then `paper check` and run again |
| `RemoteOutcomeUnknown`: a timeout, no JSON, "committed but the re-read differs" (exit 4) | the write may have committed | the adoption procedure |

**Adoption procedure** (printed with the error). Before every write the studio records the
sha256 of the exact bytes it sends (`publish_outcome.json` `bundle_sha256`,
`corrections/<stamp>.json` `body_sha256`); theo_publish journals every committed write with it.

1. Read the newest journal row, read-only:
   `ssh ancientnerds "docker exec ancient_nerds_db psql -U ancient_map -d ancient_map -c \"SELECT id, action, slug, bundle_sha256, side_effects FROM theo_paper_publications WHERE request_id = '<id>' ORDER BY id DESC LIMIT 1\""`
2. Same hash: the write committed. **Never run it again.** After a publish or `--republish`, copy
   `bundle.json` byte for byte to `published_bundle.json` by hand, before any new `paper
   bundle`. After a first publish, `episode init --paper <id>` then needs `--paper-slug <the
   row's slug>`.
3. `side_effects` NULL: IndexNow, Qdrant and the owner notice did not run. The nightly reindex
   covers Qdrant; report the missing notice to the owner.
4. Another hash: nothing committed. Run the write again from its dry run.

## Registering a video on its paper

`episode register-youtube` (skill studio-video, step 12) registers a manual upload on its paper
and calls the paper side itself. `paper register-video` is that paper side as a command of its
own: run it when `register-youtube` failed after the ledger write and its error printed it (run
the command with `./.venv/Scripts/python.exe` for the printed `python`):

`studio paper register-video <id> --youtube-id <video id> --title '<uploaded title>'
--published-at <ISO 8601 with timezone> --timestamps <STUDIO_ASSETS>/episodes/<slug>/package/evidence_timestamps.json
[--poster <STUDIO_ASSETS>/episodes/<slug>/package/thumbnail_<K>.jpg]`

It dry-runs without the poster, uploads the poster JPEG as `research-images/<id>/video_<video id>.jpg`
(verified), dry-runs with it, then applies. `--poster` is the thumbnail set on YouTube (or the A/B
winner); without it the page keeps the posterless player. The first dry run refuses a video the
paper already shows (gate `duplicate`), so repeating a registration whose outcome is unknown is
safe: if it committed, the repeat stops at that gate; if not, it goes through. Its only side effect
is IndexNow.

## Stop conditions

- **Stop and report to the owner:** the list is empty; the paper is published or the correction
  applied (report slug, url, side effects); a gate cannot pass without bending a rule (too few
  supported claims for 5,000 words, no hero image among the checked images); a `theo_publish`
  "refused the input" that is not a wrong id; an unknown outcome whose journal row cannot be read.
- **Do not stop** between `paper pull` and the publish to ask for approval.

## Never

- Edit `paper.md`, `sources.json`, `check_report.json`, `bundle.json`, `published_bundle.json`
  (except in the adoption procedure) or the handoff files (`tasks.jsonl`, `pending.jsonl`,
  `prompts/`, `accepted.json`, `verdicts.jsonl`, `mcode_runs/`).
- Keep an evidence entry the claim check did not support, or give one another verdict.
- Name another model in a stamp, a provenance, a ledger row or a disclosure: a stamp names the
  model that produced the text, and this is `MiniMax-M3.1-Flash-Preview`.
- Write to the production database or copy files to the VPS by hand: the CLIs are the only path.
- Re-run a write whose outcome is unknown before reading the journal.
- Use `--rewrite` for a small fix, or `paper publish` for a paper that is already public.
- Touch Theo's topic queue (the owner's decision) or set `DISCORD_WEBHOOK_URL`.
