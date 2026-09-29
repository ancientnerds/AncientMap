export const meta = {
  name: 'studio-casefile-verify',
  description: 'Verify every evidence item of an episode case file that is not yet verified, against its paper evidence entry, its archived text or its web page; writes each item\'s verification into casefile.json',
  whenToUse: 'studio-casefile, after writing casefile.json and before python -m pipeline.studio episode check <slug>. args: {"workspace": "<absolute path of STUDIO_ASSETS/episodes/<slug>>"}',
  phases: [
    { title: 'Inventory', detail: 'the evidence items whose verification.status is not verified' },
    { title: 'Verify', detail: 'one agent per item: read its source, judge the statement' },
    { title: 'Write', detail: 'write verification = {status, by, at, method} into casefile.json' },
  ],
}

/*
 * The case-file check of spec 4.2 and 5 and plan C's contract C2. It uses no handoff directory
 * and no studio CLI: its contract is casefile.json itself (pipeline/studio/casefile.py), which
 * `episode check` then enforces (a script may use only verified evidence).
 *
 * For every evidence[] item whose verification.status is not "verified", one Opus agent runs a
 * probe that reads the item from casefile.json and prints the text its verbatim source.quote is
 * checked against, by route:
 *   "paper evidence"  the item has a paper_anchor: that entry of
 *                     <STUDIO_ASSETS>/papers/<request_id>/evidence.json (the paper's claim check
 *                     already tied its quote to the source text);
 *   "archived text"   no paper_anchor, and the item's source_id has an archived text
 *                     (texts/<id>.txt) or a saved live text (claims_check/live/<id>.txt) in that
 *                     paper workspace;
 *   "web page"        otherwise: the page at source.url, read live with the archive's reader
 *                     (pipeline.lyra.archive_completion; Wikipedia through its REST HTML).
 * The agent judges verified, refuted or unverified. One write step then sets, for each checked
 * item, verification = {"status", "by": the verifier agent's id, "at": the UTC time of the
 * write (ISO 8601), "method": the route}. It changes no other key; the file is written back as
 * JSON with an indent of 2.
 *
 * Only Opus judges (owner rule): an agent that reports another model ID gets nothing written;
 * its item stays as it is and is listed in the result.
 */

const PY = './.venv/Scripts/python.exe'
const METHODS = ['paper evidence', 'archived text', 'web page']
const OPUS_RE = /^claude-opus-/

if (!args || typeof args.workspace !== 'string' || !args.workspace.trim()) {
  throw new Error('args.workspace must be the absolute path of the episode workspace <STUDIO_ASSETS>/episodes/<slug>')
}
const EP = args.workspace.trim().replace(/\\/g, '/').replace(/\/+$/, '')
const SLUG = EP.split('/').pop()

const INVENTORY_CMD = `${PY} -c "
import json, pathlib, sys
from pipeline.studio import casefile
from pipeline.studio.episode import EpisodeWorkspace
ep = pathlib.Path(sys.argv[1])
cf = casefile.from_dict(json.loads(EpisodeWorkspace(ep, ep.name).casefile.read_text(encoding='utf-8')))
items = [{'id': e.id, 'status': e.verification.status} for e in cf.evidence if e.verification.status != 'verified']
print(json.dumps({'evidence': len(cf.evidence), 'items': items}, indent=1))
" "${EP}"`

const probeCmd = (id) => `${PY} -c "
import asyncio, json, pathlib, sys
from pipeline.lyra.archive_completion import _client, fetch_document, resolve_fetch_url
from pipeline.studio import casefile
from pipeline.studio.episode import EpisodeWorkspace
from pipeline.studio.paper import claims
from pipeline.studio.paper.evidence import quote_in_text, ws_normalize
from pipeline.studio.paper.workspace import PaperWorkspace
ep, eid = pathlib.Path(sys.argv[1]), sys.argv[2]
ews = EpisodeWorkspace(ep, ep.name)
cf = casefile.from_dict(json.loads(ews.casefile.read_text(encoding='utf-8')))
e = next(x for x in cf.evidence if x.id == eid)
pws = PaperWorkspace(ews.paper_dir(cf.paper.request_id), cf.paper.request_id) if cf.paper else None
out = {'id': e.id, 'kind': e.kind, 'statement': e.statement, 'url': e.source.url, 'quote': e.source.quote}
def near(text):
    t, q = ws_normalize(text), ws_normalize(e.source.quote)
    i = t.find(q) if q else -1
    return {'found': i >= 0, 'chars': len(t), 'context': t[max(0, i - 600):i + len(q) + 600] if i >= 0 else t[:1500]}
async def read(url):
    async with _client() as client:
        return await fetch_document(client, url)
if e.paper_anchor:
    entry = {x['id']: x for x in json.loads(pws.evidence.read_text(encoding='utf-8'))}.get(e.paper_anchor)
    out.update(route='paper evidence', paper_evidence=entry, found=bool(entry) and quote_in_text(e.source.quote, entry['quote']))
else:
    sid = e.source.source_id
    local = [p for p in (pws.text_path(sid), pws.root / claims.live_rel(pws, sid)) if p.exists()] if pws and sid else []
    if local:
        out.update(route='archived text', path=local[0].as_posix(), **near(local[0].read_text(encoding='utf-8')))
    else:
        kind, url = resolve_fetch_url(e.source.url)
        out['route'] = 'web page'
        if kind == 'youtube':
            out['error'] = 'a YouTube source has no page text to read'
        else:
            doc = asyncio.run(read(url))
            out.update(final_url=doc.final_url, **near(doc.text))
print(json.dumps(out, indent=1))
" "${EP}" "${id}"`

