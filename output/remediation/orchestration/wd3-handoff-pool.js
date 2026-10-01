export const meta = {
  name: 'wd3-handoff-pool',
  description: 'Lane WD3 structured-field fill: Sonnet 5.5 research agents answer one run round by round (r0 + up to two re-asks), a Sonnet 5.5 operator exports, validates and imports (O12); pilot gate at the end',
  phases: [
    { title: 'Answer', detail: 'one fresh Sonnet 5.5 agent per batch of 8 sites' },
    { title: 'Operate', detail: 'export, validate, import, re-ask, pilot report' },
  ],
}
const MAIN = 'C:/PythonProjects/AncientMap'
const PY = `${MAIN}/.venv/Scripts/python.exe`
const { run, ho, pilot, width, resume } = args
// A long batch list does not survive a structured answer (2026-10-01: 327 ids came back as one string
// "wd3-r0-b0001 through wd3-r0-b0327"), so the operator reports the COUNT of batch folders and the
// first and last folder names, and the script builds the ids from the export's own naming.
const ids = (round, st) => {
  const n = st.batch_count
  const made = Array.from({ length: n }, (_, i) => `wd3-${round}-b${String(i + 1).padStart(4, '0')}`)
  if (n > 0 && (made[0] !== st.first_batch || made[n - 1] !== st.last_batch)) throw new Error(`batch names ${st.first_batch}..${st.last_batch} are not wd3-${round}-b0001..b${String(n).padStart(4, '0')}`)
  return made
}
const PRE = `cd ${MAIN} && export PYTHONIOENCODING=utf-8 && PY=${PY} && F=scripts/remediation/fields && OH=scripts/remediation/opus_handoff.py && RUN=${run} && HO=${ho}`
const OPS = {
  type: 'object',
  properties: { ok: { type: 'boolean' }, batch_count: { type: 'integer' }, first_batch: { type: 'string' }, last_batch: { type: 'string' }, reask_fields: { type: 'integer' }, summary: { type: 'string' } },
  required: ['ok', 'batch_count', 'first_batch', 'last_batch', 'reask_fields', 'summary'],
}
const op = (text, label) => agent(`You are the operator of lane WD3 (structured-field fill) of the AncientMap remediation. Never search the file system: no find over /, output/ or any large directory - open exactly the paths named here (ls of one named directory is fine). Never pipe a command into head or tail -n (on Windows the producer keeps running after head exits and piles up). You run commands exactly and report; you answer no model question and edit no file. Every command is one bash call starting with this prefix:\n  ${PRE}\nRead each tool's own output (JSON, exit code), never only a wrapper's status. Runbook: docs/procedures/FIELDS_WD3.md section 4 - read it once.\n\n${text}\n\nOn any refusal or non-zero exit: ok=false and the last 30 lines of that output in summary.`, { label, phase: 'Operate', schema: OPS, model: 'sonnet', effort: 'medium' })
const answer = (round, b) => agent(`You are a fresh Sonnet 5.5 research agent of lane WD3 (structured-field fill) of the AncientMap remediation, round ${round}, batch ${b}. Work in ${MAIN} (cd there). Run and read completely - it is your full instruction:\n  cd ${MAIN} && PYTHONIOENCODING=utf-8 ${PY} scripts/remediation/fields/handoff.py brief --run ${run} --handoff ${ho}-${round} --batch-id ${b}\nFollow it exactly, site by site: research on the web yourself, quote verbatim from the pages you cite, check every answer with handoff.py check-answer until it passes, then record it with opus_handoff.py answer as the brief says (write-once; skip labels already recorded). Scratch files only in ${ho}-${round}-scratch/${b}/. Modify no other file. No personal data in any web request; User-Agent 'AncientMapRemediation/1.0 (https://ancientnerds.com; research)'. If WebSearch is exhausted, search via curl (Wikipedia/Wikidata APIs, https://html.duckduckgo.com/html/?q=..., Nominatim).\nRecord every answer with --model claude-sonnet-5-5 (the brief prints it). Final answer (one line): "${b}: N recorded, M skipped, K failed (reasons)".`, { label: `${round}:${b}`, phase: 'Answer', model: 'sonnet', effort: 'high' })
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
let ex = await op(resume ? `Round r0 was exported before (do NOT export again): in $HO-r0 report batch_count = the number of folders in that directory holding a MANIFEST.jsonl (ls -d <dir>/*/ then test each for MANIFEST.jsonl), first_batch and last_batch = the first and last of those folder names in sorted order; run $PY $OH validate --dir $HO-r0 and put its answered/missing counts in summary - validate exits 1 while answers are missing, which is expected here: ok=true unless it reports malformed, stale or orphan answers; reask_fields=0.` : `Step: $PY $F/handoff.py export --run $RUN --handoff $HO-r0   -> report batch_count = the number of folders in that directory holding a MANIFEST.jsonl (ls -d <dir>/*/ then test each for MANIFEST.jsonl), first_batch and last_batch = the first and last of those folder names in sorted order, and the question count in summary; reask_fields=0.`, resume ? 'count:r0' : 'export:r0')
log_.push({ round: 'r0', ex })
if (!ex || !ex.ok) return log_
let round = 'r0'
let batches = ids('r0', ex)
for (let n = 0; n < 3; n++) {
  await answerAll(round, batches)
  const im = await op(`Steps: (1) $PY $OH validate --dir $HO-${round}   -> 0 missing/stale/malformed/orphans, else stop; (2) $PY $F/handoff.py import --run $RUN   -> report its summary (counted, refetched, decisions); (3) report reask_fields = the number of fields REASK.json ($RUN/REASK.json) names; (4) $PY $F/handoff.py status --run $RUN   -> summary. batch_count=0, first_batch and last_batch empty.`, `import:${round}`)
  log_.push({ round, im })
  if (!im || !im.ok) return log_
  if (im.reask_fields === 0 || n === 2) break
  const next = `r${n + 1}`
  const re = await op(`Step: $PY $F/handoff.py export-reask --run $RUN --handoff $HO-${next}   -> report batch_count = the number of folders in that directory holding a MANIFEST.jsonl (ls -d <dir>/*/ then test each for MANIFEST.jsonl), first_batch and last_batch = the first and last of those folder names in sorted order (the directory $HO-${next}); reask_fields=0.`, `export:${next}`)
  log_.push({ round: next, re })
  if (!re || !re.ok || re.batch_count === 0) break
  round = next
  batches = ids(next, re)
}
if (pilot) {
  const pr = await op('Step: $PY $F/handoff.py pilot-report --run $RUN   -> report its exit code (0 PASS, 1 STOP), the overall and per-country held-as-unreadable and unresolved rates and stopped_by; ok=true if the command ran (whatever PASS/STOP), put "PASS" or "STOP" first in summary.', 'pilot-report')
  log_.push({ step: 'pilot-report', pr })
}
return log_
