export const meta = {
  name: 'theo-claim-check',
  description: 'Answer claims_check/pending.jsonl of a paper workspace: live read of TDM-reserved sources, one verifier per task, an adversarial skeptic for every supported verdict; appends claims_check/verdicts.jsonl',
  whenToUse: 'theo-write, after ./.venv/Scripts/python.exe -m pipeline.studio paper claims-export <id> and before paper claims-import <id>. args: {"workspace": "<absolute path of STUDIO_ASSETS/papers/<request_id>>"}',
  phases: [
    { title: 'Inventory', detail: 'pending.jsonl minus the tasks verdicts.jsonl already holds' },
    { title: 'Live read', detail: 'each TDM-reserved source once, into claims_check/live/<id>.txt' },
    { title: 'Verify', detail: 'one verifier per task' },
    { title: 'Skeptic', detail: 'one adversarial skeptic per supported verdict' },
    { title: 'Write', detail: 'append the answers to claims_check/verdicts.jsonl' },
  ],
}

/*
 * The claim check of spec 3.5 and plan C's contract C2, answered by Opus agents.
 *
 * Input: the handoff directory <workspace>/claims_check/ that `paper claims-export` wrote
 * (pipeline/studio/paper/claims.py, pipeline/studio/handoff.py). Output: one line per answered
 * task appended to claims_check/verdicts.jsonl:
 *   {task_id, prompt_sha256, verdict: supported|partly|unsupported|source_missing, quote,
 *    quote_source_id, explanation, fix_suggestion, answered_by, skeptic_by}
 * `paper claims-import` then validates the file (shape, prompt hashes, the verbatim quote, the
 * skeptic, the live texts) and refuses it whole on any problem.
 *
 * - Tasks that already have a line in verdicts.jsonl are not answered again. A file that
 *   claims-import refused stays in place: delete its bad lines, then run this workflow again.
 * - TDM-reserved sources (text_status tdm_reserved, text_path null; owner decision 16) are
 *   read live once each, before any verifier runs, with the archive's own reader
 *   (pipeline.lyra.archive_completion.fetch_document), into claims_check/live/<id>.txt:
 *   "URL: <url>", "Fetched: <ISO-8601 UTC>", an empty line, the text. An existing live file is
 *   kept (earlier answers and evidence quotes were checked against it); delete it by hand to
 *   read the page again. A failed live read leaves source_missing as the only verdict for
 *   every task that cites the source (spec 3.5: the page is unreachable).
 * - Every `supported` verdict, the coherence task's included, goes to an adversarial skeptic.
 *   If the skeptic confirms it, skeptic_by names the skeptic; if it refutes it, the skeptic's
 *   verdict is written and skeptic_by stays "".
 * - Only Opus judges (owner rule): an agent that reports another model ID gets no answer
 *   written; its task stays pending and is listed in the result.
 * - prompt_sha256 is copied by the append command from the pending.jsonl row of the same
 *   task_id: the verifier read prompts/<task_id>.txt, and a task id is derived from its
 *   prompt's hash, so a changed prompt is a different task.
 */

const PY = './.venv/Scripts/python.exe'
const STUDIO = `${PY} -m pipeline.studio`
const PART = 'verdicts.part.jsonl'
const LINES_PER_WRITE = 20
const VERDICTS = ['supported', 'partly', 'unsupported', 'source_missing']
const OPUS_RE = /^claude-opus-/

if (!args || typeof args.workspace !== 'string' || !args.workspace.trim()) {
  throw new Error('args.workspace must be the absolute path of the paper workspace <STUDIO_ASSETS>/papers/<request_id>')
}
const WS = args.workspace.trim().replace(/\\/g, '/').replace(/\/+$/, '')
const DIR = `${WS}/claims_check`
const REQUEST_ID = WS.split('/').pop()

