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
 * - Closing the tab (Target.closeTarget, via /json/close) ends the run in one
 *   of two ways, depending on what the tab is doing when it goes:
 *   1. A CDP call of the frame fails with Target closed or Session closed,
 *      which Remotion answers with a replacement browser that was never proved
 *      on the NVIDIA. onNvidia (scripts/cli.ts) cancels the chunk, and the run
 *      exits 1 with REPLACED_BROWSER about 0.5 s after the close.
 *   2. The frame is in Remotion's waitForReady (seek-to-frame.js). Its
 *      WaitTask (DOMWorld.js) takes the destroyed context for a navigation and
 *      waits for the next one, which never comes, and neither race that could
 *      end the wait ('disposed', 'closed-silent') fires for a target closed
 *      from outside. The frame fails with Remotion's own ready
 *      timeout (READY_TIMEOUT_MS) about 123.5 s after the close; nothing is
 *      retried, no browser is replaced, and the run exits 1.
 *   Measured on the RTX 3080 on 2026-09-30: 6 of 30 runs of this file took
 *   outcome 2 (the test then takes about 131 s instead of 7.5 s), and 1 of 41
 *   runs of the closed-tab case alone. In the runs of Task 22's review
 *   (2026-09-29), 6 of 25 ended on the old 120 s watchdog with no stderr,
 *   outcome 2 cut short. In both outcomes the proved browser is the only one
 *   that draws a frame, the first chunk never completes and no second chunk
 *   starts.
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
 * How long a frame waits for a closed tab in outcome 2: render.ts's
 * timeoutInMilliseconds (120_000) plus the 3 s Remotion's waitForReady adds
 * (seek-to-frame.js).
 */
const READY_TIMEOUT_MS = 123_000
/**
 * The script reaches 25 % of the first chunk 7 to 20 s after its start, and
 * outcome 2 ends 123.5 s after the close (measured 2026-09-30), so a run takes
 * at most about 145 s. The watchdog kills a run that hangs beyond that (a
 * chunk left to Remotion's replacement browser rendered nothing for 3.5
 * minutes, measured 2026-09-27) before the test timeout, so the test fails
 * with the script's output.
 */
const WATCHDOG_MS = READY_TIMEOUT_MS + 60_000
const SLOW = WATCHDOG_MS + 30_000
const REMOTION_REPLACES = /The browser crashed while rendering frame \d+, retrying 1 more times/
/** Outcome 2's error; its title names the frame only in the second of seekToFrame's two waits. */
const REMOTION_READY_TIMEOUT = new RegExp(
  `TimeoutError: waiting for the page to render the React component(?: at frame \\d+)? failed: timeout ${READY_TIMEOUT_MS}ms exceeded`,
)

type ClosedTabOutcome = 'replaced' | 'ready timeout'

/** Which of the two outcomes of a closed render tab the script's stderr shows; any other stderr throws. */
function closedTabOutcome(stderr: string): ClosedTabOutcome {
  if (REMOTION_REPLACES.test(stderr)) {
    if (!stderr.includes(REPLACED_BROWSER)) throw new Error(`Remotion replaced the proved browser, but the run did not fail with REPLACED_BROWSER:\n${stderr}`)
    return 'replaced'
  }
  if (REMOTION_READY_TIMEOUT.test(stderr)) return 'ready timeout'
  throw new Error(`the run ended neither with REPLACED_BROWSER nor with Remotion's ${READY_TIMEOUT_MS} ms ready timeout:\n${stderr || '(no stderr)'}`)
}

/** The stderr of both outcomes, recorded on the RTX 3080 on 2026-09-30 (stack frames cut). */
const RECORDED_REPLACED = [
  '\u001b[33mThe browser crashed while rendering frame 175, retrying 1 more times. Learn more about this error under https://www.remotion.dev/docs/target-closed\u001b[39m',
  '\u001b[33mThe browser crashed while rendering frame 173, retrying 1 more times. Learn more about this error under https://www.remotion.dev/docs/target-closed\u001b[39m',
  '\u001b[31mError: Protocol error (Page.bringToFront): Session closed. Most likely the page has been closed.\u001b[39m',
  `Error: ${REPLACED_BROWSER}`,
  '    at <anonymous> (C:\\PythonProjects\\AncientMap-studio\\video\\scripts\\cli.ts:120:24)',
].join('\n')
const RECORDED_READY_TIMEOUT = [
  '\u001b[33mTried to get delayRender() handles for timeout, but could not do so because of\u001b[39m \u001b[33mError: Protocol error (Runtime.callFunctionOn): Session closed. Most likely the page has been closed.\u001b[39m',
  'TimeoutError: waiting for the page to render the React component failed: timeout 123000ms exceeded',
  '    at new WaitTask (file:///C:/PythonProjects/AncientMap-studio/video/node_modules/@remotion/renderer/dist/esm/index.mjs:2115:28)',
].join('\n')

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

  it('a closed render tab fails the chunk: render.ts cancels Remotion\'s replacement browser with REPLACED_BROWSER, or the frame fails on Remotion\'s ready timeout', async () => {
    const { status, stdout, stderr } = await renderAndHit(closeTab)
    expect(status, `${stdout}\n${stderr}`).toBe(1)
    expect(['replaced', 'ready timeout']).toContain(closedTabOutcome(stderr))
    expect(stdout.match(/^gpu: /gm)).toHaveLength(1)
    expect(stdout).not.toMatch(/^part 1\/4 100%$/m)
    expect(stdout).not.toMatch(/^part 2\/4/m)
  }, SLOW)

  it('the closed-tab check accepts exactly its two outcomes', () => {
    expect(closedTabOutcome(RECORDED_REPLACED)).toBe('replaced')
    expect(closedTabOutcome(RECORDED_READY_TIMEOUT)).toBe('ready timeout')
    const atFrame = RECORDED_READY_TIMEOUT.replace('component failed', 'component at frame 175 failed')
    expect(closedTabOutcome(atFrame)).toBe('ready timeout')
    // The watchdog's kill leaves no stderr.
    expect(() => closedTabOutcome('')).toThrow('(no stderr)')
    const replacedAndGoingOn = RECORDED_REPLACED.replace(`Error: ${REPLACED_BROWSER}`, 'Error: some other failure')
    expect(() => closedTabOutcome(replacedAndGoingOn)).toThrow('did not fail with REPLACED_BROWSER')
    expect(() => closedTabOutcome(`${RECORDED_READY_TIMEOUT}\n${replacedAndGoingOn}`)).toThrow('did not fail with REPLACED_BROWSER')
    expect(() => closedTabOutcome(RECORDED_READY_TIMEOUT.replace('123000ms', '120000ms'))).toThrow('neither')
    expect(() => closedTabOutcome('Error: Page crashed!')).toThrow('neither')
  })
})
