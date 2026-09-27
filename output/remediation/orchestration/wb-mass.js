export const meta = {
  name: 'wb-mass',
  description: 'Lane WB mass run in chunks: sequential selects (each excluding every earlier run), then every chunk through write/check/rewrite/verify stages with a shared agent pool, then outcomes',
  phases: [
    { title: 'Select', detail: 'one select per chunk, sequential' },
    { title: 'Stage', detail: 'operator export and import per stage and chunk' },
    { title: 'Answer', detail: 'fresh Opus agents under a shared pool' },
  ],
}
const MAIN = 'C:/PythonProjects/AncientMap'
const PY = `${MAIN}/.venv/Scripts/python.exe`
const { prefix, chunks, size, seedBase, excludeRuns, bases, width } = args
const RUNS_DIR = 'output/remediation/teaser/runs'
const STAGES = ['write', 'check', 'rewrite1', 'check1', 'rewrite2', 'check2', 'verify', 'rewrite-v', 'check-v', 'verify2']
const PRE = `cd ${MAIN} && export PYTHONIOENCODING=utf-8 && PY=${PY} && T=scripts/remediation/teaser/run.py && OH=scripts/remediation/opus_handoff.py`
const OPS = { type: 'object', properties: { ok: { type: 'boolean' }, batches: { type: 'array', items: { type: 'string' } }, questions: { type: 'integer' }, summary: { type: 'string' } }, required: ['ok', 'batches', 'questions', 'summary'] }
const op = (text, label) => agent(`You are an operator of lane WB (teaser cards) of the AncientMap remediation. You run commands exactly and report; you answer no model question and edit no file. Every command is one bash call starting with this prefix:\n  ${PRE}\nRead each tool's own output (JSON / exit lines), never only a wrapper's status. Runbook: docs/procedures/CARD_DESCRIPTIONS.md section 5 (5.1, 5.3).\n\n${text}\n\nOn any refusal or non-zero exit: ok=false and the last 30 lines of that output in summary.`, { label, phase: 'Stage', schema: OPS })
let active = 0
const waiting = []
const acquire = () => new Promise((resolve) => { if (active < width) { active++; resolve() } else waiting.push(resolve) })
const release = () => { const next = waiting.shift(); if (next) next(); else active-- }
const answer = async (run, stage, b) => {
  await acquire()
  try {
    const handoff = `output/remediation/handoff/teaser-${run}-${stage}`
    return await agent(`You are a fresh Opus agent of lane WB (teaser cards) of the AncientMap remediation, run ${run}, stage ${stage}, batch ${b}. You have worked on no other batch of this lane. Work in ${MAIN} (cd there). Run and read completely - it is your full instruction:\n  cd ${MAIN} && PYTHONIOENCODING=utf-8 ${PY} scripts/remediation/teaser/run.py brief --run ${RUNS_DIR}/${run} --handoff ${handoff} --batch-id ${b}\nFollow it exactly: check every answer with run.py check-answer until it prints "ok": true, then record it with opus_handoff.py answer --answered-by teaser-${run}-${b} (write-once; skip labels already recorded). Scratch files only in ${handoff}-scratch/${b}/. Modify no other file. No personal data in any web request; User-Agent 'AncientMapRemediation/1.0 (research; https://ancientnerds.com)'. If WebSearch is exhausted, search via curl (Wikipedia/Wikidata APIs, https://html.duckduckgo.com/html/?q=...).\nFinal answer (one line): "${b}: N recorded, M skipped, K failed (reasons)".`, { label: `${run}:${stage}:${b}`, phase: 'Answer' })
  } finally {
    release()
  }
}
phase('Select')
const runs = []
const excl = excludeRuns.slice()
const basisArgs = bases.map((b) => `--basis ${b}`).join(' ')
for (let i = 1; i <= chunks; i++) {
  const run = `${prefix}-${String(i).padStart(2, '0')}`
  const exArgs = excl.map((r) => `--exclude-run ${r}`).join(' ')
  const sel = await op(`Step: $PY $T select --run ${RUNS_DIR}/${run} --pilot ${size} --seed ${seedBase + i} ${exArgs} ${basisArgs}   -> report how many sites were drawn (questions) and the counts per listing reason. If select refuses because fewer than ${size} candidates remain, run it once more without --pilot and --seed (all remaining candidates) and report that. If no candidate is left at all, ok=true and questions=0.`, `select:${run}`)
  if (!sel || !sel.ok || sel.questions === 0) break
  runs.push(run)
  excl.push(`${RUNS_DIR}/${run}`)
  if (sel.questions < size) break
}
log(`chunks selected: ${runs.join(', ')}`)
const results = await pipeline(runs, async (run) => {
  const out = { run, stages: [] }
  for (const stage of STAGES) {
    const ex = await op(`Step: $PY $T export --run ${RUNS_DIR}/${run} --stage ${stage} --handoff output/remediation/handoff/teaser-${run}-${stage}   -> report "questions" and the batch ids (folder names in that handoff directory). If "questions": 0, batches=[].`, `export:${run}:${stage}`)
    if (!ex || !ex.ok) { out.stages.push({ stage, ex }); return out }
    if (ex.questions === 0 || ex.batches.length === 0) continue
    await parallel(ex.batches.map((b) => () => answer(run, stage, b)))
    const im = await op(`Steps: (1) $PY $OH validate --dir output/remediation/handoff/teaser-${run}-${stage}   -> 0 missing/stale/malformed/orphans; (2) $PY $T import --run ${RUNS_DIR}/${run} --stage ${stage}   -> report failures or verdicts (and transient_failures: if not empty, run the import once more); (3) $PY $T status --run ${RUNS_DIR}/${run}   -> states. batches=[] questions=0.`, `import:${run}:${stage}`)
    out.stages.push({ stage, questions: ex.questions, im: im && im.summary })
    if (!im || !im.ok) return out
  }
  const oc = await op(`Step: $PY $T outcomes --run ${RUNS_DIR}/${run}   -> report accepted / cleared counts (with reasons) and the number of description defects. batches=[] questions=0.`, `outcomes:${run}`)
  out.outcomes = oc && oc.summary
  return out
})
return { runs, results }
