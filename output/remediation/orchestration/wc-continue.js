export const meta = {
  name: 'wc-continue',
  description: 'Lane WC: continue every exported chunk from whatever state its files show (answer missing labels, import, re-ask, verify, verify2, build); Sonnet 5.5 agents, shared pool',
  phases: [
    { title: 'Operate', detail: 'state + one command per step, per chunk' },
    { title: 'Answer', detail: 'fresh Sonnet 5.5 agents, one per batch, shared pool' },
  ],
}
// Owner decision 2026-10-01: the orchestrating session runs Opus 5.5, every agent here runs Sonnet 5.5
// (model set explicitly - never inherited) and records its answers with --model claude-sonnet-5-5.
const MAIN = 'C:/PythonProjects/AncientMap'
const PY = `${MAIN}/.venv/Scripts/python.exe`
const { runs, firstBatchBase, width } = args
const RUNS = 'output/remediation/wc_runner/runs'
const H = 'output/remediation/handoff'
const PRE = `cd ${MAIN} && export PYTHONIOENCODING=utf-8 && PY=${PY} && M=output/remediation && mkdir -p $M/wc_runner/runs $M/logs/p4wc && C="$PY scripts/remediation/wc/cli.py" && OH="$PY scripts/remediation/opus_handoff.py"`
const STEP = { type: 'object', properties: { ok: { type: 'boolean' }, done: { type: 'boolean' }, ran: { type: 'string', description: 'the command run in this step, or empty' }, answer: { type: 'object', properties: { handoff: { type: 'string' }, brief: { type: 'string', enum: ['brief', 'verify-brief'] }, batches: { type: 'array', items: { type: 'string' } } }, required: ['handoff', 'brief', 'batches'] }, state: { type: 'string', description: 'one line: where the chunk stands after this step' }, summary: { type: 'string' } }, required: ['ok', 'done', 'ran', 'state', 'summary'] }
const SONNET = { model: 'sonnet' }

const stepPrompt = (run, k) => `You are an operator of lane WC (sentence check) of the AncientMap remediation. You run commands exactly and report; you answer no model question and edit no file. Every command is one bash call starting with this prefix:
  ${PRE}
Read each tool's own output (JSON, WC_EXIT=), never only a wrapper's status. Runbook: docs/procedures/SENTENCE_CHECK.md sections 3 and 4 (read them if a rule below is unclear).

Chunk run: R=${RUNS}/${run}, handoffs ${H}/wc-${run}-r1, -r2, -verify, -verify2. Determine the FIRST unfinished stage from the files, in this order, and do exactly ONE thing for it, then return:
1. If R/WC4.jsonl exists: done=true (built), ran="".
2. Check round 1: if R/round-1/ANSWERS.jsonl does not exist: ${H}/wc-${run}-r1 must exist (if not: ok=false). Run $OH validate --dir ${H}/wc-${run}-r1. If questions are missing: return answer={handoff: that dir, brief:"brief", batches: the distinct batch_id values of "missing"}, ran="validate". If malformed/stale/orphans: ok=false. If clean: run $C import --run-dir R --handoff ${H}/wc-${run}-r1 and return (ran = the import; summary = its counts incl. to_reask).
3. Re-ask (round 2, once): read R/round-1/REASK.json. If it asks nothing (no sentence to re-ask), skip to 4. Else if R/round-2/ANSWERS.jsonl exists, skip to 4. Else if ${H}/wc-${run}-r2 does not exist: run $C export-reask --run-dir R --handoff ${H}/wc-${run}-r2 and return. Else validate it: missing -> answer={handoff, brief:"brief", batches}; clean -> $C import --run-dir R --handoff ${H}/wc-${run}-r2 and return.
4. Verification round 1: if R/verify/round-1/ROUND.json does not exist: run $C verify-export --run-dir R --handoff ${H}/wc-${run}-verify and return (if it refuses with "nothing to verify", go to 6 in this same step). Else, if round 1 is not yet imported (R/VERIFIED.jsonl does not exist or holds no round-1 record - inspect its lines): validate ${H}/wc-${run}-verify: missing -> answer={handoff, brief:"verify-brief", batches}; clean -> $C verify-import --run-dir R --handoff ${H}/wc-${run}-verify and return (summary incl. to_verify2).
5. Verification round 2 (once, only for texts a drop changed): if R/verify/round-2/ROUND.json does not exist: run $C verify-export --run-dir R --handoff ${H}/wc-${run}-verify2 and return; if it refuses with "nothing to verify", go to 6 in this same step. Else if round 2 is not imported (inspect R/VERIFIED.jsonl): validate ${H}/wc-${run}-verify2: missing -> answer={handoff, brief:"verify-brief", batches}; clean -> $C verify-import --run-dir R --handoff ${H}/wc-${run}-verify2 and return.
6. Build: $C build --run-dir R --first-batch ${firstBatchBase + 100 * k} -> summary = the SUMMARY counts, the WC4.jsonl batch range and sha256; done=true.
A command that refuses or exits non-zero for a reason these rules do not cover: ok=false, the last 30 lines in summary. A verify-import that lists transient fetch failures: run it once more before you return.`

