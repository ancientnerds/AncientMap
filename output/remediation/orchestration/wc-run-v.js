export const meta = {
  name: 'wc-run-v',
  description: 'Lane WC sentence check: read, export, one Opus agent per batch, validate, import, one re-ask round, build; for a pilot also the independent judge and its gate',
  phases: [
    { title: 'Operate', detail: 'read, export, import, build, judge import' },
    { title: 'Answer', detail: 'one fresh Opus agent per batch' },
    { title: 'Judge', detail: 'independent judges (pilot only)' },
  ],
}
const MAIN = 'C:/PythonProjects/AncientMap'
const PY = `${MAIN}/.venv/Scripts/python.exe`
const { run, exportArgs, firstBatch, pilot, width } = args
const RUNDIR = `output/remediation/wc_runner/runs/${run}`
const HB = `output/remediation/handoff/wc-${run}`
const PRE = `cd ${MAIN} && export PYTHONIOENCODING=utf-8 && PY=${PY} && M=output/remediation && mkdir -p $M/wc_runner/runs $M/logs/p4wc && C="$PY scripts/remediation/wc/cli.py" && OH="$PY scripts/remediation/opus_handoff.py"`
const OPS = { type: 'object', properties: { ok: { type: 'boolean' }, batches: { type: 'array', items: { type: 'string' } }, to_reask: { type: 'integer' }, summary: { type: 'string' } }, required: ['ok', 'batches', 'to_reask', 'summary'] }
const op = (text, label) => agent(`You are the operator of lane WC (sentence check) of the AncientMap remediation. You run commands exactly and report; you answer no model question and edit no file. Every command is one bash call starting with this prefix:\n  ${PRE}\nRead each tool's own output (JSON, exit lines such as JUDGE_EXIT=), never only a wrapper's status. Runbook: docs/procedures/SENTENCE_CHECK.md section 4 - read it once.\n\n${text}\n\nOn any refusal or non-zero exit (except the judge's JUDGE_EXIT=1, which you report): ok=false and the last 30 lines of that output in summary.`, { label, phase: 'Operate', schema: OPS })
const answer = (handoff, b, briefCmd) => agent(`You are a fresh Opus research agent of lane WC (sentence check of old AI-written site descriptions) of the AncientMap remediation, batch ${b} (${briefCmd}). You worked on no other batch and checked or verified no site of this run before. Work in ${MAIN} (cd there). Run and read completely - it is your full instruction:\n  cd ${MAIN} && PYTHONIOENCODING=utf-8 ${PY} scripts/remediation/wc/cli.py ${briefCmd} --run-dir ${RUNDIR} --handoff ${handoff} --batch-id ${b}\nFollow it exactly, sentence by sentence: research on the web yourself, quote verbatim from the pages you cite (reputable, independent sources; never ancientnerds.com, never AI content farms or mirrors of the site's own text), check each answer with the brief's check command before recording it through opus_handoff.py answer as the brief says (write-once; skip labels already recorded). Scratch files only in ${handoff}-scratch/${b}/. Modify no other file. No personal data in any web request; User-Agent 'AncientMapRemediation/1.0 (research; https://ancientnerds.com)'. If WebSearch is exhausted, search via curl (Wikipedia/Wikidata APIs, https://html.duckduckgo.com/html/?q=...).\nFinal answer (one line): "${b}: N recorded, M skipped, K failed (reasons)".`, { label: `${briefCmd}:${b}`, phase: briefCmd === 'judge-brief' ? 'Judge' : 'Answer' })
const pool = async (handoff, batches, briefCmd) => {
  let next = 0
  const worker = async () => { while (next < batches.length) { const b = batches[next++]; await answer(handoff, b, briefCmd) } }
  await parallel(Array.from({ length: Math.min(width, batches.length) }, () => worker))
}
const log_ = []
const ex = await op(`Steps: (1) $C read --run-dir ${RUNDIR} ; (2) $C export --run-dir ${RUNDIR} --handoff ${HB}-r1 ${exportArgs}   -> report the batch ids (folders in ${HB}-r1 holding a MANIFEST.jsonl) and the site/question counts. to_reask=0.`, 'read+export')
log_.push({ ex })
if (!ex || !ex.ok || ex.batches.length === 0) return log_
await pool(`${HB}-r1`, ex.batches, 'brief')
let im = await op(`Steps: (1) $OH validate --dir ${HB}-r1 -> must be clean; (2) $C import --run-dir ${RUNDIR} --handoff ${HB}-r1   -> report its summary and to_reask. batches=[].`, 'import:r1')
log_.push({ im })
if (!im || !im.ok) return log_
if (im.to_reask > 0) {
  const re = await op(`Step: $C export-reask --run-dir ${RUNDIR} --handoff ${HB}-r2   -> report the batch ids (folders in ${HB}-r2 with a MANIFEST.jsonl). to_reask=0.`, 'export:r2')
  log_.push({ re })
  if (!re || !re.ok) return log_
  if (re.batches.length > 0) {
    await pool(`${HB}-r2`, re.batches, 'brief')
    im = await op(`Steps: (1) $OH validate --dir ${HB}-r2 -> clean; (2) $C import --run-dir ${RUNDIR} --handoff ${HB}-r2   -> report its summary. batches=[] to_reask=0.`, 'import:r2')
    log_.push({ im })
    if (!im || !im.ok) return log_
  }
}
const vex = await op(`Step: $C verify-export --run-dir ${RUNDIR} --handoff ${HB}-verify   -> report the batch ids (folders in ${HB}-verify with a MANIFEST.jsonl). to_reask=0.`, 'verify-export')
log_.push({ vex })
if (!vex || !vex.ok) return log_
if (vex.batches.length > 0) {
  await pool(`${HB}-verify`, vex.batches, 'verify-brief')
  const vim = await op(`Steps: (1) $OH validate --dir ${HB}-verify -> clean; (2) $C verify-import --run-dir ${RUNDIR} --handoff ${HB}-verify   -> report its summary and to_verify2 (put the to_verify2 number into to_reask). batches=[].`, 'verify-import')
  log_.push({ vim })
  if (!vim || !vim.ok) return log_
  if (vim.to_reask > 0) {
    const v2 = await op(`Step: $C verify-export --run-dir ${RUNDIR} --handoff ${HB}-verify2   -> report the batch ids (folders in ${HB}-verify2 with a MANIFEST.jsonl). to_reask=0.`, 'verify2-export')
    log_.push({ v2 })
    if (!v2 || !v2.ok) return log_
    if (v2.batches.length > 0) {
      await pool(`${HB}-verify2`, v2.batches, 'verify-brief')
      const v2im = await op(`Steps: (1) $OH validate --dir ${HB}-verify2 -> clean; (2) $C verify-import --run-dir ${RUNDIR} --handoff ${HB}-verify2   -> report its summary. batches=[] to_reask=0.`, 'verify2-import')
      log_.push({ v2im })
      if (!v2im || !v2im.ok) return log_
    }
  }
}
const bd = await op(`Step: $C build --run-dir ${RUNDIR} --first-batch ${firstBatch}   -> report FINAL/SUMMARY counts (kept / trimmed / dropped sentences, sites kept / cleared) and the WC4.jsonl batch range. batches=[] to_reask=0.`, 'build')
log_.push({ bd })
if (!bd || !bd.ok || !pilot) return log_
const je = await op(`Step: $C judge-export --run-dir ${RUNDIR} --handoff ${HB}-judge   -> report the judge batch ids (folders in ${HB}-judge with a MANIFEST.jsonl). to_reask=0.`, 'judge-export')
log_.push({ je })
if (!je || !je.ok || je.batches.length === 0) return log_
await pool(`${HB}-judge`, je.batches, 'judge-brief')
const jg = await op(`Steps: (1) $OH validate --dir ${HB}-judge -> clean; (2) $C judge-import --run-dir ${RUNDIR} --handoff ${HB}-judge   -> report JUDGE_EXIT (0 pass, 1 stop), and copy ${RUNDIR}/judge/RESULT.json (or where it says) into summary. ok=true if the commands ran.`, 'judge-import')
log_.push({ jg })
return log_
