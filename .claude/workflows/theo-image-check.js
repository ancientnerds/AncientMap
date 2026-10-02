export const meta = {
  name: 'theo-image-check',
  description: 'Answer images/pending.jsonl of a paper workspace: one agent looks at each candidate picture; appends images/verdicts.jsonl',
  whenToUse: 'theo-write, after ./.venv/Scripts/python.exe -m pipeline.studio paper images-export <id> and before paper images-import <id>. args: {"workspace": "<absolute path of STUDIO_ASSETS/papers/<request_id>>"}',
  phases: [
    { title: 'Inventory', detail: 'pending.jsonl minus the tasks verdicts.jsonl already holds' },
    { title: 'Look', detail: 'one agent per candidate picture' },
    { title: 'Write', detail: 'append the answers to images/verdicts.jsonl' },
  ],
}

/*
 * The image check of spec 3.6 and plan C's contract C2, answered by Sonnet 5.5 agents.
 *
 * Input: the handoff directory <workspace>/images/ that `paper images-export` wrote
 * (pipeline/studio/paper/images.py, pipeline/studio/handoff.py). Output: one line per answered
 * task appended to images/verdicts.jsonl:
 *   {task_id, prompt_sha256, verdict: meaningful|weak|misleading|off_topic, depicts,
 *    subject_box: [x, y, w, h] fractions | null, caption, answered_by}
 * The caption is one plain-English sentence of at most 120 characters for meaningful and weak,
 * "" otherwise. `paper images-import` validates the file, refuses it whole on any problem,
 * then selects and embeds one picture per opportunity.
 *
 * - Tasks that already have a line in verdicts.jsonl are not answered again. A file that
 *   images-import refused stays in place: delete its bad lines, then run this workflow again.
 * - Only Sonnet 5.5 or Opus judges (owner rule 2026-10-02): an agent that reports another model ID gets no answer
 *   written; its task stays pending and is listed in the result.
 * - An answer with a box outside the picture or a meaningful or weak picture without a caption
 *   is not written; its task is listed with the reason. The answer schema holds a caption to
 *   120 characters without [ or *, and the prompt asks for Latin script. The one rule the
 *   workflow cannot check is the script itself (images.answer_check's Latin-script test is
 *   Python, theo_citations.contains_non_latin_script): a caption in another script is refused
 *   by `paper images-import`, which names its answer and refuses the file whole.
 * - prompt_sha256 is copied by the append command from the pending.jsonl row of the same
 *   task_id (the agent read prompts/<task_id>.txt; a task id is derived from its prompt's hash).
 */

const PY = './.venv/Scripts/python.exe'
const STUDIO = `${PY} -m pipeline.studio`
const PART = 'verdicts.part.jsonl'
const LINES_PER_WRITE = 20
const KEEP = ['meaningful', 'weak']
const MAX_CAPTION_CHARS = 120
const JUDGE_RE = /^claude-(sonnet|opus)-/
// Every subagent runs on Sonnet 5.5 (owner rule 2026-10-02, also for the checks).
const judge = (prompt, opts = {}) => agent(prompt, { ...opts, model: 'sonnet' })

if (!args || typeof args.workspace !== 'string' || !args.workspace.trim()) {
  throw new Error('args.workspace must be the absolute path of the paper workspace <STUDIO_ASSETS>/papers/<request_id>')
}
const WS = args.workspace.trim().replace(/\\/g, '/').replace(/\/+$/, '')
const DIR = `${WS}/images`
const REQUEST_ID = WS.split('/').pop()

const INVENTORY_CMD = `${PY} -c "
import json, pathlib, sys
from pipeline.studio import handoff
d = pathlib.Path(sys.argv[1])
v = d / handoff.VERDICTS_FILE
done = {r.get('task_id') for r in handoff.read_jsonl(v)} if v.exists() else set()
rows = [r for r in handoff.read_jsonl(d / handoff.PENDING_FILE) if r['task_id'] not in done]
print(json.dumps({'in_verdicts_file': len(done), 'tasks': [{'task_id': r['task_id'], 'ref': r['ref']} for r in rows]}, indent=1))
" "${DIR}"`

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

const INVENTORY_SCHEMA = {
  type: 'object',
  properties: {
    error: { type: 'string' },
    in_verdicts_file: { type: 'integer', minimum: 0 },
    tasks: {
      type: 'array',
      items: {
        type: 'object',
        properties: { task_id: { type: 'string' }, ref: { type: 'string' } },
        required: ['task_id', 'ref'],
      },
    },
  },
  required: ['error', 'in_verdicts_file', 'tasks'],
}

const ANSWER_SCHEMA = {
  type: 'object',
  properties: {
    verdict: { type: 'string', enum: ['meaningful', 'weak', 'misleading', 'off_topic'] },
    depicts: { type: 'string' },
    subject_box: {
      anyOf: [
        { type: 'array', items: { type: 'number', minimum: 0, maximum: 1 }, minItems: 4, maxItems: 4 },
        { type: 'null' },
      ],
    },
    caption: { type: 'string', maxLength: MAX_CAPTION_CHARS, pattern: '^[^\\[*]*$' },
    model: { type: 'string', description: 'The exact model ID your system prompt names, for example claude-sonnet-5-5' },
  },
  required: ['verdict', 'depicts', 'subject_box', 'caption', 'model'],
}