let active = 0
const waiting = []
const acquire = () => new Promise((resolve) => { if (active < width) { active++; resolve() } else waiting.push(resolve) })
const release = () => { const n = waiting.shift(); if (n) n(); else active-- }
const answer = async (run, handoff, b, briefCmd) => {
  await acquire()
  try {
    return await agent(`You are a fresh research agent (Claude Sonnet 5.5) of lane WC (sentence check of old AI-written site descriptions) of the AncientMap remediation, run ${run}, batch ${b} (${briefCmd}). You worked on no other batch and checked or verified no site of this run before. Work in ${MAIN} (cd there). Run and read completely - it is your full instruction:
  cd ${MAIN} && PYTHONIOENCODING=utf-8 ${PY} scripts/remediation/wc/cli.py ${briefCmd} --run-dir ${RUNS}/${run} --handoff ${handoff} --batch-id ${b}
Follow it exactly (where it says "Opus agent", that is you): research on the web yourself, quote verbatim from the pages you cite (reputable, independent sources; never ancientnerds.com, AI content farms or mirrors of the site's own text), check each answer with the brief's check command before recording it through opus_handoff.py answer as the brief says, with --model claude-sonnet-5-5 (the model you run as; write-once; skip labels already recorded). Scratch files only in ${handoff}-scratch/${b}/. Modify no other file. No personal data in any web request; User-Agent 'AncientMapRemediation/1.0 (research; https://ancientnerds.com)'. If WebSearch is exhausted, search via curl (Wikipedia/Wikidata APIs, https://html.duckduckgo.com/html/?q=...).
Final answer (one line): "${b}: N recorded, M skipped, K failed (reasons)".`, { label: `${run}:${briefCmd}:${b}`, phase: 'Answer', ...SONNET, effort: 'high' })
  } finally { release() }
}

const results = await pipeline(runs, async (run, _item, idx) => {
  const k = Number(run.slice(-2))
  const out = { run, steps: [] }
  let last = ''
  let same = 0
  for (let guard = 0; guard < 16; guard++) {
    const st = await agent(stepPrompt(run, k), { label: `step:${run}:${guard}`, phase: 'Operate', schema: STEP, ...SONNET, effort: 'medium' })
    out.steps.push(st && { ran: st.ran, state: st.state, ok: st.ok })
    if (!st || !st.ok) { out.stopped = st ? st.summary : 'operator failed'; return out }
    if (st.done) { out.built = st.summary; return out }
    if (st.answer && st.answer.batches.length > 0) {
      await parallel(st.answer.batches.map((b) => () => answer(run, st.answer.handoff, b, st.answer.brief)))
    }
    const key = `${st.ran}|${st.state}|${st.answer ? st.answer.batches.join(',') : ''}`
    same = key === last ? same + 1 : 0
    last = key
    if (same >= 2) { out.stopped = `no progress after three identical steps: ${st.state}`; return out }
  }
  out.stopped = 'step guard reached'
  return out
})
return results
