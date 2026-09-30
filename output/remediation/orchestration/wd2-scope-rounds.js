export const meta = {
  name: 'wd2-scope-rounds',
  description: 'Lane WD2 scope review: rounds 0..N (export, one fresh Opus agent per batch, import) until a round asks nothing, shared agent pool',
  phases: [
    { title: 'Operate', detail: 'export, validate, import per round' },
    { title: 'Answer', detail: 'fresh Opus agents, one per batch' },
  ],
}
const MAIN = 'C:/PythonProjects/AncientMap'
const PY = `${MAIN}/.venv/Scripts/python.exe`
const { width, maxRound, handoffBase } = args
const PRE = `cd ${MAIN} && export PYTHONIOENCODING=utf-8 && PY=${PY} && SR=scripts/remediation/mechanical/scope_review.py && OH=scripts/remediation/opus_handoff.py`
const ST = { type: 'object', properties: { ok: { type: 'boolean' }, asks_nothing: { type: 'boolean' }, batches: { type: 'array', items: { type: 'string' } }, summary: { type: 'string' } }, required: ['ok', 'asks_nothing', 'batches', 'summary'] }
const OPS = { type: 'object', properties: { ok: { type: 'boolean' }, summary: { type: 'string' } }, required: ['ok', 'summary'] }
const opText = (t) => `You are an operator of lane WD2 (E3 scope review) of the AncientMap remediation. You run commands exactly and report; you answer no model question and edit no file. Every command is one bash call starting with this prefix:\n  ${PRE}\nRead each tool's own output (JSON, exit code), never only a wrapper's status. Runbook: docs/procedures/WD2_SERVED_IMAGE_AND_SCOPE.md section 2.1.\n\n${t}\n\nOn a refusal or non-zero exit you cannot resolve as described: ok=false and the last 30 lines in summary.`
let active = 0
const waiting = []
const acquire = () => new Promise((resolve) => { if (active < width) { active++; resolve() } else waiting.push(resolve) })
const release = () => { const n = waiting.shift(); if (n) n(); else active-- }
const answer = async (round, ho, b) => {
  await acquire()
  try {
    return await agent(`You are a fresh Opus research agent of lane WD2 (E3 scope review: is this entry an archaeological site?) of the AncientMap remediation, round ${round}, batch ${b}. You answered no other batch. Work in ${MAIN} (cd there). Run and read completely - it is your full instruction:\n  cd ${MAIN} && PYTHONIOENCODING=utf-8 ${PY} scripts/remediation/mechanical/scope_review.py brief --round ${round} --batch-id ${b}\nFollow it exactly: research on the web yourself, quote verbatim from at least two independent websites when you answer not_a_site (a site answer carries no quotes), check every answer with scope_review.py check-answer until it passes, then record it with opus_handoff.py answer as the brief says (write-once; SKIP every label already recorded). Scratch files only in ${ho}-scratch/${b}/. Modify no other file. No personal data in any web request; User-Agent 'AncientMapRemediation/1.0 (research; https://ancientnerds.com)'. If WebSearch is exhausted, search via curl (Wikipedia/Wikidata APIs, https://html.duckduckgo.com/html/?q=..., Nominatim).\nFinal answer (one line): "${b}: N recorded, M skipped, K failed (reasons)".`, { label: `scope:r${round}:${b}`, phase: 'Answer' })
  } finally { release() }
}
const out = { rounds: [] }
for (let n = 0; n <= maxRound; n++) {
  const ho = `${handoffBase}-r${n}`
  const st = await agent(opText(`State of scope round ${n}:
- If the directory ${ho} exists: $PY $OH validate --dir ${ho}; batches = the distinct batch_id values of its "missing" list (empty when all answered); malformed or stale answers: ok=false. asks_nothing=false.
- Else: first (only if n = 0, or the export directory is older than the previous round's import - simply always) $PY $SR export ; then $PY $SR export-round --round ${n} --handoff ${ho}. If it refuses with "round ${n} asks nothing": ok=true, asks_nothing=true, batches=[]. Otherwise batches = the folders of ${ho} that contain a MANIFEST.jsonl (their names are the batch ids).`), { label: `state:r${n}`, phase: 'Operate', schema: ST })
  if (!st || !st.ok) { out.rounds.push({ round: n, st }); return out }
  if (st.asks_nothing) { out.rounds.push({ round: n, note: 'asks nothing' }); break }
  if (st.batches.length > 0) await parallel(st.batches.map((b) => () => answer(n, ho, b)))
  const im = await agent(opText(`Steps: (1) $PY $OH validate --dir ${ho} -> must be clean (0 missing/stale/malformed/orphans); (2) $PY $SR import-round --round ${n} -> report its summary: counted not_a_site, uncounted, site answers; if it stops on answers out of shape, list them all (ok=false).`), { label: `import:r${n}`, phase: 'Operate', schema: OPS })
  out.rounds.push({ round: n, im: im && im.summary })
  if (!im || !im.ok) return out
}
return out
