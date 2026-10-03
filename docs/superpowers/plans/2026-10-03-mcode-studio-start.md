# Start brief for MiniMax Code (mcode) - the studio, 2026-10-03

You take over the studio from Claude Code (owner decision 2026-10-03: MiniMax Code replaces Claude
Code; FINISH_PLAN section 8 in the main checkout). A second mcode session works in the main checkout
`C:\PythonProjects\AncientMap` on the sites remediation at the same time - never touch that checkout's
files or branches. Work autonomously; ask the owner only what the memory and the owner-questions file
do not decide.

## 0. Read first
1. Owner memory `C:\Users\marti\.claude\projects\C--PythonProjects-AncientMap\memory\MEMORY.md`
   (Critical Rules), then `project-theo-youtube-studio.md` (all owner decisions - never re-ask them),
   `feedback-no-deepseek-opus-only.md`, `reference-minimax-code-cli.md`.
2. This worktree's `CLAUDE.md`, `docs/procedures/STUDIO.md` (the runbook; section 0 first),
   `docs/procedures/PROJECT_LESSONS.md`, the skills `.claude/skills/{theo-write,studio-video,
   studio-casefile}/SKILL.md`, `docs/superpowers/plans/2026-09-26-00-index.md` and
   `docs/superpowers/plans/2026-09-26-owner-questions.md`.

## 1. State (read 2026-10-03 from production, read-only)
- Release live: migrations 0025/0026 applied, `theo_publish`/`theo_dossier`/`studio.ledger_cli`
  import in the API image, API commit `893aa8cb` = `origin/main`. `studio_episodes` 0 rows,
  `theo_paper_publications` 1 row. Theo is stopped (`THEO_WORKER_DISABLED=1`, owner Q1).
- `feat/studio` is 3 commits ahead of `origin/main` (e2a963d check workflows on Sonnet, 502f8d9 repo
  argument for the check workflows, 9c7ed7c cache drop on publish/correct). Not pushed.
- Open acceptance (memory): (a) dry run of 95fa3798, (c) Baalbek claim-5 slice = first pilot video with
  the full package (MP4, SRT, description, thumbnails; no upload), (d) the Roswell correction
  (7 vs 8 July 1947, the first real corrections-log entry). (b) waits for the owner's Theo restart.

## 2. Build - the studio on MiniMax Code (branch `feat/studio`, tests first, gates green)
- **The check workflows** `.claude/workflows/{theo-claim-check,theo-image-check,studio-casefile-verify,
  studio-marker-check}.js` run only in Claude Code's Workflow runtime. Replace them with a Python
  driver (one module, e.g. `pipeline/studio/mcode_checks.py` + CLI) that answers each handoff's
  `pending.jsonl` through `mcode exec --model minimax/MiniMax-M3.1-Flash-Preview --effort max
  --permission full --timeout ... --output-format json`, one run per task (verifier) and one
  independent run per `supported` answer (skeptic - a fresh session, never the verifier's), with the
  same instructions the JS scripts give. Answers are written to a file and validated by a script
  before they count (mcode's `--output-schema` does not work with M3.1 - see the memory); after every
  run check that no tracked file changed (`git status --porcelain`). `answered_by` / `skeptic_by` name
  the real model and run id. Concurrency: start at 2, raise while no 429 appears, halve on one; RAM
  cap ~14. Quota stop at <= 10 % weekly (`/v1/token_plan/remains`, key `LYRA_MINIMAX_API_KEY` from
  `.env`, never print it). The remediation's driver (`scripts/remediation/mcode_driver.py`, being
  built in the main checkout) solves the same problem - once it is merged to `main`, reuse its
  mcode-call/429/quota parts instead of duplicating them (owner rule: never duplicate utilities).
- **The paper and video sessions** (`theo-write`, `studio-video`, `studio-casefile` skills) were written
  for Claude: replace Claude-only tool names and "Opus/Sonnet" model rules with mcode equivalents;
  any model string recorded in a paper, a ledger row, a provenance or a public AI disclosure names
  the real model. Where a public disclosure names "Claude", use one combined disclosure naming both
  families (owner decision O19 of 2026-10-03, as in the remediation), existing publications keep theirs.
- **Calibration before any MiniMax verdict gates a publish:** re-answer the already-accepted claim-check
  and image-check tasks of the published paper (the one `theo_paper_publications` row; its workspace
  holds `accepted.json`) with the new driver into a copy; pass = >= 90 % agreement and 0 false sources
  (owner O18). Record the numbers in the plan index. A failed check type holds and goes to the owner.

## 3. Release and acceptance
- Push rule (memory): pure code with green gates may go to `main` without asking; migrations, compose,
  CI, secrets, data deletion, publishing: ask. Merge `origin/main` before every push, push a fixed SHA,
  check the deploy's `commit` field afterwards (drift guard).
- **Push lock shared with the remediation session:** a deploy re-imports
  `public/data/card_descriptions.json`, so a push between the remediation's card write and its own
  push overwrites new cards. Before pushing, the file `C:\PythonProjects\AncientMap\.git\main-push.lock`
  must not exist; create it with your session name and UTC time, push, wait for the deploy to finish,
  delete it. If it exists, wait and retry (it is the other session's).
- Then acceptance (a), (c), (d) per the runbook and the memory; the video release gate is the final
  video only (owner) - the pilot package goes to the owner, no upload.
