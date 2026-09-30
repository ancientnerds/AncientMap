export const meta = {
  name: 'wb-continue',
  description: 'Lane WB: continue chunk runs from whatever stage they stopped at (answer only the missing labels, import, next stage), shared agent pool, then outcomes',
  phases: [
    { title: 'Stage', detail: 'operator: state, export, import per stage and chunk' },
    { title: 'Answer', detail: 'fresh Opus agents, only batches with missing answers' },
  ],
}
const MAIN = 'C:/PythonProjects/AncientMap'
const PY = `${MAIN}/.venv/Scripts/python.exe`
const { runs, width } = args
const RUNS_DIR = 'output/remediation/teaser/runs'
const STAGES = ['write', 'check', 'rewrite1', 'check1', 'rewrite2', 'check2', 'verify', 'rewrite-v', 'check-v', 'verify2']
const PRE = `cd ${MAIN} && export PYTHONIOENCODING=utf-8 && PY=${PY} && T=scripts/remediation/teaser/run.py && OH=scripts/remediation/opus_handoff.py`
const STATE = { type: 'object', properties: { ok: { type: 'boolean' }, state: { type: 'string', enum: ['imported', 'nothing', 'needs-answers', 'needs-import'] }, batches: { type: 'array', items: { type: 'string' } }, summary: { type: 'string' } }, required: ['ok', 'state', 'batches', 'summary'] }
const OPS = { type: 'object', properties: { ok: { type: 'boolean' }, summary: { type: 'string' } }, required: ['ok', 'summary'] }
const opText = (t) => `You are an operator of lane WB (teaser cards) of the AncientMap remediation. You run commands exactly and report; you answer no model question and edit no file. Every command is one bash call starting with this prefix:\n  ${PRE}\nRead each tool's own output (JSON / exit lines), never only a wrapper's status. Runbook: docs/procedures/CARD_DESCRIPTIONS.md section 5.1.\n\n${t}\n\nOn a refusal you cannot resolve as described, or a non-zero exit: ok=false and the last 30 lines in summary.`
let active = 0
const waiting = []
const acquire = () => new Promise((resolve) => { if (active < width) { active++; resolve() } else waiting.push(resolve) })
const release = () => { const next = waiting.shift(); if (next) next(); else active-- }
const answer = async (run, stage, b) => {
  await acquire()
  try {
    const handoff = `output/remediation/handoff/teaser-${run}-${stage}`
    return await agent(`You are a fresh Opus agent of lane WB (teaser cards) of the AncientMap remediation, run ${run}, stage ${stage}, batch ${b}. You have worked on no other batch of this lane. Work in ${MAIN} (cd there). Run and read completely - it is your full instruction:\n  cd ${MAIN} && PYTHONIOENCODING=utf-8 ${PY} scripts/remediation/teaser/run.py brief --run ${RUNS_DIR}/${run} --handoff ${handoff} --batch-id ${b}\nFollow it exactly: check every answer with run.py check-answer until it prints "ok": true, then record it with opus_handoff.py answer --answered-by teaser-${run}-${b} (write-once; SKIP every label already recorded - an earlier agent may have answered part of this batch). Scratch files only in ${handoff}-scratch/${b}/. Modify no other file. No personal data in any web request; User-Agent 'AncientMapRemediation/1.0 (research; https://ancientnerds.com)'. If WebSearch is exhausted, search via curl (Wikipedia/Wikidata APIs, https://html.duckduckgo.com/html/?q=...).\nFinal answer (one line): "${b}: N recorded, M skipped, K failed (reasons)".`, { label: `${run}:${stage}:${b}`, phase: 'Answer' })
  } finally {
    release()
  }
}
const results = await pipeline(runs, async (run) => {
  const out = { run, stages: [] }
  for (const stage of STAGES) {
    const H = `output/remediation/handoff/teaser-${run}-${stage}`
    const st = await agent(opText(`Determine the state of stage ${stage} of run ${run}:
1. $PY $T status --run ${RUNS_DIR}/${run}  -> "rounds" lists EXPORTED stages, not imported ones. Read "states": if no site is in state "due ${stage}" (the key is absent), the stage is imported: state="imported", batches=[]. If sites are "due ${stage}", it is not imported: go on with step 2.
2. Otherwise, if the directory ${H} does not exist: $PY $T export --run ${RUNS_DIR}/${run} --stage ${stage} --handoff ${H}. If it prints "questions": 0 (nobody is due), state="nothing", batches=[]. If it exported questions, continue with step 3.
3. $PY $OH validate --dir ${H}  -> if ok true (every question answered): state="needs-import", batches=[]. If questions are missing: state="needs-answers" and batches = the distinct batch_id values of the "missing" list (malformed or stale answers: report ok=false).`), { label: `state:${run}:${stage}`, phase: 'Stage', schema: STATE })
    if (!st || !st.ok) { out.stages.push({ stage, st }); return out }
    if (st.state === 'imported' || st.state === 'nothing') continue
    if (st.state === 'needs-answers') await parallel(st.batches.map((b) => () => answer(run, stage, b)))
    const im = await agent(opText(`Steps: (1) $PY $OH validate --dir ${H}  -> must be clean (0 missing/stale/malformed/orphans); (2) $PY $T import --run ${RUNS_DIR}/${run} --stage ${stage}  -> report failures or verdicts (if transient_failures is not empty, run the import once more); (3) $PY $T status --run ${RUNS_DIR}/${run}  -> states.`), { label: `import:${run}:${stage}`, phase: 'Stage', schema: OPS })
    out.stages.push({ stage, im: im && im.summary })
    if (!im || !im.ok) return out
  }
  const oc = await agent(opText(`Step: $PY $T outcomes --run ${RUNS_DIR}/${run}  -> report accepted / cleared counts (with reasons) and the number of description defects.`), { label: `outcomes:${run}`, phase: 'Stage', schema: OPS })
  out.outcomes = oc && oc.summary
  return out
})
return results
