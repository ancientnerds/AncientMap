/**
 * A render browser that crashes mid-render fails the run (spec 4.11;
 * workstation only, not CI: it needs the RTX 3080). Run from video/:
 * `npm run test:gpu`.
 *
 * scripts/render.ts renders the demo timeline (it needs only the brand fonts)
 * in chunks of 600 frames. Once the first chunk reports 25 %, each test hits
 * one of its render tabs over the Chrome DevTools protocol:
 * - CDP Page.crash kills the tab's renderer. Remotion 4.0.529 fails the frame
 *   with "Page crashed!" and does not retry it, so the run ends there.
 * - Closing the tab (Target.closeTarget, via /json/close) fails the frame with
 *   Target closed, which Remotion answers with a replacement browser that was
 *   never proved on the NVIDIA. onNvidia (scripts/cli.ts) has to cancel the
 *   chunk and exit 1 with REPLACED_BROWSER, before the chunk finishes and
 *   before a second chunk starts.
 *
 * The render browser's DevTools port: Remotion starts Chrome with
 * --remote-debugging-port=0 in a profile directory it creates under
 * os.tmpdir() (puppeteer_dev_chrome_profile-*), and Chrome writes the port it
 * picked into that directory's DevToolsActivePort file. Each script runs with
 * TMP and TEMP pointing at a directory of its own, so the only profile there
 * belongs to the proved browser.
 */
import { spawn, spawnSync } from 'node:child_process'
import { cpSync, existsSync, mkdirSync, mkdtempSync, readFileSync, readdirSync, rmSync } from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

import { afterAll, beforeAll, describe, expect, it } from 'vitest'

import { REPLACED_BROWSER } from '../../scripts/cli'
import { SITE_PUBLIC_DIR } from '../../scripts/fontCoverage'
import { FONT_FILES } from '../../src/theme/fonts'

const VIDEO_ROOT = fileURLToPath(new URL('../..', import.meta.url))
const DEMO = path.join(VIDEO_ROOT, 'src', 'fixtures', 'demo-timeline.json')
/**
 * One run takes about 20 s (measured 2026-09-27). The watchdog kills a hung one
 * (a chunk left to Remotion's replacement browser never finished in that
 * measurement) before the test timeout, so the test fails with its output.
 */
const WATCHDOG_MS = 120_000
const SLOW = 180_000
const REMOTION_REPLACES = /The browser crashed while rendering frame \d+, retrying 1 more times/

let work = ''
let publicDir = ''

beforeAll(() => {
  work = mkdtempSync(path.join(os.tmpdir(), 'studio-crash-'))
  publicDir = path.join(work, 'public')
  for (const file of FONT_FILES) {
    mkdirSync(path.dirname(path.join(publicDir, file)), { recursive: true })
    cpSync(path.join(SITE_PUBLIC_DIR, file), path.join(publicDir, file))
  }
})

afterAll(() => {
  rmSync(work, { recursive: true, force: true, maxRetries: 10, retryDelay: 500 })
})

type Target = { id: string; type: string; url: string; webSocketDebuggerUrl: string }
type Hit = (endpoint: string, tab: Target) => Promise<void>

/** Open a CDP session on the tab and send Page.crash; the tab's renderer dies with the command in flight, so no answer comes. */
const crashTab: Hit = async (_endpoint, tab) => {
  const ws = new WebSocket(tab.webSocketDebuggerUrl)
  await new Promise<void>((resolve, reject) => {
    ws.onopen = () => resolve()
    ws.onerror = () => reject(new Error(`cannot connect to ${tab.webSocketDebuggerUrl}`))
  })
  ws.send(JSON.stringify({ id: 1, method: 'Page.crash', params: {} }))
}

/** Close the tab through the DevTools HTTP endpoint (Target.closeTarget). */
const closeTab: Hit = async (endpoint, tab) => {
  const res = await fetch(`${endpoint}/json/close/${tab.id}`)
  if (!res.ok) throw new Error(`closing tab ${tab.id}: HTTP ${res.status} ${await res.text()}`)
}