const writeCmd = (results) => `${PY} -c "
import datetime, json, pathlib, sys
from pipeline.studio import casefile
from pipeline.studio.episode import EpisodeWorkspace
ep = pathlib.Path(sys.argv[1])
path = EpisodeWorkspace(ep, ep.name).casefile
results = json.loads(sys.argv[2])
data = json.loads(path.read_text(encoding='utf-8'))
items = {e['id']: e for e in data['evidence']}
bad = [r[0] for r in results if r[0] not in items or items[r[0]]['verification']['status'] == 'verified']
if bad:
    sys.exit('not an unverified evidence item of casefile.json: ' + json.dumps(bad))
at = datetime.datetime.now(datetime.UTC).isoformat(timespec='seconds')
for eid, status, method, by in results:
    items[eid]['verification'] = {'status': status, 'by': by, 'at': at, 'method': method}
casefile.from_dict(data)
path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + chr(10), encoding='utf-8', newline='')
print(json.dumps([r[0] for r in results]))
" "${EP}" '${JSON.stringify(results)}'`

const command = (cmd) => `-----BEGIN COMMAND-----\n${cmd}\n-----END COMMAND-----`

const RUN_ONCE = 'Run the command between the markers once, from the repository root (the directory that holds .venv), as one Bash command, exactly as written.'

const INVENTORY_SCHEMA = {
  type: 'object',
  properties: {
    error: { type: 'string' },
    evidence: { type: 'integer', minimum: 0 },
    items: {
      type: 'array',
      items: {
        type: 'object',
        properties: { id: { type: 'string' }, status: { type: 'string' } },
        required: ['id', 'status'],
      },
    },
  },
  required: ['error', 'evidence', 'items'],
}

const VERDICT_SCHEMA = {
  type: 'object',
  properties: {
    status: { type: 'string', enum: ['verified', 'refuted', 'unverified'] },
    method: { type: 'string', enum: METHODS },
    explanation: { type: 'string', minLength: 1 },
    model: { type: 'string', description: 'The exact model ID your system prompt names, for example claude-opus-5-5' },
  },
  required: ['status', 'method', 'explanation', 'model'],
}

const WRITE_SCHEMA = {
  type: 'object',
  properties: {
    updated: { type: 'array', items: { type: 'string' } },
    error: { type: 'string' },
  },
  required: ['updated', 'error'],
}

function verifyPrompt(item) {
  return [
    'You verify one evidence item of the case file of a Case File episode (Ancient Nerds): does its source really say what the item states? A script may show only verified evidence.',
    [`Episode workspace: ${EP}`, `Evidence item: ${item.id} (now ${item.status})`].join('\n'),
    `1. ${RUN_ONCE} It reads the item from casefile.json and prints its statement, its verbatim source quote and the text the quote is checked against, by route:\n- "paper evidence" (the item has a paper_anchor): the entry of the paper's evidence.json with that id (null when there is none); found tells whether the item's quote occurs verbatim, whitespace aside, in the entry's quote.\n- "archived text" (the item names a source_id whose archived text, or saved live text, the paper workspace holds): found, and the context around the quote in that text (the start of the text when the quote is absent); path is the file.\n- "web page" (otherwise): the page at the item's source url read live; found, and the context around the quote (the start of the page when the quote is absent), or error.`,
    command(probeCmd(item.id)),
    '2. Judge:\n- verified: found is true, and the quote read in its context states the statement: the statement says nothing the quote does not (names, dates, numbers, certainty). With route "paper evidence", the entry\'s verdict must also be "supported" and the statement must say no more than the entry\'s claim.\n- refuted: the text is readable and the quote, read in its context, says something else, or the source contradicts the statement.\n- unverified: the text cannot be checked: the command failed while reading the page (its last error line says why), the source is a YouTube video, the page is a paywall, login or cookie wall, or the quote does not occur verbatim in a readable text.\nWith route "archived text" you may read more of the file at path with Grep or fold -s -w 1000 "<file>" | sed -n "1,40p". Do not search the web. Do not create, edit or delete any file.',
    '3. Answer with status; method: the route the command printed ("web page" when it failed while reading the page); explanation: what you found, and for refuted or unverified exactly why; model.',
  ].join('\n\n')
}