const INVENTORY_CMD = `${PY} -c "
import json, pathlib, sys
from pipeline.studio import handoff
from pipeline.studio.paper import claims
from pipeline.studio.paper.workspace import PaperWorkspace
root = pathlib.Path(sys.argv[1])
d = PaperWorkspace(root, root.name).claims_dir
v = d / handoff.VERDICTS_FILE
done = {r.get('task_id') for r in handoff.read_jsonl(v)} if v.exists() else set()
rows = [r for r in handoff.read_jsonl(d / handoff.PENDING_FILE) if r['task_id'] not in done]
def tdm(r):
    return [c['source_id'] for c in r['cited'] if c['text_status'] == 'tdm_reserved' and c['text_path'] is None]
ids = sorted({s for r in rows for s in tdm(r)})
tasks = [{'task_id': r['task_id'], 'kind': r['kind'], 'ref': r['ref'], 'cited': [c['source_id'] for c in r['cited']], 'tdm': tdm(r)} for r in rows]
live = [{'source_id': s, 'live_saved': (d / claims.LIVE_DIR / (s + '.txt')).exists()} for s in ids]
print(json.dumps({'in_verdicts_file': len(done), 'tasks': tasks, 'tdm_sources': live}, indent=1))
" "${WS}"`

const liveCmd = (sid) => `${PY} -c "
import asyncio, datetime, json, pathlib, sys
from pipeline.lyra.archive_completion import _client, fetch_document
from pipeline.studio import handoff
from pipeline.studio.paper import claims
from pipeline.studio.paper.workspace import PaperWorkspace
root, sid = pathlib.Path(sys.argv[1]), sys.argv[2]
ws = PaperWorkspace(root, root.name)
url = next(c['url'] for r in handoff.read_jsonl(ws.claims_dir / handoff.TASKS_FILE) for c in r['cited'] if c['source_id'] == sid and c['text_status'] == 'tdm_reserved')
async def read():
    async with _client() as client:
        return await fetch_document(client, url)
doc = asyncio.run(read())
at = datetime.datetime.now(datetime.UTC).isoformat(timespec='seconds')
out = ws.root / claims.live_rel(ws, sid)
out.parent.mkdir(parents=True, exist_ok=True)
with out.open('x', encoding='utf-8', newline='') as f:
    f.write('URL: ' + url + chr(10) + 'Fetched: ' + at + chr(10) + chr(10) + doc.text + chr(10))
text = claims.live_text(ws, {'id': sid, 'url': url})
print(json.dumps({'source_id': sid, 'url': url, 'final_url': doc.final_url, 'content_type': doc.content_type, 'chars': len(text), 'start': text[:400]}, indent=1))
" "${WS}" "${sid}"`

const APPEND_CMD = `${PY} -c "
import json, pathlib, sys
from pipeline.studio import handoff
d = pathlib.Path(sys.argv[1])
part = d / sys.argv[2]
pending = {r['task_id']: r for r in handoff.read_jsonl(d / handoff.PENDING_FILE)}
v = d / handoff.VERDICTS_FILE
old = v.read_text(encoding='utf-8') if v.exists() else ''
there = {r.get('task_id') for r in handoff.read_jsonl(v)} if old else set()
rows = handoff.read_jsonl(part)
bad = [r.get('task_id') for r in rows if r.get('task_id') not in pending or r.get('task_id') in there]
if bad:
    sys.exit('not pending, or already in verdicts.jsonl: ' + json.dumps(bad))
for r in rows:
    r['prompt_sha256'] = pending[r['task_id']]['prompt_sha256']
lead = chr(10) if old and not old.endswith(chr(10)) else ''
with v.open('a', encoding='utf-8', newline='') as f:
    f.write(lead + ''.join(json.dumps(r, ensure_ascii=False, sort_keys=True) + chr(10) for r in rows))
part.unlink()
print(json.dumps([r['task_id'] for r in rows]))
" "${DIR}" "${PART}"`

const command = (cmd) => `-----BEGIN COMMAND-----\n${cmd}\n-----END COMMAND-----`

const RUN_ONCE = 'Run the command between the markers once, from the repository root (the directory that holds .venv), as one Bash command, exactly as written.'

const LONG_LINES = 'A text file can be one very long line (a web page is flattened to a single line), which the Read tool cuts off: page through it with fold -s -w 1000 "<file>" | sed -n "1,40p" (then 41,80p and so on) and search it with Grep.'

