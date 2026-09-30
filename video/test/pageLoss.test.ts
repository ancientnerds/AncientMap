/**
 * The check test/gpu/crash.gpu.ts applies to render.ts's stderr after it hit
 * a render tab (test/gpu/pageLoss.ts), run here without a GPU on stderr
 * recorded on the RTX 3080, so CI holds it to exactly one outcome per hit
 * (owner decision Q17).
 */
import { describe, expect, it } from 'vitest'

import { PAGE_CLOSED, PAGE_CRASHED, REPLACED_BROWSER } from '../scripts/cli'
import { pageLossOf } from './gpu/pageLoss'

/**
 * A closed and a crashed render tab since Q17, recorded on the RTX 3080 on
 * 2026-09-30 (stack frames cut). 2 of 15 crashed runs also carried the
 * bringToFront line Remotion's tab cycling logs when a page is gone.
 */
const RECORDED_CLOSED = [`Error: ${PAGE_CLOSED}`, '    at <anonymous> (C:\\PythonProjects\\AncientMap-studio\\video\\scripts\\cli.ts:195:23)'].join('\n')
const RECORDED_CRASHED = [`Error: ${PAGE_CRASHED}`, '    at <anonymous> (C:\\PythonProjects\\AncientMap-studio\\video\\scripts\\cli.ts:195:23)'].join('\n')
const RECORDED_CRASHED_CYCLING = [
  '\u001b[31mProtocolError: Protocol error (Page.bringToFront): Target closed. https://www.remotion.dev/docs/target-closed\u001b[39m',
  RECORDED_CRASHED,
].join('\n')

/** How a hit render tab ended before Q17, recorded on the RTX 3080 on 2026-09-30 (stack frames cut). */
const BEFORE_Q17 = {
  replaced: [
    '\u001b[33mThe browser crashed while rendering frame 175, retrying 1 more times. Learn more about this error under https://www.remotion.dev/docs/target-closed\u001b[39m',
    '\u001b[33mThe browser crashed while rendering frame 173, retrying 1 more times. Learn more about this error under https://www.remotion.dev/docs/target-closed\u001b[39m',
    '\u001b[31mError: Protocol error (Page.bringToFront): Session closed. Most likely the page has been closed.\u001b[39m',
    `Error: ${REPLACED_BROWSER}`,
    '    at <anonymous> (C:\\PythonProjects\\AncientMap-studio\\video\\scripts\\cli.ts:120:24)',
  ].join('\n'),
  readyTimeout: [
    '\u001b[33mTried to get delayRender() handles for timeout, but could not do so because of\u001b[39m \u001b[33mError: Protocol error (Runtime.callFunctionOn): Session closed. Most likely the page has been closed.\u001b[39m',
    'TimeoutError: waiting for the page to render the React component failed: timeout 123000ms exceeded',
    '    at new WaitTask (file:///C:/PythonProjects/AncientMap-studio/video/node_modules/@remotion/renderer/dist/esm/index.mjs:2115:28)',
  ].join('\n'),
  crashed: ['Error: Page crashed!', '    at #onTargetCrashed (file:///C:/PythonProjects/AncientMap-studio/video/node_modules/@remotion/renderer/dist/esm/index.mjs)'].join('\n'),
}

describe('a hit render tab ends the run in exactly one way (owner decision Q17)', () => {
  it('names the page loss onNvidia cancelled on', () => {
    expect(pageLossOf(RECORDED_CLOSED)).toBe('closed')
    expect(pageLossOf(RECORDED_CRASHED)).toBe('crashed')
    expect(pageLossOf(RECORDED_CRASHED_CYCLING)).toBe('crashed')
  })

  it('refuses the ways a hit tab ended before Q17', () => {
    expect(() => pageLossOf(BEFORE_Q17.replaced)).toThrow('Remotion replaced the proved browser')
    expect(() => pageLossOf(BEFORE_Q17.readyTimeout)).toThrow("Remotion's ready timeout")
    expect(() => pageLossOf(BEFORE_Q17.readyTimeout.replace('component failed', 'component at frame 175 failed'))).toThrow("Remotion's ready timeout")
    // A ready timeout of any length: the check does not repeat render.ts's timeout.
    expect(() => pageLossOf(BEFORE_Q17.readyTimeout.replace('123000ms', '33000ms'))).toThrow("Remotion's ready timeout")
    expect(() => pageLossOf(BEFORE_Q17.crashed)).toThrow('exactly one of PAGE_CLOSED and PAGE_CRASHED')
  })

  it('refuses a cancel that came after Remotion had reacted', () => {
    expect(() => pageLossOf(`${BEFORE_Q17.replaced.split('\n')[0]}\n${RECORDED_CLOSED}`)).toThrow('Remotion replaced the proved browser')
    expect(() => pageLossOf(`${BEFORE_Q17.readyTimeout}\n${RECORDED_CLOSED}`)).toThrow("Remotion's ready timeout")
  })

  it('refuses a run that names no loss or both', () => {
    // A watchdog's kill leaves no stderr.
    expect(() => pageLossOf('')).toThrow('(no stderr)')
    expect(() => pageLossOf('Error: some other failure')).toThrow('exactly one of PAGE_CLOSED and PAGE_CRASHED')
    expect(() => pageLossOf(`${RECORDED_CLOSED}\n${RECORDED_CRASHED}`)).toThrow('exactly one of PAGE_CLOSED and PAGE_CRASHED')
  })
})
