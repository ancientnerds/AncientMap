export const meta = {
  name: 'wa-v3d-handoff',
  description: 'Lane WA (Phase 4 v3): Opus selector and reviewer agents for 209 batches through the handoff, with serialized mass4 imports per group of 8 batches',
  phases: [
    { title: 'Select', detail: 'one Opus agent per batch (selector stage)' },
    { title: 'Import select', detail: 'serialized: select import, translate, assemble, verify, review export' },
    { title: 'Review', detail: 'one Opus agent per batch with review questions' },
    { title: 'Import review', detail: 'serialized: review import and holds' },
  ],
}

const WT = 'C:/PythonProjects/AncientMap/.claude/worktrees/p4-pilot'
const PY = 'C:/PythonProjects/AncientMap/.venv/Scripts/python.exe'
const RUN = `${WT}/output/remediation/phase4_runner/runs/v3d-2026-09-26`
const HSEL = `${WT}/output/remediation/handoff/p4-v3d-select`
const HREV = `${WT}/output/remediation/handoff/p4-v3d-review`
const { first, last, groupSize } = args
const batches = []
for (let n = first; n <= last; n++) batches.push(`p4-${n}`)
const groups = []
for (let i = 0; i < batches.length; i += groupSize) groups.push(batches.slice(i, i + groupSize))

const answerPrompt = (stage, b, handoff) => `You are an Opus ${stage} agent of the AncientMap Phase-4 v3d run, batch ${b}. Work in ${WT} (cd there first). If ${handoff}/${b}/MANIFEST.jsonl does not exist yet (the export may still be writing), wait with 'sleep 60' until it does (at most 45 minutes), then continue.
Run and read completely - it is your full instruction:
  cd ${WT} && PYTHONIOENCODING=utf-8 ${PY} scripts/remediation/phase4/handoff4.py brief --run-dir ${RUN} --handoff ${handoff} --batch-id ${b}
Follow it exactly, question by question: read every prompt fully, answer in exactly the required format, validate each answer with the brief's check-answer command before recording it with opus_handoff.py answer (answers are write-once; skip labels already recorded). Use scratch files unique to your batch. Do not modify any other file. Never put personal data into a web request.
Final answer (one line): "${b}: N recorded, M skipped (already recorded), K failed (reasons)".`

let lock = Promise.resolve()
const serial = (fn) => {
  const p = lock.then(fn)
  lock = p.catch(() => null)
  return p
}

const SHELL = `cd ${WT} && export PYTHONIOENCODING=utf-8 && PY=${PY} && M=output/remediation && R4=$M/phase4_runner && P4=scripts/remediation/phase4 && HF=$P4/handoff4.py && RUNNAME=v3d-2026-09-26 && RUN=$R4/runs/$RUNNAME && L=$M/logs/p4_v3d && H=$M/handoff/p4-v3d && ROUNDS="--plan $R4/PLAN4.v3d.jsonl --run-dir $RUN --log-dir $L --searches-off"`

const IMPORT_SCHEMA = {
  type: 'object',
  properties: {
    ok: { type: 'boolean' },
    imported: { type: 'array', items: { type: 'string' } },
    not_ready: { type: 'array', items: { type: 'string' } },
    review_batches: { type: 'array', items: { type: 'string' } },
    exit_lines: { type: 'string' },
    problems: { type: 'string' },
  },
  required: ['ok', 'imported', 'not_ready', 'review_batches', 'exit_lines', 'problems'],
}
const REVIEW_IMPORT_SCHEMA = {
  type: 'object',
  properties: {
    ok: { type: 'boolean' },
    imported: { type: 'array', items: { type: 'string' } },
    not_ready: { type: 'array', items: { type: 'string' } },
    exit_lines: { type: 'string' },
    holds: { type: 'string' },
    problems: { type: 'string' },
  },
  required: ['ok', 'imported', 'not_ready', 'exit_lines', 'problems'],
}

const importSelect = (g) => `You are the import operator of the AncientMap Phase-4 v3d run for the batch group ${g.join(' ')}. You only run commands and report; you answer no model question and edit no file.
First wait until the file C:/tmp/wa_run/EXPORT_DONE exists (check every 60 s, at most 60 minutes) - the selector export round must be finished before any other mass4 round runs.
Shell prefix for every command (one bash invocation each, prefix included):
  ${SHELL}
Steps (docs/procedures/PHASE4_V3_RUNBOOK.md steps 5-6 in ${WT}; read its section 5 once if anything is unclear):
1. For each batch B of the group: $PY $HF ready --handoff $H-select --run-dir $RUN --batch B ; a batch is ready only when it prints "ok": true. Let G be the ready batches (space-separated, each passed as '--only B' or as the runbook's --only syntax - check 'mass4.py --help' for how --only takes several batches).
2. $PY $P4/mass4.py $ROUNDS --live --only <G> --stages select --handoff-import $H-select   -> must end with STAGE_EXIT=0.
3. $PY $P4/mass4.py $ROUNDS --live --only <G> --stages translate --handoff-export $H-translate   -> lanes T/R are closed: expect no translate questions; if a $H-translate folder for these batches appears, STOP and report it (ok=false).
4. $PY $P4/mass4.py $ROUNDS --live --only <G> --stages translate,assemble,verify --handoff-import $H-translate   -> STAGE_EXIT=0.
5. $PY $P4/mass4.py $ROUNDS --live --only <G> --stages review --handoff-export $H-review   -> STAGE_EXIT=0.
6. review_batches = the batches of G that now have a folder with a MANIFEST.jsonl in $H-review.
Read every tool's own exit line (STAGE_EXIT=...), never a wrapper's status. If any step does not end with STAGE_EXIT=0, stop the sequence, report ok=false with the last 30 lines of that output in problems. Report the exit lines you saw.`

const importReview = (g) => `You are the import operator of the AncientMap Phase-4 v3d run for the review stage of the batch group ${g.join(' ')}. You only run commands and report; you edit no file.
Shell prefix for every command (one bash invocation each, prefix included):
  ${SHELL}
1. For each batch B of the group that has a folder in $H-review: $PY $HF ready --handoff $H-review --run-dir $RUN --batch B ; ready only on "ok": true. Batches of the group without a review folder have no review questions and are imported with the others.
2. $PY $P4/mass4.py $ROUNDS --live --only <the group's batches except the not-ready ones> --stages review --handoff-import $H-review   -> STAGE_EXIT=0 (check 'mass4.py --help' for how --only takes several batches).
3. $PY $P4/run4.py holds --run-dir $RUN   -> report its summary line(s) in holds.
Read each tool's own exit line. On any non-zero exit: stop, ok=false, last 30 lines in problems.`

const results = await pipeline(
  groups,
  (g) => parallel(g.map((b) => () => agent(answerPrompt('selector', b, HSEL), { label: `select:${b}`, phase: 'Select' }))),
  (sel, g) => serial(() => agent(importSelect(g), { label: `import-select:${g[0]}`, phase: 'Import select', schema: IMPORT_SCHEMA })),
  (imp, g) => {
    const rb = (imp && imp.review_batches) || []
    return parallel(rb.map((b) => () => agent(answerPrompt('reviewer', b, HREV), { label: `review:${b}`, phase: 'Review' }))).then(() => imp)
  },
  (imp, g) => serial(() => agent(importReview(g), { label: `import-review:${g[0]}`, phase: 'Import review', schema: REVIEW_IMPORT_SCHEMA })).then((rev) => ({ group: g, select_import: imp, review_import: rev })),
)
return results