const NO_FORMAT = 'Ignore the answer-format paragraph at the end of the prompt file: answer through the structured output below; the workflow adds task_id, prompt_sha256, answered_by and skeptic_by.'

const MODEL_FIELD = { type: 'string', description: 'The exact model ID your system prompt names, for example claude-opus-5-5' }

const INVENTORY_SCHEMA = {
  type: 'object',
  properties: {
    error: { type: 'string' },
    in_verdicts_file: { type: 'integer', minimum: 0 },
    tasks: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          task_id: { type: 'string' },
          kind: { type: 'string', enum: ['evidence', 'paragraph', 'coherence'] },
          ref: { type: 'string' },
          cited: { type: 'array', items: { type: 'string' } },
          tdm: { type: 'array', items: { type: 'string' } },
        },
        required: ['task_id', 'kind', 'ref', 'cited', 'tdm'],
      },
    },
    tdm_sources: {
      type: 'array',
      items: {
        type: 'object',
        properties: { source_id: { type: 'string' }, live_saved: { type: 'boolean' } },
        required: ['source_id', 'live_saved'],
      },
    },
  },
  required: ['error', 'in_verdicts_file', 'tasks', 'tdm_sources'],
}

const LIVE_SCHEMA = {
  type: 'object',
  properties: {
    saved: { type: 'boolean' },
    chars: { type: 'integer', minimum: 0 },
    detail: { type: 'string' },
  },
  required: ['saved', 'chars', 'detail'],
}

const WRITE_SCHEMA = {
  type: 'object',
  properties: {
    appended: { type: 'array', items: { type: 'string' } },
    error: { type: 'string' },
  },
  required: ['appended', 'error'],
}

function verifierSchema(t, unread) {
  const coherence = t.kind === 'coherence'
  const verdicts = unread.length ? ['source_missing'] : coherence ? ['supported', 'unsupported'] : VERDICTS
  return {
    type: 'object',
    properties: {
      verdict: { type: 'string', enum: verdicts },
      quote: { type: 'string' },
      quote_source_id: { type: 'string', enum: coherence ? [''] : [...new Set(['', ...t.cited])] },
      explanation: { type: 'string' },
      fix_suggestion: { type: 'string' },
      model: MODEL_FIELD,
    },
    required: ['verdict', 'quote', 'quote_source_id', 'explanation', 'fix_suggestion', 'model'],
  }
}

function skepticSchema(t) {
  return {
    type: 'object',
    properties: {
      verdict: { type: 'string', enum: t.kind === 'coherence' ? ['supported', 'unsupported'] : VERDICTS },
      explanation: { type: 'string' },
      fix_suggestion: { type: 'string' },
      model: MODEL_FIELD,
    },
    required: ['verdict', 'explanation', 'fix_suggestion', 'model'],
  }
}

function taskHead(t) {
  return [
    `Paper workspace: ${WS}`,
    `Task: ${t.task_id} (kind ${t.kind}, ref ${t.ref})`,
    `Prompt file: ${DIR}/prompts/${t.task_id}.txt`,
  ].join('\n')
}

// `saved` are the TDM-reserved sources of the task whose live text is in live/<id>.txt. A source
// whose live read failed is not one of them: its failure is the verifier's `unread` note.
function liveNote(saved) {
  if (!saved.length) return ''
  return `The prompt asks you to read TDM-reserved sources live and save their text. This workflow has done that already: the page text of ${saved.join(', ')} is saved in ${DIR}/live/<source_id>.txt (lines 1-3 are the header "URL: ...", "Fetched: ..." and an empty line; the text starts on line 4). Read that file as the source's text and quote from it. Do not fetch the page again.`
}

