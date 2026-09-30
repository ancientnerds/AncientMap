export const meta = {
  name: 'wd1-handoff-pool',
  description: 'Lane WD1 structured fields: Opus research agents answer one run round by round (r0 + up to two re-asks), an operator exports, validates and imports; pilot gate at the end',
  phases: [
    { title: 'Answer', detail: 'one fresh Opus agent per batch of 8 sites' },
    { title: 'Operate', detail: 'export, validate, import, re-ask, pilot report' },
  ],
}
const MAIN = 'C:/PythonProjects/AncientMap'
const PY = `${MAIN}/.venv/Scripts/python.exe`
const { run, ho, pilot, width } = args
const PRE = `cd ${MAIN} && export PYTHONIOENCODING=utf-8 && PY=${PY} && F=scripts/remediation/fields && OH=scripts/remediation/opus_handoff.py && RUN=${run} && HO=${ho}`
const OPS = {
  type: 'object',
  properties: { ok: { type: 'boolean' }, batches: { type: 'array', items: { type: 'string' } }, reask_fields: { type: 'integer' }, summary: { type: 'string' } },
  required: ['ok', 'batches', 'reask_fields', 'summary'],
}
const op = (text, label) => agent(`You are the operator of lane WD1 (structured fields) of the AncientMap remediation. You run commands exactly and report; you answer no model question and edit no file. Every command is one bash call starting with this prefix:\n  ${PRE}\nRead each tool's own output (JSON, exit code), never only a wrapper's status. Runbook: docs/procedures/FIELDS_WD1.md section 3.3 - read it once.\n\n${text}\n\nOn any refusal or non-zero exit: ok=false and the last 30 lines of that output in summary.`, { label, phase: 'Operate', schema: OPS })
const answer = (round, b) => agent(`You are a fresh Opus research agent of lane WD1 (structured fields) of the AncientMap remediation, round ${round}, batch ${b}. Work in ${MAIN} (cd there). Run and read completely - it is your full instruction:\n  cd ${MAIN} && PYTHONIOENCODING=utf-8 ${PY} scripts/remediation/fields/handoff.py brief --run ${run} --handoff ${ho}-${round} --batch-id ${b}\nFollow it exactly, site by site: research on the web yourself, quote verbatim from the pages you cite, check every answer with handoff.py check-answer until it passes, then record it with opus_handoff.py answer as the brief says (write-once; skip labels already recorded). Scratch files only in ${ho}-${round}-scratch/${b}/. Modify no other file. No personal data in any web request; User-Agent 'AncientMapRemediation/1.0 (research; https://ancientnerds.com)'. If WebSearch is exhausted, search via curl (Wikipedia/Wikidata APIs, https://html.duckduckgo.com/html/?q=..., Nominatim).\nFinal answer (one line): "${b}: N recorded, M skipped, K failed (reasons)".`, { label: `${round}:${b}`, phase: 'Answer' })
const answerAll = async (round, batches) => {
  let next = 0
  const worker = async () => {
    while (next < batches.length) {
      const b = batches[next++]
      await answer(round, b)
    }
  }
  await parallel(Array.from({ length: Math.min(width, batches.length) }, () => worker))
}
const log_ = []
let ex = await op(`Step: $PY $F/handoff.py export --run $RUN --handoff $HO-r0   -> report the batch ids (folder names in $HO-r0 that hold a MANIFEST.jsonl) and the question count in summary; reask_fields=0.`, 'export:r0')
log_.push({ round: 'r0', ex })
if (!ex || !ex.ok) return log_
let round = 'r0'
let batches = ex.batches
for (let n = 0; n < 3; n++) {
  await answerAll(round, batches)
  const im = await op(`Steps: (1) $PY $OH validate --dir $HO-${round}   -> 0 missing/stale/malformed/orphans, else stop; (2) $PY $F/handoff.py import --run $RUN   -> report its summary (counted, refetched, decisions); (3) report reask_fields = the number of fields REASK.json ($RUN/REASK.json) names; (4) $PY $F/handoff.py status --run $RUN   -> summary. batches=[].`, `import:${round}`)
  log_.push({ round, im })
  if (!im || !im.ok) return log_
  if (im.reask_fields === 0 || n === 2) break
  const next = `r${n + 1}`
  const re = await op(`Step: $PY $F/handoff.py export-reask --run $RUN --handoff $HO-${next}   -> report the batch ids (folders with a MANIFEST.jsonl in $HO-${next}); reask_fields=0.`, `export:${next}`)
  log_.push({ round: next, re })
  if (!re || !re.ok || re.batches.length === 0) break
  round = next
  batches = re.batches
}
if (pilot) {
  const pr = await op('Step: $PY $F/handoff.py pilot-report --run $RUN   -> report its exit code (0 PASS, 1 STOP), the overall and per-country cleared-on-exhaustion rates and stopped_by; ok=true if the command ran (whatever PASS/STOP), put "PASS" or "STOP" first in summary.', 'pilot-report')
  log_.push({ step: 'pilot-report', pr })
}
return log_
