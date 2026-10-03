# Start brief for MiniMax Code (mcode) - 2026-10-03

You take over the AncientMap work from Claude Code (owner decision 2026-10-03, FINISH_PLAN section 8).
Work autonomously; ask the owner only for what section 8 and the memory do not decide.

## 0. Read first, in this order
1. The owner memory index `C:\Users\marti\.claude\projects\C--PythonProjects-AncientMap\memory\MEMORY.md`
   (Critical Rules), then `feedback-no-deepseek-opus-only.md` and `reference-minimax-code-cli.md`.
2. `CLAUDE.md` (in your context), `docs/procedures/PROJECT_LESSONS.md`.
3. `output/remediation/FINISH_PLAN_2026-09-26.md` sections 7 and 8 (decisions O17-O23),
   `output/remediation/HANDOVER.md` (traps), the newest AUDIT_LOG entries (tail of
   `output/remediation/AUDIT_LOG.md`).

## 1. Housekeeping (before any build)
- `git status`: the repo root holds strays of earlier sessions (UUID-named `*.json`, `dd.html`,
  `ddg_out.html`, `page.html`, `sz.html`, `vdoc.html`, `wmu.pdf`, `pam.txt`, `wp_en.txt`, `wp_sr.txt`) -
  look at each, delete agent scratch, report anything that is not scratch. `output/remediation/
  mechanical_country_b2/APPLY.sql` shows as modified (line endings only? check `git diff`), and
  `output/remediation/fields/wd3/`, `wd3-pilot/` and `mechanical_country_b2/REHEARSAL_ROLLBACK.sql` are
  untracked lane state - find in AUDIT_LOG whether they belong committed, then commit or leave them.
- The Claude Code workflow runs named in section 7 (`wf_...`) cannot be resumed here. Establish from the
  handoff directories and `status` commands of each lane where each one actually stands.

## 2. Build A - truthful stamp and combined disclosure (O19), in a worktree branch `wip/minimax-stamp`
- `scripts/remediation/opus_handoff.py`: `ANSWER_MODELS` accepts `MiniMax-M3.1-Flash-Preview` with its
  own stamp; `answer --model` records it. Every consumer of `ANSWER_MODELS` (e.g.
  `mechanical/scope_review._FAMILY_OF_STAMP`, which splits the model id on "-") must handle it - check
  each with grep.
- `phase4/model4.py`: a new combined `AI_SYSTEM` string naming "Claude (Anthropic) and MiniMax M3.1 Flash
  (MiniMax)" for new writes; the existing strings stay accepted for existing writes (follow how
  `AI_SYSTEM_OPUS` -> `AI_SYSTEM` was handled on 2026-10-01: `wip/model-stamp`, AUDIT_LOG). Every gate,
  verifier and acceptance that checks a fixed set of disclosure strings, and the frontend/API text that
  shows the disclosure, must agree.
- Tests first (TDD skill), then the full gate suite from CLAUDE.md; merge into `integrate/wave1`.

## 3. Build B - the driver that replaces Claude Code's Workflow tool (O22), branch `wip/mcode-driver`
- A Python driver (`scripts/remediation/mcode_driver.py`) that takes over what
  `output/remediation/orchestration/*.js` did: the operator steps (export, validate, import, re-ask,
  status, pilot-report) run as plain subprocess commands - no model; every answering batch is one
  `mcode exec --cwd C:\PythonProjects\AncientMap --model minimax/MiniMax-M3.1-Flash-Preview --effort max
  --permission full --timeout <t> --max-steps <n> --output-format json --diagnostics-dir <d>` with the
  same agent prompt the JS script used, but `--model MiniMax-M3.1-Flash-Preview` as the answer stamp.
- Per batch: keep the exec JSON (last stdout line), exit code and diagnostics; after the batch check
  `git status --porcelain` of tracked files is unchanged (else: stop, the batch is void) - an M3.1 run
  once rewrote a check file.
- Concurrency (O22): start at 2, add one concurrent run after each window without a 429/rate-limit
  error, halve on the first one; hard cap by local RAM (~14). Quota stop (O20): before each batch read
  `https://api.minimax.io/v1/token_plan/remains` (key `LYRA_MINIMAX_API_KEY` from `.env`, never print
  it); stop when `current_weekly_remaining_percent <= 10`, resume after the reset.
- Resumable from its own state file; a lane is driven by args equal to the JS scripts' args.
- Tests for the driver's logic (fake `mcode`), then gates; merge.

## 4. Calibration (O18) before any lane writes MiniMax answers to production
Per lane type still open (WC sentence check, WD3 field research, WB writer/checker, WD2 image, WN):
copy 2-3 already-answered batches into a separate handoff dir, let M3.1 (effort max) re-answer them
through the driver, compare with the recorded answers. Pass = >= 90 % agreement and 0 false sources
(spot-check every cited URL/quote of disagreements yourself). Record the numbers in AUDIT_LOG. A
failing lane holds and goes to the owner.

## 5. Then continue FINISH_PLAN section 7's order with the driver; every production write journalled as
before (rehearse, steps <= 100 sites, read back, rollback rehearsal, acceptance with 0 deviations).
Push rule: MEMORY.md (pushes to main without asking for pure code with green gates; ask for
migrations, compose, CI, secrets, data deletion, publishing).