function verifierPrompt(t, unread) {
  const coherence = t.kind === 'coherence'
  const parts = [
    'You are the verifier of one claim-check task of a Theo paper (Ancient Nerds). Your answer is checked by machine on import (a quote must occur verbatim in the text of the source it names), and if you judge the claim supported, an adversarial skeptic tries to refute it.',
    taskHead(t),
    '1. Read the prompt file in full. It is the exact question and its rules bind you. Its task JSON holds the paragraph, the claim and the cited sources; cited[].n is the number that source\'s marker [n] shows in the paragraph.',
    coherence
      ? '2. Kind coherence: judge the list of measurements in "claim". There are no source files; quote and quote_source_id are "".'
      : `2. Read the text of every cited source in full: ${WS}/<text_path> for each cited[].text_path. ${LONG_LINES}`,
    liveNote(t.tdm.filter((sid) => !unread.some((u) => u.sid === sid))),
    unread.length
      ? `The live read of ${unread.map((u) => `${u.sid} failed (${u.read.detail})`).join('; ')}. The only verdict you may give is therefore source_missing: say in explanation which statements rest on that source, and in fix_suggestion which other cited source could carry them, or that they must go.`
      : '',
    '3. Judge only from these files: no web search, no outside knowledge. Do not create, edit or delete any file.',
    NO_FORMAT,
    'Answer with: verdict; quote: the sentence that proves the claim, copied character for character from the text of quote_source_id ("" when no quote applies); quote_source_id: the id of that source ("" when none); explanation: what the sources say about the claim; fix_suggestion: how to fix the paper ("" when supported); model.',
  ]
  return parts.filter(Boolean).join('\n\n')
}

function skepticPrompt(t, v) {
  const coherence = t.kind === 'coherence'
  const checks = coherence
    ? [
        '1. No two measurements in the list contradict each other for the same thing: compare every pair that measures the same object or quantity, with units converted.',
      ]
    : [
        `1. The quote occurs verbatim, whitespace aside, in the text of quote_source_id: ${WS}/texts/<id>.txt, or for a TDM-reserved source the saved live text ${DIR}/live/<id>.txt. Search for it with Grep.`,
        '2. The source states the claim. For kind paragraph: every factual statement of the paragraph, every name, date and number, is stated by the source that its own marker [n] names (cited[].n); a statement that only another cited source states is a wrong citation.',
        '3. The paper states nothing more strongly than the source does (certainty, size, date, who said it).',
      ]
  const parts = [
    'You are the adversarial skeptic for one claim-check answer of a Theo paper (Ancient Nerds). A verifier judged the task below supported. That verdict stands only if you try hard to refute it and fail. When you cannot confirm a part, refute it.',
    taskHead(t),
    `The verifier's answer: ${JSON.stringify({ quote: v.quote, quote_source_id: v.quote_source_id, explanation: v.explanation })}`,
    coherence
      ? 'Read the prompt file in full; the list of measurements is its "claim".'
      : `Read the prompt file in full, and the text of every cited source it names: ${WS}/<text_path>. ${LONG_LINES}`,
    // a supported verdict is only possible when every live read of the task was saved
    liveNote(t.tdm),
    'Check:',
    checks.join('\n'),
    'Judge only from these files: no web search, no outside knowledge. Do not create, edit or delete any file.',
    NO_FORMAT,
    'Answer with: verdict: supported when every check holds, otherwise the verdict the prompt file defines for what you found; explanation: what you checked and, when you refute, exactly what fails; fix_suggestion: how to fix the paper ("" when supported); model.',
  ]
  return parts.filter(Boolean).join('\n\n')
}

function writePrompt(lines) {
  return [
    `Append ${lines.length} answer lines to ${DIR}/verdicts.jsonl. Change no other file.`,
    `1. Remove a leftover scratch file: rm -f "${DIR}/${PART}"`,
    `2. Create ${DIR}/${PART} with the Write tool. Its content is exactly the lines between BEGIN LINES and END LINES below, character for character, one JSON object per line, each line ending in a newline, nothing before or after them.`,
    `3. ${RUN_ONCE} It checks every line against pending.jsonl (the task is pending and not yet in verdicts.jsonl), copies each task's prompt_sha256 from pending.jsonl into its line, appends the lines to verdicts.jsonl, deletes the scratch file and prints the appended task ids as a JSON list.`,
    command(APPEND_CMD),
    '4. Answer with appended: the printed task ids, and error: "". If the command fails, answer with appended [] and error: the last line of its error output, and repair nothing by hand.',
    `-----BEGIN LINES-----\n${lines.join('\n')}\n-----END LINES-----`,
  ].join('\n\n')
}

