---
name: theo-write
description: Use when the owner runs /theo-write for the weekly Theo paper session, when a researched Theo dossier waits for its paper, when a published Theo paper needs a correction, a legacy rewrite or a video registration, or when a paper publish or correct call timed out, exited 3 or 4, or raised RemoteOutcomeUnknown.
---

# Theo write: the weekly paper session

## Overview

Theo (MiniMax M3 on the VPS) only researches: a run ends as `researched` with a dossier. This
session writes the paper as Claude, has it fact-checked claim by claim and image by image, and
publishes it through the gated VPS CLI `theo_publish`. **Publishing is automatic once every gate
passes (spec §0): there is no owner approval step.** The apply itself sends the owner notice.

Core rule: the code validates, Claude judges. Every judgement is made in this session or by the
named workflows (Opus only: no DeepSeek, no MiniMax, no Pi or opencode). A red gate is fixed in
the paper, never in a derived file or a handoff answer.

Run every command from the checkout root as `./.venv/Scripts/python.exe -m pipeline.studio …`;
below it is written `studio …`. Exit 0 = ok, 1 = a check failed (`paper check`), 2 = a
`StudioError` (message on stderr). The workspace is `<STUDIO_ASSETS>/papers/<request_id>/`
(default `<main checkout>/video-assets/studio`, also from a worktree). `<id>` is always the
research request id (a lowercase uuid), never the slug.

## The session

1. **Pick the dossier.** `studio paper list` prints the researched runs as JSON, oldest first.
   Take the id the owner passed to `/theo-write`; with none, the oldest row. An empty list ends
   the session: nothing to write.
2. **Pull and write.** `studio paper pull <id>` writes `dossier.json.gz`, `texts/<source_id>.txt`
   and `brief.md`. Read `brief.md` in full: it holds the house format (editorial spec sections
   1-9), the rules the checker enforces and the dossier. Write `draft.md`, `paper_meta.json`
   and `evidence.json` exactly as its "What you hand in" says. Cite only with
   `[S:<source_id>]`. Every evidence entry is `"verdict": "supported"`.
3. **Claim check.** `studio paper number <id>`, `studio paper claims-export <id>`, then the
   workflow **theo-claim-check** (below), then `studio paper claims-import <id>`.
   - `partly` or `unsupported`: fix the paragraph (see `fix_suggestion`) or the evidence entry.
   - `source_missing`: re-source the claim or drop it.
   - An evidence `quote` from a `tdm_reserved` source is copied verbatim from the live text
     the claim check saved, `claims_check/live/<source_id>.txt`, after this import.
4. **Images.** Write `images/opportunities.json` (4-10 entries, `brief.md` item 4), then
   `studio paper images-export <id>`, the workflow **theo-image-check**, and
   `studio paper images-import <id>`.
5. **Check.** `studio paper check <id>`. On exit 1 read the failing gates in `check_report.json`,
   fix `draft.md`, `paper_meta.json`, `evidence.json` or `opportunities.json`, and repeat from
   step 3 (`number` → claims → images → `check`). Unchanged paragraphs keep their accepted
   answers; only changed ones become new tasks.
6. **Publish.** `studio paper bundle <id>`, then `studio paper publish <id> --dry-run`, then
   `studio paper publish <id>`. The apply uploads the selected images (verified), dry-runs
   again, applies, and writes `publish_outcome.json` and `published_bundle.json`.
7. **Report** the printed `slug`, `url` and `side_effects` to the owner. The `paper_published`
   notice (`side_effects.notify`) goes to `thinking_log` automatically; Discord stays unset
   (owner #5). A failed side effect does not undo the publish: name it in the report.

## Workflows (the handoff seam)

Run each with the Workflow tool by name, passing the paper workspace path as `args`. They write
answers only; the import step validates them by machine and refuses the whole file on any
problem (listed). A refused `verdicts.jsonl` stays in place: remove it and run the workflow
again. Never write or edit an answer by hand.

| Workflow | Answers | Then |
|---|---|---|
| `theo-claim-check` | `claims_check/pending.jsonl`: one verifier per task, an adversarial skeptic (`skeptic_by`) for every `supported`, a live read of every cited `tdm_reserved` source into `claims_check/live/<id>.txt` | `paper claims-import` |
| `theo-image-check` | `images/pending.jsonl`: `meaningful\|weak\|misleading\|off_topic`, `depicts`, `subject_box`, caption ≤ 120 chars | `paper images-import` |

When an import still reports pending tasks, run the workflow again and import again.

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
| Legacy paper, full Claude rewrite of its stored text | the same plus `--rewrite`: the page shows the Claude disclosure line and the `paper_published` notice goes out |
| Legacy paper, rewrite from a fresh Theo run RUN on its question (#17, #18) | `studio paper pull <id> --dossier-from <RUN>` (RUN must be `researched`), write as in step 2, steps 3-5, `paper bundle`, then `studio paper correct <id> --text '<entry>' --republish`. **Never `paper publish`**: it refuses this workspace. The first republish sends RUN as `dossier_request_id` and theo_publish closes RUN as `cancelled` |

- Legacy rewrites run only when the owner asks; the owner picks the basis per paper (#18).
- An evidence id is never renumbered or reused; it is retired only by an entry that names it
  (`--evidence-id`). The studio never fills `result.corrections` (it is always `[]`).
- A log-only correction re-runs the quality gate on the stored text. 9 legacy papers fail it
  there: send their entry with a `--report-file` text that passes `validate_paper_artifact`.
  `mogollon-pithouse-sites-across-the-upper-gila` changes only through a full `--republish`.

## When theo_publish refuses or the outcome is unknown

| Signal | Meaning | Do |
|---|---|---|
| exit 1, "refused: failing gates [...]" | a gate failed, nothing written | fix the paper, `paper check`, run again |
| "the paper is already public: change it with `paper correct`" | the row is public | this is a correction, not a publish |
| exit 2, "refused the input" | the payload broke the contract | stop and report: a bug in the studio or theo_publish |
| exit 3, "the row changed underneath" | nothing committed | read the journal row (below) to see what changed it, then `paper check` and run again |
| exit 4, a timeout, no JSON: `RemoteOutcomeUnknown` | the write may have committed | the adoption procedure |

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

## Stop conditions

- **Stop and report to the owner:** the list is empty; the paper is published or the correction
  applied (report slug, url, side effects); a gate cannot pass without bending a rule (too few
  supported claims for 5,000 words, no hero image among the checked images); exit 2; an
  unknown outcome whose journal row cannot be read.
- **Do not stop** between `paper pull` and the publish to ask for approval.

## Never

- Edit `paper.md`, `sources.json`, `check_report.json`, `bundle.json`, `published_bundle.json`
  (except in the adoption procedure) or the handoff files (`tasks.jsonl`, `pending.jsonl`,
  `prompts/`, `accepted.json`, `verdicts.jsonl`).
- Keep an evidence entry the claim check did not support, or give one another verdict.
- Write to the production database or copy files to the VPS by hand: the CLIs are the only path.
- Re-run a write whose outcome is unknown before reading the journal.
- Use `--rewrite` for a small fix, or `paper publish` for a paper that is already public.
- Touch Theo's topic queue (the owner's decision) or set `DISCORD_WEBHOOK_URL`.
