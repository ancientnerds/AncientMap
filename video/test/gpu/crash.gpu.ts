/**
 * A render tab that is closed from outside or crashes mid-render cancels the
 * run at once (spec 4.11, owner decision Q17; workstation only, not CI: it
 * needs the RTX 3080). Run from video/: `npm run test:gpu`.
 *
 * scripts/render.ts renders the demo timeline (it needs only the brand fonts)
 * in chunks of 600 frames. Once the first chunk reports 25 %, each test hits
 * one of its render tabs over the Chrome DevTools protocol:
 * - CDP Page.crash kills the tab's renderer.
 * - Target.closeTarget (via /json/close) closes the tab.
 * onNvidia (scripts/cli.ts watchPages) sees the crash or the tab's detached
 * session before Remotion does and cancels the chunk, and the run exits 1
 * with PAGE_CRASHED or PAGE_CLOSED. That is the only outcome
 * (test/gpu/pageLoss.ts; test/pageLoss.test.ts replays its recorded stderr in
 * CI). Before Q17 a closed tab also ended in one of two other ways: Remotion
 * replaced the proved browser (then cancelled with REPLACED_BROWSER), or a
 * frame waiting in Remotion's waitForReady (seek-to-frame.js) was left to
 * Remotion's ready timeout, about 123 s after the close (6 of 30 runs,
 * measured 2026-09-30). In every outcome the proved browser is the only one
 * that draws a frame, the first chunk never completes and no second chunk
 * starts.
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

import { SITE_PUBLIC_DIR } from '../../scripts/fontCoverage'
import { FONT_FILES } from '../../src/theme/fonts'
import { pageLossOf } from './pageLoss'

const VIDEO_ROOT = fileURLToPath(new URL('../..', import.meta.url))
const DEMO = path.join(VIDEO_ROOT, 'src', 'fixtures', 'demo-timeline.json')
/**
 * The script reaches 25 % of the first chunk 7 to 32 s after its start when
 * warm, and took more than 90 s on the first run after an npm install
 * (measured 2026-09-30).
 */
const START_MS = 180_000
/**
 * The run must end this soon after the hit. Measured 2026-09-30 in 30 runs:
 * 0.9 to 5.9 s after a close, 1.3 to 8.9 s after a crash. That is far
 * below Remotion's ready timeout (render.ts's timeoutInMilliseconds plus
 * 3 s), so a frame left waiting is killed here; pageLossOf refuses a ready
 * timeout of any length besides.
 */
const AT_ONCE_MS = 30_000
const SLOW = START_MS + AT_ONCE_MS + 30_000

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

/**
 * Run render.ts on the demo in 600-frame chunks, hit a render tab once the
 * first chunk reports 25 %, and return how the script ended. A script that
 * does not reach the hit within START_MS, or does not end within AT_ONCE_MS
 * of it, is killed and fails the test with its output.
 */
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
  const killed: string[] = []
  const killAfter = (ms: number, why: string) =>
    setTimeout(() => {
      killed.push(why)
      spawnSync('taskkill', ['/pid', String(child.pid), '/T', '/F'])
    }, ms)
  const watchdogs = [killAfter(START_MS, `the first chunk did not reach 25 % within ${START_MS / 1000} s`)]
  // The hit's outcome, held until the script has ended: an error rejects the test there.
  let hitOutcome: Promise<unknown> | null = null
  child.stdout.setEncoding('utf-8').on('data', (chunk: string) => {
    stdout += chunk
    if (!hitOutcome && /^part 1\/4 25%$/m.test(stdout)) {
      watchdogs.push(killAfter(AT_ONCE_MS, `the run did not end within ${AT_ONCE_MS / 1000} s of the hit`))
      hitOutcome = hitRenderTab(tmp, hit).then(() => null, (err: unknown) => err)
    }
  })
  child.stderr.setEncoding('utf-8').on('data', (chunk: string) => {
    stderr += chunk
  })
  const status = await new Promise<number | null>((resolve) => child.on('close', resolve))
  watchdogs.forEach(clearTimeout)
  if (killed.length) throw new Error(`killed: ${killed.join('; ')}\n${stdout}\n${stderr}`)
  if (!hitOutcome) throw new Error(`the first chunk never reached 25 % (exit ${status}):\n${stdout}\n${stderr}`)
  const hitError = await hitOutcome
  if (hitError) throw hitError
  return { status, stdout, stderr }
}

describe('a render tab lost mid-render cancels the run at once (spec 4.11, owner decision Q17)', () => {
  it.each([
    ['crashed', 'a crashed render tab (CDP Page.crash)', crashTab],
    ['closed', 'a render tab closed from outside (Target.closeTarget)', closeTab],
  ] as const)('%s: %s cancels the chunk at once, and the proved browser is the only one that drew', async (loss, _what, hit) => {
    const { status, stdout, stderr } = await renderAndHit(hit)
    expect(status, `${stdout}\n${stderr}`).toBe(1)
    expect(pageLossOf(stderr)).toBe(loss)
    expect(stdout.match(/^gpu: /gm)).toHaveLength(1)
    expect(stdout).not.toMatch(/^part 1\/4 100%$/m)
    expect(stdout).not.toMatch(/^part 2\/4/m)
  }, SLOW)
})