// ---- Inventory ------------------------------------------------------------------------------

phase('Inventory')
const inv = await agent(
  [
    `List the pending claim-check tasks of the paper workspace ${WS}. ${RUN_ONCE} Change no file.`,
    command(INVENTORY_CMD),
    'If the command fails, answer with error: the last line of its error output, in_verdicts_file 0 and empty lists. Otherwise answer with error "" and copy the printed JSON exactly: in_verdicts_file, every task with its task_id, kind, ref, cited and tdm, and every TDM-reserved source with live_saved.',
  ].join('\n\n'),
  { label: 'inventory', phase: 'Inventory', schema: INVENTORY_SCHEMA, effort: 'low' },
)
if (inv === null) throw new Error('the inventory agent did not finish')
if (inv.error) throw new Error(`reading ${DIR}/pending.jsonl failed: ${inv.error} (run \`${STUDIO} paper claims-export ${REQUEST_ID}\` first)`)
if (inv.in_verdicts_file) {
  log(`${inv.in_verdicts_file} tasks already have a line in verdicts.jsonl and are not answered again (run claims-import; if it refused the file, delete the refused lines first)`)
}
log(`${inv.tasks.length} tasks to answer, ${inv.tdm_sources.length} TDM-reserved sources among their citations`)
if (!inv.tasks.length) {
  return { workspace: WS, answered: 0, verdicts: {}, overruled_by_skeptic: 0, live_reads: [], not_answered: [], next: `${STUDIO} paper claims-import ${REQUEST_ID}` }
}

// ---- Live read: every TDM-reserved source once, before the verifiers that cite it ----------

const liveReads = {}
for (const s of inv.tdm_sources) {
  liveReads[s.source_id] = s.live_saved
    ? Promise.resolve({ saved: true, chars: 0, detail: 'kept: an earlier run saved it' })
    : agent(
        [
          `Read one TDM-reserved source of a Theo paper live: ${s.source_id}. The paper cites it like any source; only the automatic archive skips such sources (owner decision 16).`,
          `${RUN_ONCE} It fetches the page with the archive's own reader (pipeline.lyra.archive_completion.fetch_document, HTML or PDF), saves the exact text to ${DIR}/live/${s.source_id}.txt with the header the import checks ("URL: <url>", "Fetched: <UTC time>", an empty line) and prints what it saved.`,
          command(liveCmd(s.source_id)),
          'Do not retry, do not fetch the page any other way, and do not edit the saved file.',
          'Answer with saved: true when the command printed its JSON, false when it failed; chars: the printed chars (0 when it failed); detail: when saved, one sentence on what the text holds, judged from the printed start (an article, an abstract page, a paywall, a cookie or login wall); when it failed, the last line of the error output.',
        ].join('\n\n'),
        { label: `live ${s.source_id}`, phase: 'Live read', schema: LIVE_SCHEMA, effort: 'low' },
      )
}

// ---- Verify, then the skeptic for every supported verdict -----------------------------------

async function verify(t) {
  const lives = []
  for (const sid of t.tdm) lives.push({ sid, read: await liveReads[sid] })
  const lost = lives.filter((l) => l.read == null)
  if (lost.length) return { t, skipped: `no live read result for ${lost.map((l) => l.sid).join(', ')}` }
  const unread = lives.filter((l) => !l.read.saved)
  const v = await agent(verifierPrompt(t, unread), {
    label: `verify ${t.ref}`,
    phase: 'Verify',
    schema: verifierSchema(t, unread),
  })
  if (v === null) return { t, skipped: 'the verifier did not finish' }
  if (!OPUS_RE.test(v.model)) return { t, skipped: `the verifier ran on ${v.model}; only Opus judges (owner rule)` }
  if (v.verdict === 'supported' && t.kind !== 'coherence' && !(v.quote.trim() && v.quote_source_id)) {
    return { t, skipped: 'the verifier judged it supported without a quote and its source' }
  }
  return { t, v }
}

