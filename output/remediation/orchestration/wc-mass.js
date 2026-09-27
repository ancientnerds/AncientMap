export const meta = {
  name: 'wc-mass',
  description: 'Lane WC mass run in chunks of 500: sequential read+export (each after the earlier chunks), then per chunk the check, one re-ask, the verification rounds and the build, sharing one agent pool',
  phases: [
    { title: 'Export', detail: 'read + export per chunk, sequential' },
    { title: 'Operate', detail: 'imports, verify exports, build' },
    { title: 'Answer', detail: 'fresh Opus agents under a shared pool' },
  ],
}
const MAIN = 'C:/PythonProjects/AncientMap'
const PY = `${MAIN}/.venv/Scripts/python.exe`
const { prefix, chunks, limit, firstBatchBase, width } = args
const RUNS = 'output/remediation/wc_runner/runs'
const PRE = `cd ${MAIN} && export PYTHONIOENCODING=utf-8 && PY=${PY} && M=output/remediation && mkdir -p $M/wc_runner/runs $M/logs/p4wc && C="$PY scripts/remediation/wc/cli.py" && OH="$PY scripts/remediation/opus_handoff.py"`
const OPS = { type: 'object', properties: { ok: { type: 'boolean' }, batches: { type: 'array', items: { type: 'string' } }, count: { type: 'integer' }, summary: { type: 'string' } }, required: ['ok', 'batches', 'count', 'summary'] }
const op = (text, label, ph) => agent(`You are an operator of lane WC (sentence check) of the AncientMap remediation. You run commands exactly and report; you answer no model question and edit no file. Every command is one bash call starting with this prefix:\n  ${PRE}\nRead each tool's own output (JSON, WC_EXIT=), never only a wrapper's status. Runbook: docs/procedures/SENTENCE_CHECK.md section 4.\n\n${text}\n\nOn a refusal or non-zero exit: ok=false and the last 30 lines in summary.`, { label, phase: ph || 'Operate', schema: OPS })
let active = 0
const waiting = []
const acquire = () => new Promise((resolve) => { if (active < width) { active++; resolve() } else waiting.push(resolve) })
const release = () => { const n = waiting.shift(); if (n) n(); else active-- }
const answer = async (run, handoff, b, briefCmd) => {
  await acquire()
  try {
    return await agent(`You are a fresh Opus research agent of lane WC (sentence check of old AI-written site descriptions) of the AncientMap remediation, run ${run}, batch ${b} (${briefCmd}). You worked on no other batch and checked or verified no site of this run before. Work in ${MAIN} (cd there). Run and read completely - it is your full instruction:\n  cd ${MAIN} && PYTHONIOENCODING=utf-8 ${PY} scripts/remediation/wc/cli.py ${briefCmd} --run-dir ${RUNS}/${run} --handoff ${handoff} --batch-id ${b}\nFollow it exactly: research on the web yourself, quote verbatim from the pages you cite (reputable, independent sources; never ancientnerds.com, AI content farms or mirrors of the site's own text), check each answer with the brief's check command before recording it through opus_handoff.py answer as the brief says (write-once; skip labels already recorded). Scratch files only in ${handoff}-scratch/${b}/. Modify no other file. No personal data in any web request; User-Agent 'AncientMapRemediation/1.0 (research; https://ancientnerds.com)'. If WebSearch is exhausted, search via curl (Wikipedia/Wikidata APIs, https://html.duckduckgo.com/html/?q=...).\nFinal answer (one line): "${b}: N recorded, M skipped, K failed (reasons)".`, { label: `${run}:${briefCmd}:${b}`, phase: 'Answer' })
  } finally { release() }
}
const answerAll = (run, handoff, batches, briefCmd) => parallel(batches.map((b) => () => answer(run, handoff, b, briefCmd)))
phase('Export')
const runs = []
for (let k = 1; k <= chunks; k++) {
  const run = `${prefix}-${String(k).padStart(2, '0')}`
  const after = runs.map((r) => `--after ${RUNS}/${r}`).join(' ')
  const ex = await op(`Steps: (1) $C read --run-dir ${RUNS}/${run} ; (2) $C export --run-dir ${RUNS}/${run} --handoff output/remediation/handoff/wc-${run}-r1 --limit ${limit} ${after}   -> report the batch ids (folders in that handoff holding a MANIFEST.jsonl) in batches and the site count in count. If export refuses with "nothing to ask", ok=true, batches=[] and count=0.`, `export:${run}`, 'Export')
  if (!ex || !ex.ok || ex.count === 0) break
  runs.push({ run, batches: ex.batches, k })
  if (ex.count < limit) break
}
log(`WC chunks: ${runs.map((r) => r.run).join(', ')}`)
const results = await pipeline(runs, async ({ run, batches, k }) => {
  const H = `output/remediation/handoff/wc-${run}`
  const out = { run }
  await answerAll(run, `${H}-r1`, batches, 'brief')
  let im = await op(`Steps: (1) $OH validate --dir ${H}-r1 -> clean; (2) $C import --run-dir ${RUNS}/${run} --handoff ${H}-r1  -> summary; count = to_reask. batches=[].`, `import:${run}`)
  out.import = im && im.summary
  if (!im || !im.ok) return out
  if (im.count > 0) {
    const re = await op(`Step: $C export-reask --run-dir ${RUNS}/${run} --handoff ${H}-r2  -> batch ids in batches, count = questions.`, `reask:${run}`)
    if (!re || !re.ok) { out.reask = re; return out }
    if (re.batches.length > 0) {
      await answerAll(run, `${H}-r2`, re.batches, 'brief')
      im = await op(`Steps: (1) $OH validate --dir ${H}-r2 -> clean; (2) $C import --run-dir ${RUNS}/${run} --handoff ${H}-r2  -> summary. batches=[] count=0.`, `import2:${run}`)
      if (!im || !im.ok) { out.import2 = im; return out }
    }
  }
  const vx = await op(`Step: $C verify-export --run-dir ${RUNS}/${run} --handoff ${H}-verify  -> batch ids in batches, count = questions.`, `verify-export:${run}`)
  if (!vx || !vx.ok) { out.vx = vx; return out }
  if (vx.batches.length > 0) {
    await answerAll(run, `${H}-verify`, vx.batches, 'verify-brief')
    const vi = await op(`Steps: (1) $OH validate --dir ${H}-verify -> clean; (2) $C verify-import --run-dir ${RUNS}/${run} --handoff ${H}-verify  -> summary; count = to_verify2. batches=[].`, `verify-import:${run}`)
    out.verify = vi && vi.summary
    if (!vi || !vi.ok) return out
    if (vi.count > 0) {
      const v2 = await op(`Step: $C verify-export --run-dir ${RUNS}/${run} --handoff ${H}-verify2  -> batch ids in batches, count = questions.`, `verify2-export:${run}`)
      if (!v2 || !v2.ok) { out.v2 = v2; return out }
      if (v2.batches.length > 0) {
        await answerAll(run, `${H}-verify2`, v2.batches, 'verify-brief')
        const v2i = await op(`Steps: (1) $OH validate --dir ${H}-verify2 -> clean; (2) $C verify-import --run-dir ${RUNS}/${run} --handoff ${H}-verify2  -> summary. batches=[] count=0.`, `verify2-import:${run}`)
        out.verify2 = v2i && v2i.summary
        if (!v2i || !v2i.ok) return out
      }
    }
  }
  const bd = await op(`Step: $C build --run-dir ${RUNS}/${run} --first-batch ${firstBatchBase + 100 * k}  -> report the SUMMARY counts and the WC4.jsonl batch range and sha256. batches=[] count=0.`, `build:${run}`)
  out.build = bd && bd.summary
  out.built = !!(bd && bd.ok)
  return out
})
return { runs: runs.map((r) => r.run), results }