const WRITE_SCHEMA = {
  type: 'object',
  properties: {
    appended: { type: 'array', items: { type: 'string' } },
    error: { type: 'string' },
  },
  required: ['appended', 'error'],
}

function lookPrompt(t) {
  return [
    'You check one candidate picture for a Theo paper (Ancient Nerds): does it show the reader the subject of the paragraph it would sit under?',
    [`Paper workspace: ${WS}`, `Task: ${t.task_id} (ref ${t.ref})`, `Prompt file: ${DIR}/prompts/${t.task_id}.txt`].join('\n'),
    '1. Read the prompt file in full. It is the exact question and its rules bind you. Its task JSON holds the subject, the paragraph, image_path and the candidate\'s metadata (title, description, licence, source).',
    `2. Open the picture ${WS}/<image_path> (image_path from the task JSON, relative to the paper workspace) with the Read tool and look at it.`,
    '3. Judge from the picture and the task JSON only: no web search. Do not create, edit or delete any file.',
    'Ignore the answer-format paragraph at the end of the prompt file: answer through the structured output below; the workflow adds task_id, prompt_sha256 and answered_by.',
    `Answer with: verdict; depicts: what the picture actually shows, one sentence; subject_box: [x, y, w, h] as fractions of the picture's width and height around the subject, with x + w and y + h at most 1, or null; caption: for meaningful or weak, one plain-English sentence of at most ${MAX_CAPTION_CHARS} characters in Latin script, without [ or *, that says what the reader sees, and "" otherwise; model.`,
  ].join('\n\n')
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
const inv = await judge(
  [
    `List the pending image-check tasks of the paper workspace ${WS}. ${RUN_ONCE} Change no file.`,
    command(INVENTORY_CMD),
    'If the command fails, answer with error: the last line of its error output, in_verdicts_file 0 and an empty task list. Otherwise answer with error "" and copy the printed JSON exactly: in_verdicts_file and every task with its task_id and ref.',
  ].join('\n\n'),
  { label: 'inventory', phase: 'Inventory', schema: INVENTORY_SCHEMA, effort: 'low' },
)
if (inv === null) throw new Error('the inventory agent did not finish')
if (inv.error) throw new Error(`reading ${DIR}/pending.jsonl failed: ${inv.error} (run \`${STUDIO} paper images-export ${REQUEST_ID}\` first)`)
if (inv.in_verdicts_file) {
  log(`${inv.in_verdicts_file} tasks already have a line in verdicts.jsonl and are not answered again (run images-import; if it refused the file, delete the refused lines first)`)
}
log(`${inv.tasks.length} candidate pictures to check`)
if (!inv.tasks.length) {
  return { workspace: WS, answered: 0, verdicts: {}, not_answered: [], next: `${STUDIO} paper images-import ${REQUEST_ID}` }
}

// ---- Look: one agent per picture ------------------------------------------------------------

async function look(t) {
  const a = await judge(lookPrompt(t), { label: `look ${t.ref}`, phase: 'Look', schema: ANSWER_SCHEMA })
  if (a === null) return { t, skipped: 'the agent did not finish' }
  if (!JUDGE_RE.test(a.model)) return { t, skipped: `the agent ran on ${a.model}; only Sonnet 5.5 or Opus judges (owner rule 2026-10-02)` }
  const box = a.subject_box
  if (box !== null && (box[0] + box[2] > 1.0001 || box[1] + box[3] > 1.0001)) {
    return { t, skipped: `subject_box ${JSON.stringify(box)} reaches outside the picture` }
  }
  const keep = KEEP.includes(a.verdict)
  if (keep && !a.caption.trim()) return { t, skipped: `a ${a.verdict} picture needs a caption` }
  return {
    t,
    line: {
      task_id: t.task_id,
      verdict: a.verdict,
      depicts: a.depicts,
      subject_box: box,
      caption: keep ? a.caption.trim() : '',
      answered_by: `${a.model} (image check agent, theo-image-check, ${t.task_id})`,
    },
  }
}

phase('Look')
const results = await pipeline(inv.tasks, (_prev, t) => look(t))

const lines = []
const notAnswered = []
results.forEach((r, i) => {
  const t = inv.tasks[i]
  if (r === null) notAnswered.push({ task_id: t.task_id, ref: t.ref, reason: 'its stage failed' })
  else if (r.skipped) notAnswered.push({ task_id: t.task_id, ref: t.ref, reason: r.skipped })
  else lines.push(r.line)
})
for (const n of notAnswered) log(`not answered: ${n.ref} (${n.task_id}): ${n.reason}`)

// ---- Write: append the answers, a few lines per agent, one agent at a time ------------------

phase('Write')
for (let i = 0; i < lines.length; i += LINES_PER_WRITE) {
  const chunk = lines.slice(i, i + LINES_PER_WRITE)
  const ids = chunk.map((l) => l.task_id)
  const w = await judge(writePrompt(chunk.map((l) => JSON.stringify(l))), {
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
log(`appended ${lines.length} answers: ${JSON.stringify(verdicts)}`)
return {
  workspace: WS,
  answered: lines.length,
  verdicts,
  not_answered: notAnswered,
  next: `${STUDIO} paper images-import ${REQUEST_ID}`,
}
