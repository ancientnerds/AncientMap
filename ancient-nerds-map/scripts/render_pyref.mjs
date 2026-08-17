/**
 * Hydration-gate helper (react-ssr Task 15): render the nine pyref route
 * payloads through the built SSR bundle and print {name: {entry, head,
 * html, route}} as JSON. A Python step splices each into the built shell
 * (pipeline/app_shell.py) exactly like ssr_shell_response() does, so the
 * gate exercises the same document the API would serve — without a DB.
 *
 *   node scripts/render_pyref.mjs > /tmp/ssr_pages.json
 */
import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

import { render } from '../dist-ssr/entry-server.js'

const HERE = dirname(fileURLToPath(import.meta.url))
const PYREF = join(HERE, '..', 'src', 'seo', '__tests__', 'pyref')

const ENTRY_BY_TYPE = {
  story: 'story.html',
  storyArchive: 'story.html',
  site: 'site.html',
  sitesIndex: 'site.html',
  country: 'site.html',
  research: 'research.html',
  researchIndex: 'research.html',
  article: 'articles.html',
  articleIndex: 'articles.html',
}

const NAMES = [
  'story',
  'storyArchive',
  'site',
  'sitesIndex',
  'country',
  'research',
  'researchIndex',
  'article',
  'articleIndex',
]

const out = {}
for (const name of NAMES) {
  const route = JSON.parse(readFileSync(join(PYREF, `${name}.route.json`), 'utf8'))
  const { head, html } = render(route)
  out[name] = { entry: ENTRY_BY_TYPE[route.type], head, html, route }
}
process.stdout.write(JSON.stringify(out))
