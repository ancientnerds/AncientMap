export const meta = {
  name: 'wb-pilot-ws-3',
  description: 'Lane WB pilot 1 (20 sites, Phase-4 W/S texts): select, write/check/rewrite stages through the handoff, outcomes, independent web judge and its gate',
  phases: [
    { title: 'Stage', detail: 'operator export, one fresh Opus agent per batch, operator import' },
    { title: 'Judge', detail: 'independent web judges of the accepted cards' },
  ],
}
const MAIN = 'C:/PythonProjects/AncientMap'
const PY = `${MAIN}/.venv/Scripts/python.exe`
const RUN = 'output/remediation/teaser/runs/wb-pilot-2026-09-26c'
const H = 'output/remediation/handoff/teaser-wb-pilot-2026-09-26c'
const PRE = `cd ${MAIN} && export PYTHONIOENCODING=utf-8 && PY=${PY} && T=scripts/remediation/teaser/run.py && OH=scripts/remediation/opus_handoff.py && RUN=${RUN} && H=${H}`
const OPS = {
  type: 'object',
  properties: { ok: { type: 'boolean' }, batches: { type: 'array', items: { type: 'string' } }, questions: { type: 'integer' }, summary: { type: 'string' } },
  required: ['ok', 'batches', 'questions', 'summary'],
}
const op = (text, label) => agent(`You are the operator of lane WB (teaser cards) of the AncientMap remediation. You run commands exactly and report; you answer no model question and edit no file. Every command is one bash call starting with this prefix:\n  ${PRE}\nRead each tool's own output (its JSON / exit lines), never only a wrapper's status. The runbook is docs/procedures/CARD_DESCRIPTIONS.md section 5 - read 5.1 and 5.2 once.\n\n${text}\n\nOn any refusal or non-zero exit: ok=false and the last 30 lines of that output in summary.`, { label, phase: 'Stage', schema: OPS })
const answer = (stage, handoff, b, judge) => agent(`You are a fresh Opus agent of lane WB of the AncientMap remediation, ${judge ? 'an independent web judge' : `stage ${stage}`}, batch ${b}. You have worked on no other batch of this lane. Work in ${MAIN} (cd there). Run and read completely - it is your full instruction:\n  cd ${MAIN} && PYTHONIOENCODING=utf-8 ${PY} scripts/remediation/teaser/run.py brief --run ${RUN} --handoff ${handoff} --batch-id ${b}\nFollow it exactly: check every answer with run.py check-answer until it prints "ok": true, then record it with opus_handoff.py answer --answered-by teaser-${b} (write-once; skip labels already recorded). Scratch files only in ${handoff}-scratch/${b}/. Modify no other file. No personal data in any web request; User-Agent 'AncientMapRemediation/1.0 (research; https://ancientnerds.com)'. If WebSearch is exhausted, search via curl (Wikipedia/Wikidata APIs, https://html.duckduckgo.com/html/?q=...).\nFinal answer (one line): "${b}: N recorded, M skipped, K failed (reasons)".`, { label: `${stage}:${b}`, phase: judge ? 'Judge' : 'Stage' })

const log_ = []
const sel = await op('Step: $PY $T select --run $RUN --pilot 20 --seed 20260928 --exclude-run output/remediation/teaser/runs/wb-pilot-2026-09-26 --exclude-run output/remediation/teaser/runs/wb-pilot-2026-09-26b --basis W --basis S --basis T --basis R   -> report the counts per listing reason and per basis in summary; batches=[] questions=20 if 20 sites were drawn.', 'select')
log_.push({ step: 'select', sel })
if (!sel || !sel.ok) return log_
for (const stage of ['write', 'check', 'rewrite1', 'check1', 'rewrite2', 'check2', 'verify', 'rewrite-v', 'check-v', 'verify2']) {
  const ex = await op(`Step: $PY $T export --run $RUN --stage ${stage} --handoff $H-${stage}   -> report "questions" and the batch ids (the folder names in $H-${stage}). If "questions": 0, batches=[].`, `export:${stage}`)
  log_.push({ stage, ex })
  if (!ex || !ex.ok) return log_
  if (ex.questions === 0 || ex.batches.length === 0) continue
  await parallel(ex.batches.map((b) => () => answer(stage, `${H}-${stage}`, b, false)))
  const im = await op(`Steps: (1) $PY $OH validate --dir $H-${stage}   -> must show 0 missing/stale/malformed/orphans; (2) $PY $T import --run $RUN --stage ${stage}   -> report the mechanical failures or verdicts; (3) $PY $T status --run $RUN   -> report who is due where. batches=[] questions=0.`, `import:${stage}`)
  log_.push({ stage, im })
  if (!im || !im.ok) return log_
}
const out = await op('Steps: (1) $PY $T outcomes --run $RUN   -> report accepted / cleared counts; (2) $PY $T judge-export --run $RUN --handoff $H-judge   -> report the judge batch ids (folder names in $H-judge) and the number of cards.', 'outcomes')
log_.push({ step: 'outcomes', out })
if (!out || !out.ok || out.batches.length === 0) return log_
await parallel(out.batches.map((b) => () => answer('judge', `${H}-judge`, b, true)))
const gate = await op('Steps: (1) $PY $OH validate --dir $H-judge ; (2) $PY $T judge-import --run $RUN   -> report its exit code (0 = PASS), the summary line and the counts of claims SUPPORTED / CONTRADICTED / UNVERIFIABLE / unproven; then read $RUN/JUDGE.md and copy its section "Every contradiction" (verbatim, all lines) and the first 20 lines of $RUN/OUTCOMES.md into summary. ok=true only if judge-import exited 0.', 'judge-gate')
log_.push({ step: 'judge-gate', gate })
return log_
