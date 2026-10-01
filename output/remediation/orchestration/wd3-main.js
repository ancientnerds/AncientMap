export const meta = {
  name: 'wd3-main',
  description: 'Lane WD3 main run after the passed pilot: answer the exported rounds through the pool (resume mode), write its wave, then handoff and owner list - Sonnet 5.5 agents only',
  phases: [
    { title: 'Main', detail: 'pool (resume), wave, handoff, owner list' },
  ],
}
// O12-O15 as in wd3-run.js. Used when the main run's r0 is already exported (wd3-run.js 2026-10-01 stopped
// after the export because the pool lost its batch list; wd3-handoff-pool.js now builds the ids from a count).
const MAIN = 'C:/PythonProjects/AncientMap'
const PY = `${MAIN}/.venv/Scripts/python.exe`
const POOL = `${MAIN}/output/remediation/orchestration/wd3-handoff-pool.js`
const { width, wavePilot, waveMain } = args
const PRE = `cd ${MAIN} && export PYTHONIOENCODING=utf-8 && PY=${PY} && F=scripts/remediation/fields && W3=output/remediation/fields/wd3 && W3P=output/remediation/fields/wd3-pilot`
const OPS = { type: 'object', properties: { ok: { type: 'boolean' }, summary: { type: 'string' } }, required: ['ok', 'summary'] }
const op = (text, label) => agent(`You are the operator of lane WD3 (structured-field fill) of the AncientMap remediation. You run commands exactly and report; you answer no model question and edit no file. Every command is one bash call starting with this prefix:\n  ${PRE}\nRead each tool's own output (JSON, exit code, *_EXIT= lines), never only a wrapper's status. Runbook: docs/procedures/FIELDS_WD3.md section 4.\n\n${text}\n\nOn any refusal or non-zero exit you cannot resolve as the runbook describes: ok=false and the last 30 lines in summary.`, { label, phase: 'Main', schema: OPS, model: 'sonnet', effort: 'medium' })

phase('Main')
const mainLog = await workflow({ scriptPath: POOL }, { run: 'output/remediation/fields/wd3', ho: 'output/remediation/handoff/fields-wd3', pilot: false, width, resume: true })
const imports = (mainLog || []).filter((x) => x && x.im)
const lastImport = imports.length ? imports[imports.length - 1].im : null
if (!lastImport || !lastImport.ok) return { mainLog, stopped: 'the main run did not import cleanly' }
const mw = await op(`Runbook 4.5 for the main run: bash output/remediation/orchestration/wd3_wave.sh ${waveMain} $W3  -> report every step's outcome (written cells per field, SKIPPED reasons, ACCEPTED with 0 deviations) and the final status lines. Exit 0 and "WAVE ... DONE" is success.`, 'wave:main')
if (!mw || !mw.ok) return { mainLog, mainWave: mw }
const fin = await op(`Runbook 4.6 steps 13 and 17: $PY $F/plan.py handoff --stage wd3 --wave ${wavePilot} ; $PY $F/plan.py handoff --stage wd3 --wave ${waveMain} ; $PY $F/owner_list.py build --runs $W3P $W3 --final  -> report sites_written per wave, and the owner list's counts per field and reason.`, 'handoff+owner-list')
return { mainWave: mw.summary, final: fin && fin.summary }