async function challenge(r) {
  if (!r.v || r.v.verdict !== 'supported') return r
  const s = await agent(skepticPrompt(r.t, r.v), {
    label: `skeptic ${r.t.ref}`,
    phase: 'Skeptic',
    schema: skepticSchema(r.t),
  })
  if (s === null) return { t: r.t, skipped: 'the skeptic did not finish' }
  if (!OPUS_RE.test(s.model)) return { t: r.t, skipped: `the skeptic ran on ${s.model}; only Opus judges (owner rule)` }
  return { ...r, s }
}

function answerLine(r) {
  const { t, v, s } = r
  const coherence = t.kind === 'coherence'
  const verifier = `${v.model} (verifier agent, theo-claim-check, ${t.task_id})`
  const line = {
    task_id: t.task_id,
    verdict: v.verdict,
    quote: coherence ? '' : v.quote,
    quote_source_id: coherence ? '' : v.quote_source_id,
    explanation: v.explanation,
    fix_suggestion: v.fix_suggestion,
    answered_by: verifier,
    skeptic_by: '',
  }
  if (v.verdict !== 'supported') return line
  const skeptic = `${s.model} (skeptic agent, theo-claim-check, ${t.task_id})`
  if (s.verdict === 'supported') return { ...line, skeptic_by: skeptic }
  return {
    ...line,
    verdict: s.verdict,
    quote: '',
    quote_source_id: '',
    explanation: `The verifier judged it supported (${v.explanation}); the skeptic refuted that: ${s.explanation}`,
    fix_suggestion: s.fix_suggestion,
    answered_by: `${verifier}, overruled by ${skeptic}`,
  }
}

phase('Verify')
const results = await pipeline(inv.tasks, (_prev, t) => verify(t), (r) => challenge(r))

const answered = []
const notAnswered = []
results.forEach((r, i) => {
  const t = inv.tasks[i]
  if (r === null) notAnswered.push({ task_id: t.task_id, ref: t.ref, reason: 'its stage failed' })
  else if (r.skipped) notAnswered.push({ task_id: t.task_id, ref: t.ref, reason: r.skipped })
  else answered.push(r)
})
for (const n of notAnswered) log(`not answered: ${n.ref} (${n.task_id}): ${n.reason}`)

// ---- Write: append the answers, a few lines per agent, one agent at a time ------------------

phase('Write')
const lines = answered.map(answerLine)
for (let i = 0; i < lines.length; i += LINES_PER_WRITE) {
  const chunk = lines.slice(i, i + LINES_PER_WRITE)
  const ids = chunk.map((l) => l.task_id)
  const w = await agent(writePrompt(chunk.map((l) => JSON.stringify(l))), {
    label: `write ${i / LINES_PER_WRITE + 1}`,
    phase: 'Write',
    schema: WRITE_SCHEMA,
    effort: 'low',
  })
  const where = `${i} of ${lines.length} answers are in ${DIR}/verdicts.jsonl; resume this run, or run the workflow again (it skips the tasks the file holds)`
  if (w === null) throw new Error(`the write agent did not finish; ${where}`)
  if (w.error) throw new Error(`appending to verdicts.jsonl failed: ${w.error}; ${where}`)
  const got = new Set(w.appended)
  if (got.size !== ids.length || ids.some((id) => !got.has(id))) {
    throw new Error(`the append reported ${JSON.stringify(w.appended)}, expected ${JSON.stringify(ids)}; check ${DIR}/verdicts.jsonl by hand`)
  }
}

const verdicts = {}
for (const l of lines) verdicts[l.verdict] = (verdicts[l.verdict] || 0) + 1
const liveReport = []
for (const s of inv.tdm_sources) {
  const read = await liveReads[s.source_id]
  liveReport.push({ source_id: s.source_id, saved: read ? read.saved : false, detail: read ? read.detail : 'no result' })
}
log(`appended ${lines.length} answers: ${JSON.stringify(verdicts)}`)
return {
  workspace: WS,
  answered: lines.length,
  verdicts,
  overruled_by_skeptic: answered.filter((r) => r.v.verdict === 'supported' && r.s.verdict !== 'supported').length,
  live_reads: liveReport,
  not_answered: notAnswered,
  next: `${STUDIO} paper claims-import ${REQUEST_ID}`,
}
