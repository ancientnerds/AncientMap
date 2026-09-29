export const meta = {
  name: 'studio-marker-check',
  description: 'Answer markers_check/pending.jsonl of an episode workspace: one Opus agent opens the crop and the context picture of each case-file marker and says hits or misses; appends markers_check/verdicts.jsonl',
  whenToUse: 'studio-casefile, after python -m pipeline.studio episode markers-export <slug> and before episode markers-import <slug>. args: {"workspace": "<absolute path of STUDIO_ASSETS/episodes/<slug>>"}',
  phases: [
    { title: 'Inventory', detail: 'pending.jsonl minus the tasks verdicts.jsonl already holds' },
    { title: 'Look', detail: 'one agent per marker' },
    { title: 'Write', detail: 'append the answers to markers_check/verdicts.jsonl' },
  ],
}

/*
 * The crop check of every case-file marker (spec 4.2 and 5; owner rule: every marking must hit
 * the right object, crop check, otherwise no marking), plan C's contract C2 and Task 14b.
 *
 * Input: the handoff directory <episode>/markers_check/ that `episode markers-export` wrote
 * (pipeline/studio/markers.py, pipeline/studio/handoff.py): per marker the crop
 * (markers_check/crops/<mk>.png, the box plus a 10 % margin, enlarged) and the context picture
 * (markers_check/context/<mk>.png, the whole picture with the box outlined in red), both paths
 * relative to the episode directory. Output: one line per answered task appended to
 * markers_check/verdicts.jsonl:
 *   {task_id, prompt_sha256, verdict: hits|misses, explanation, answered_by}
 * `episode markers-import` validates the file and refuses it whole on any problem.
 *
 * - Tasks that already have a line in verdicts.jsonl are not answered again. A file that
 *   markers-import refused stays in place: delete its bad lines, then run this workflow again.
 * - Only Opus judges (owner rule): an agent that reports another model ID gets no answer
 *   written; its task stays pending and is listed in the result.
 * - prompt_sha256 is copied by the append command from the pending.jsonl row of the same
 *   task_id (the agent read prompts/<task_id>.txt; a task id is derived from its prompt's hash).
 */

const PY = './.venv/Scripts/python.exe'
const PART = 'verdicts.part.jsonl'
const LINES_PER_WRITE = 20
const OPUS_RE = /^claude-opus-/

if (!args || typeof args.workspace !== 'string' || !args.workspace.trim()) {
  throw new Error('args.workspace must be the absolute path of the episode workspace <STUDIO_ASSETS>/episodes/<slug>')
}
const EP = args.workspace.trim().replace(/\\/g, '/').replace(/\/+$/, '')
const DIR = `${EP}/markers_check`
const SLUG = EP.split('/').pop()

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
    verdict: { type: 'string', enum: ['hits', 'misses'] },
    explanation: { type: 'string', minLength: 1 },
    model: { type: 'string', description: 'The exact model ID your system prompt names, for example claude-opus-5-5' },
  },
  required: ['verdict', 'explanation', 'model'],
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
    'You check one marker of a Case File episode (Ancient Nerds). The video will draw a labelled marker on a box of a picture. Owner rule: every marking must hit the right object; a marker that misses is not drawn.',
    [`Episode workspace: ${EP}`, `Task: ${t.task_id} (marker ${t.ref})`, `Prompt file: ${DIR}/prompts/${t.task_id}.txt`].join('\n'),
    '1. Read the prompt file in full. It is the exact question and its rules bind you. Its task JSON holds the label, what the picture depicts, the box, crop_path and context_path.',
    `2. Open both pictures with the Read tool and look at them: ${EP}/<crop_path> (the box with a 10 % margin, enlarged) and ${EP}/<context_path> (the whole picture with the box outlined in red). Both paths are in the task JSON, relative to the episode workspace.`,
    '3. Judge from the two pictures and the task JSON only: no web search. Do not create, edit or delete any file.',
    'Ignore the answer-format paragraph at the end of the prompt file: answer through the structured output below; the workflow adds task_id, prompt_sha256 and answered_by.',
    'Answer with: verdict; explanation: what the box covers (for misses: what it actually covers and where the named object is); model.',
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
const inv = await agent(
  [
    `List the pending marker crop checks of the episode workspace ${EP}. ${RUN_ONCE} Change no file.`,
    command(INVENTORY_CMD),
    'If the command fails, answer with error: the last line of its error output, in_verdicts_file 0 and an empty task list. Otherwise answer with error "" and copy the printed JSON exactly: in_verdicts_file and every task with its task_id and ref.',
  ].join('\n\n'),
  { label: 'inventory', phase: 'Inventory', schema: INVENTORY_SCHEMA, effort: 'low' },
)
if (inv === null) throw new Error('the inventory agent did not finish')
if (inv.error) throw new Error(`reading ${DIR}/pending.jsonl failed: ${inv.error} (run \`python -m pipeline.studio episode markers-export ${SLUG}\` first)`)
if (inv.in_verdicts_file) {
  log(`${inv.in_verdicts_file} tasks already have a line in verdicts.jsonl and are not answered again (run markers-import; if it refused the file, delete the refused lines first)`)
}
log(`${inv.tasks.length} markers to check`)
if (!inv.tasks.length) {
  return { workspace: EP, answered: 0, verdicts: {}, not_answered: [], next: `python -m pipeline.studio episode markers-import ${SLUG}` }
}

// ---- Look: one agent per marker -------------------------------------------------------------

async function look(t) {
  const a = await agent(lookPrompt(t), { label: `look ${t.ref}`, phase: 'Look', schema: ANSWER_SCHEMA })
  if (a === null) return { t, skipped: 'the agent did not finish' }
  if (!OPUS_RE.test(a.model)) return { t, skipped: `the agent ran on ${a.model}; only Opus judges (owner rule)` }
  return {
    t,
    line: {
      task_id: t.task_id,
      verdict: a.verdict,
      explanation: a.explanation,
      answered_by: `${a.model} (marker check agent, studio-marker-check, ${t.task_id})`,
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
log(`appended ${lines.length} answers: ${JSON.stringify(verdicts)}`)
return {
  workspace: EP,
  answered: lines.length,
  verdicts,
  misses: lines.filter((l) => l.verdict === 'misses').map((l) => ({ task_id: l.task_id, explanation: l.explanation })),
  not_answered: notAnswered,
  next: `python -m pipeline.studio episode markers-import ${SLUG}`,
}
