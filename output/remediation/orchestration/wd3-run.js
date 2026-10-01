export const meta = {
  name: 'wd3-run',
  description: 'Lane WD3 end to end (O13-O15): harvest refresh and build, the 80-site pilot through the pool, its gate and spot-check, the pilot wave, the main run, its wave, handoff and owner list - Sonnet 5.5 agents only',
  phases: [
    { title: 'Prepare', detail: 'FIELDS_WD3 4.1-4.2' },
    { title: 'Pilot', detail: 'pool, gate, spot-check, wave' },
    { title: 'Main', detail: 'pool, wave, handoff, owner list' },
  ],
}
// Owner decisions 2026-10-01: O12 (every agent Sonnet 5.5, set explicitly), O13 one source suffices,
// O14 nothing sourced -> the field stays empty (owner list), O15 coordinates: research, else keep (owner list).
const MAIN = 'C:/PythonProjects/AncientMap'
const PY = `${MAIN}/.venv/Scripts/python.exe`
const POOL = `${MAIN}/output/remediation/orchestration/wd3-handoff-pool.js`
const { width, pilotSeed, wavePilot, waveMain } = args
const PRE = `cd ${MAIN} && export PYTHONIOENCODING=utf-8 && PY=${PY} && F=scripts/remediation/fields && A=scripts/remediation/mechanical/apply.py && W3=output/remediation/fields/wd3 && W3P=output/remediation/fields/wd3-pilot && H=output/remediation/handoff/fields-wd3`
const OPS = { type: 'object', properties: { ok: { type: 'boolean' }, summary: { type: 'string' } }, required: ['ok', 'summary'] }
const op = (text, label, ph, effort) => agent(`You are the operator of lane WD3 (structured-field fill) of the AncientMap remediation. Never search the file system: no find over /, output/ or any large directory - open exactly the paths named here (ls of one named directory is fine). Never pipe a command into head or tail -n (on Windows the producer keeps running after head exits and piles up). You run commands exactly and report; you answer no model question and edit no file. Every command is one bash call starting with this prefix:\n  ${PRE}\nRead each tool's own output (JSON, exit code, *_EXIT= lines), never only a wrapper's status. Runbook: docs/procedures/FIELDS_WD3.md section 4.\n\n${text}\n\nOn any refusal or non-zero exit you cannot resolve as the runbook describes: ok=false and the last 30 lines in summary.`, { label, phase: ph, schema: OPS, model: 'sonnet', effort: effort || 'medium' })

phase('Prepare')
const prep = await op(`Runbook 4.1 and 4.2, state-aware (skip a step whose output exists and is from today's state; never build a run twice):
- If $W3/RUN.json and $W3P/RUN.json both exist, everything here is done: report their COUNTS.json and stop.
- 4.1: mkdir -p $W3 && cp -r output/remediation/fields/harvest $W3/harvest (only if $W3/harvest does not exist); $PY $F/harvest.py --root $W3/harvest export; straight after it $PY $F/population.py --out $W3 export; then $PY $F/harvest.py --root $W3/harvest fetch, re-run until it fetches nothing (it is paced; it may take ~30 minutes); then $PY $F/classify.py --root $W3/harvest unmapped must print [] (if not: ok=false, list the classes - mapping them needs a code change).
- 4.2: mkdir -p $W3P && cp $W3/STORED.jsonl $W3/LINKS.jsonl $W3/POINTS.jsonl $W3/SEEDS.jsonl $W3P/ ; $PY $F/population.py --out $W3P build --root $W3/harvest --pilot 80 --seed ${pilotSeed} ; $PY $F/population.py --out $W3 build --root $W3/harvest --without $W3P
Report from both COUNTS.json: population.fields, wd1_sourced_but_empty (must be {}), wd1_unseen_sites, journal_sourced_points count.`, 'prepare', 'Prepare', 'high')
if (!prep || !prep.ok) return { prep }

phase('Pilot')
const pilotLog = await workflow({ scriptPath: POOL }, { run: 'output/remediation/fields/wd3-pilot', ho: 'output/remediation/handoff/fields-wd3-pilot', pilot: true, width })
const pr = (pilotLog || []).find((x) => x && x.step === 'pilot-report')
const gate = pr && pr.pr && pr.pr.summary ? pr.pr.summary : ''
log(`WD3 pilot gate: ${gate.slice(0, 200)}`)
if (!gate.startsWith('PASS')) return { prep: prep.summary, pilotLog, stopped: 'pilot gate did not PASS' }
const spot = await agent(`You spot-check the WD3 pilot of the AncientMap remediation (runbook docs/procedures/FIELDS_WD3.md 4.4, "Spot-check a PASS anyway"), read-only: edit nothing, record nothing. In ${MAIN}/output/remediation/fields/wd3-pilot read DECISIONS.jsonl and the questions (the handoff output/remediation/handoff/fields-wd3-pilot-r0/*/ prompts) and pick up to 10 fields decided "unresolved" on sites whose question showed a Wikidata item or an English Wikipedia article. For each, open that article/item yourself (curl with User-Agent 'AncientMapRemediation/1.0 (https://ancientnerds.com; research)') and decide whether it plainly states the value (a construction/use start date for period_start, the kind of site for site_type, the site's own page for source_url, coordinates within 1 km for coordinates). Report checked, findable (how many the source plainly stated) and one line per field.`, { label: 'spot-check', phase: 'Pilot', model: 'sonnet', effort: 'high', schema: { type: 'object', properties: { checked: { type: 'integer' }, findable: { type: 'integer' }, details: { type: 'string' } }, required: ['checked', 'findable', 'details'] } })
log(`WD3 spot-check: ${spot ? spot.findable + ' of ' + spot.checked + ' findable' : 'no result'}`)
if (spot && spot.checked >= 5 && spot.findable * 2 > spot.checked) return { prep: prep.summary, pilotLog, spot, stopped: 'spot-check: more than half of the unresolved fields were findable - the brief needs work before the main run' }
const pw = await op(`Runbook 4.5 for the pilot: bash output/remediation/orchestration/wd3_wave.sh ${wavePilot} $W3P  -> report every step's outcome (written cells, SKIPPED reasons, ACCEPTED with 0 deviations) and the final status lines. Exit 0 and "WAVE ... DONE" is success.`, 'wave:pilot', 'Pilot', 'medium')
if (!pw || !pw.ok) return { prep: prep.summary, pilotLog, spot, pilotWave: pw }

phase('Main')
const mainLog = await workflow({ scriptPath: POOL }, { run: 'output/remediation/fields/wd3', ho: 'output/remediation/handoff/fields-wd3', pilot: false, width })
const mw = await op(`Runbook 4.5 for the main run: bash output/remediation/orchestration/wd3_wave.sh ${waveMain} $W3  -> report every step's outcome and the final status lines. Exit 0 and "WAVE ... DONE" is success.`, 'wave:main', 'Main', 'medium')
if (!mw || !mw.ok) return { prep: prep.summary, pilotLog, spot, pilotWave: pw.summary, mainLog, mainWave: mw }
const fin = await op(`Runbook 4.6 steps 13 and 17: $PY $F/plan.py handoff --stage wd3 --wave ${wavePilot} ; $PY $F/plan.py handoff --stage wd3 --wave ${waveMain} ; $PY $F/owner_list.py build --runs $W3P $W3 --final  -> report sites_written per wave, and the owner list's counts per field and reason.`, 'handoff+owner-list', 'Main', 'medium')
return { prep: prep.summary, spot, pilotWave: pw.summary, mainWave: mw.summary, final: fin && fin.summary }