/** The DevTools HTTP endpoint of the one Chrome profile under `tmp`. */
function devtoolsEndpoint(tmp: string): string {
  const profiles = readdirSync(tmp).filter((name) => name.startsWith('puppeteer_dev_chrome_profile-'))
  if (profiles.length !== 1) throw new Error(`expected one Chrome profile in ${tmp}, found ${profiles.join(', ') || 'none'}`)
  const portFile = path.join(tmp, profiles[0], 'DevToolsActivePort')
  if (!existsSync(portFile)) throw new Error(`${portFile} does not exist`)
  return `http://127.0.0.1:${readFileSync(portFile, 'utf-8').split('\n')[0].trim()}`
}

/** Hit one render tab (a page on the bundle's local server) of the proved browser. */
async function hitRenderTab(tmp: string, hit: Hit): Promise<void> {
  const endpoint = devtoolsEndpoint(tmp)
  const targets = (await (await fetch(`${endpoint}/json/list`)).json()) as Target[]
  const tab = targets.find((t) => t.type === 'page' && t.url.startsWith('http://localhost:'))
  if (!tab) throw new Error(`no render tab among ${JSON.stringify(targets.map((t) => [t.type, t.url]))}`)
  await hit(endpoint, tab)
}

/** Run render.ts on the demo in 600-frame chunks, hit a render tab once the first chunk reports 25 %, and return how the script ended. */
async function renderAndHit(hit: Hit): Promise<{ status: number | null; stdout: string; stderr: string }> {
  const tmp = mkdtempSync(path.join(work, 'tmp-'))
  const out = path.join(work, 'out', 'demo.mp4')
  const child = spawn(
    process.execPath,
    ['--import', 'tsx', 'scripts/render.ts', '--timeline', DEMO, '--public-dir', publicDir, '--out', out, '--chunk-frames', '600'],
    { cwd: VIDEO_ROOT, env: { ...process.env, TMP: tmp, TEMP: tmp }, stdio: ['ignore', 'pipe', 'pipe'] },
  )
  let stdout = ''
  let stderr = ''
  // The hit's outcome, held until the script has ended: an error rejects the test there.
  let hitOutcome: Promise<unknown> | null = null
  child.stdout.setEncoding('utf-8').on('data', (chunk: string) => {
    stdout += chunk
    if (!hitOutcome && /^part 1\/4 25%$/m.test(stdout)) hitOutcome = hitRenderTab(tmp, hit).then(() => null, (err: unknown) => err)
  })
  child.stderr.setEncoding('utf-8').on('data', (chunk: string) => {
    stderr += chunk
  })
  const watchdog = setTimeout(() => spawnSync('taskkill', ['/pid', String(child.pid), '/T', '/F']), WATCHDOG_MS)
  const status = await new Promise<number | null>((resolve) => child.on('close', resolve))
  clearTimeout(watchdog)
  if (!hitOutcome) throw new Error(`the first chunk never reached 25 % (exit ${status}):\n${stdout}\n${stderr}`)
  const hitError = await hitOutcome
  if (hitError) throw hitError
  return { status, stdout, stderr }
}

describe('a render browser that crashes mid-render fails the run (spec 4.11)', () => {
  it('a crashed render tab (CDP Page.crash) fails the chunk without a replacement browser', async () => {
    const { status, stdout, stderr } = await renderAndHit(crashTab)
    expect(status, `${stdout}\n${stderr}`).toBe(1)
    expect(stderr).toContain('Error: Page crashed!')
    expect(stderr).not.toMatch(REMOTION_REPLACES)
    expect(stdout.match(/^gpu: /gm)).toHaveLength(1)
    expect(stdout).not.toMatch(/^part 2\/4/m)
  }, SLOW)

  it('a closed render tab makes Remotion replace the browser, and render.ts cancels the chunk and exits 1 with REPLACED_BROWSER', async () => {
    const { status, stdout, stderr } = await renderAndHit(closeTab)
    expect(status, `${stdout}\n${stderr}`).toBe(1)
    expect(stderr).toMatch(REMOTION_REPLACES)
    expect(stderr).toContain(REPLACED_BROWSER)
    expect(stdout.match(/^gpu: /gm)).toHaveLength(1)
    expect(stdout).not.toMatch(/^part 1\/4 100%$/m)
    expect(stdout).not.toMatch(/^part 2\/4/m)
  }, SLOW)
})
