export const meta = {
  name: 'wd2-image',
  description: 'Lane WD2 served image: read, pre-check, vision check of every served image (one fresh Opus agent per batch), replacement stage, plan - state-aware, shared agent pool',
  phases: [
    { title: 'Operate', detail: 'read, precheck, export, import, plan' },
    { title: 'Answer', detail: 'fresh Opus agents, one per batch (they open the pictures)' },
  ],
}
const MAIN = 'C:/PythonProjects/AncientMap'
const PY = `${MAIN}/.venv/Scripts/python.exe`
const { width, run, handoff } = args
const PRE = `cd ${MAIN} && export PYTHONIOENCODING=utf-8 && PY=${PY} && S=scripts/remediation/served_image/run.py && R=${run} && H=${handoff} && OH=scripts/remediation/opus_handoff.py`
const ST = { type: 'object', properties: { ok: { type: 'boolean' }, nothing: { type: 'boolean' }, batches: { type: 'array', items: { type: 'string' } }, summary: { type: 'string' } }, required: ['ok', 'nothing', 'batches', 'summary'] }
const OPS = { type: 'object', properties: { ok: { type: 'boolean' }, summary: { type: 'string' } }, required: ['ok', 'summary'] }
const opText = (t) => `You are an operator of lane WD2 (served image, O6) of the AncientMap remediation. You run commands exactly and report; you answer no model question and edit no file. Every command is one bash call starting with this prefix:\n  ${PRE}\nRead each tool's own output (JSON, exit code), never only a wrapper's status. Runbook: docs/procedures/WD2_SERVED_IMAGE_AND_SCOPE.md section 3.5.\n\n${t}\n\nOn a refusal or non-zero exit you cannot resolve as described: ok=false and the last 30 lines in summary.`
let active = 0
const waiting = []
const acquire = () => new Promise((resolve) => { if (active < width) { active++; resolve() } else waiting.push(resolve) })
const release = () => { const n = waiting.shift(); if (n) n(); else active-- }
const answer = async (stage, b) => {
  await acquire()
  try {
    return await agent(`You are a fresh agent (Claude Sonnet 5.5) of lane WD2 (served image of ancient sites: does the picture show the site?) of the AncientMap remediation, stage ${stage}, batch ${b}. You answered no other batch. Work in ${MAIN} (cd there). Run and read completely - it is your full instruction:\n  cd ${MAIN} && PYTHONIOENCODING=utf-8 ${PY} scripts/remediation/served_image/run.py brief --run-dir ${run} --handoff ${handoff}-${stage} --batch-id ${b}\nFollow it exactly: open each picture with your Read tool, judge it, check your answer with the brief's check-answer command until it passes, then record it with opus_handoff.py answer as the brief says, with --model claude-sonnet-5-5 (the model you run as; where the brief says "Opus agent", that is you; write-once; SKIP every label already recorded). Scratch files only in ${handoff}-${stage}-scratch/${b}/. Modify no other file. No personal data in any web request.\nFinal answer (one line): "${b}: N recorded, M skipped, K failed (reasons)".`, { label: `img:${stage}:${b}`, phase: 'Answer', model: 'sonnet', effort: 'high' })
  } finally { release() }
}
const out = {}
const prep = await agent(opText(`Prepare the run: if ${run}/READ.json does not exist run $PY $S read --run-dir $R. If ${run}/PRECHECK.json does not exist run $PY $S precheck --run-dir $R. Report both as done in the summary.`), { label: 'prepare', phase: 'Operate', schema: OPS, model: 'sonnet', effort: 'low' })
out.prepare = prep
if (!prep || !prep.ok) return out
for (const stage of ['check', 'replace']) {
  const H = `${handoff}-${stage}`
  const st = await agent(opText(`State of stage ${stage}:
- If ${run}/${stage === 'check' ? 'CHECK.jsonl' : 'REPLACE.jsonl'} exists, the stage is imported: nothing=true, batches=[].
- Else if the directory ${H} exists: $PY $OH validate --dir ${H}; batches = the distinct batch_id values of its "missing" list (empty if all answered; malformed or stale answers: ok=false). nothing=false.
- Else export: ${stage === 'check' ? '$PY $S export-check --run-dir $R --handoff ' + H : '$PY $S export-replace --run-dir $R --handoff ' + H + ' (it prints "questions": N; with N = 0 no handoff exists: nothing=true, batches=[])'}. batches = the folders of ${H} that contain a MANIFEST.jsonl. nothing=false.`), { label: `state:${stage}`, phase: 'Operate', schema: ST, model: 'sonnet', effort: 'medium' })
  out[stage] = { st }
  if (!st || !st.ok) return out
  if (st.nothing) continue
  if (st.batches.length > 0) await parallel(st.batches.map((b) => () => answer(stage, b)))
  const im = await agent(opText(`Steps: (1) $PY $OH validate --dir ${H} -> must be clean (0 missing/stale/malformed/orphans); (2) $PY $S import-${stage} --run-dir $R -> report its summary (counts per verdict, unfetchable).`), { label: `import:${stage}`, phase: 'Operate', schema: OPS, model: 'sonnet', effort: 'low' })
  out[stage].im = im && im.summary
  if (!im || !im.ok) return out
}
const pl = await agent(opText(`Step: $PY $S plan --run-dir $R -> report PLAN_SUMMARY.json (chunks, per outcome counts).`), { label: 'plan', phase: 'Operate', schema: OPS, model: 'sonnet', effort: 'low' })
out.plan = pl
return out