// ---- Inventory ------------------------------------------------------------------------------

phase('Inventory')
const inv = await agent(
  [
    `List the evidence items of the case file in ${EP} that are not yet verified. ${RUN_ONCE} Change no file.`,
    command(INVENTORY_CMD),
    'If the command fails, answer with error: the last line of its error output, evidence 0 and an empty item list. Otherwise answer with error "" and copy the printed JSON exactly: evidence (the item count) and every listed item with its id and status.',
  ].join('\n\n'),
  { label: 'inventory', phase: 'Inventory', schema: INVENTORY_SCHEMA, effort: 'low' },
)
if (inv === null) throw new Error('the inventory agent did not finish')
if (inv.error) throw new Error(`reading ${EP}/casefile.json failed: ${inv.error}`)
log(`${inv.items.length} of ${inv.evidence} evidence items are not verified yet`)
if (!inv.items.length) {
  return { workspace: EP, checked: 0, statuses: {}, items: [], not_checked: [], next: `python -m pipeline.studio episode check ${SLUG}` }
}

// ---- Verify: one agent per item -------------------------------------------------------------

async function verify(item) {
  const v = await agent(verifyPrompt(item), { label: `verify ${item.id}`, phase: 'Verify', schema: VERDICT_SCHEMA })
  if (v === null) return { item, skipped: 'the agent did not finish' }
  if (!OPUS_RE.test(v.model)) return { item, skipped: `the agent ran on ${v.model}; only Opus judges (owner rule)` }
  return { item, v, by: `${v.model} (verifier agent, studio-casefile-verify, ${item.id})` }
}

phase('Verify')
const results = await pipeline(inv.items, (_prev, item) => verify(item))

const checked = []
const notChecked = []
results.forEach((r, i) => {
  const item = inv.items[i]
  if (r === null) notChecked.push({ id: item.id, reason: 'its stage failed' })
  else if (r.skipped) notChecked.push({ id: item.id, reason: r.skipped })
  else checked.push(r)
})
for (const n of notChecked) log(`not checked: ${n.id}: ${n.reason}`)

// ---- Write: one agent sets every checked item's verification --------------------------------

phase('Write')
if (checked.length) {
  const rows = checked.map((r) => [r.item.id, r.v.status, r.v.method, r.by])
  const w = await agent(
    [
      `Write the verification of ${rows.length} evidence items into ${EP}/casefile.json. ${RUN_ONCE} It sets verification = {status, by, at, method} of each listed item (at = the UTC time now), changes no other key, checks the result with the case-file parser, writes the file back and prints the ids it updated as a JSON list. Change no other file.`,
      command(writeCmd(rows)),
      'Answer with updated: the printed ids, and error: "". If the command fails, answer with updated [] and error: the last line of its error output, and repair nothing by hand.',
    ].join('\n\n'),
    { label: 'write', phase: 'Write', schema: WRITE_SCHEMA, effort: 'low' },
  )
  if (w === null) throw new Error(`the write agent did not finish; ${EP}/casefile.json may be unchanged: resume this run`)
  if (w.error) throw new Error(`writing ${EP}/casefile.json failed: ${w.error}`)
  const ids = rows.map((row) => row[0])
  const got = new Set(w.updated)
  if (got.size !== ids.length || ids.some((id) => !got.has(id))) {
    throw new Error(`the write reported ${JSON.stringify(w.updated)}, expected ${JSON.stringify(ids)}; check ${EP}/casefile.json by hand`)
  }
}

const statuses = {}
for (const r of checked) statuses[r.v.status] = (statuses[r.v.status] || 0) + 1
log(`wrote ${checked.length} verifications: ${JSON.stringify(statuses)}`)
return {
  workspace: EP,
  checked: checked.length,
  statuses,
  items: checked.map((r) => ({ id: r.item.id, status: r.v.status, method: r.v.method, explanation: r.v.explanation })),
  not_checked: notChecked,
  next: `python -m pipeline.studio episode check ${SLUG}`,
}
