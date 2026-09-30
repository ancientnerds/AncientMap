/**
 * How a run of scripts/render.ts ended after test/gpu/crash.gpu.ts closed or
 * crashed one of its render tabs, read from the script's stderr. Since owner
 * decision Q17 each hit has exactly one outcome: onNvidia (scripts/cli.ts)
 * cancels the render the moment the tab's session detaches (closed) or Chrome
 * reports the crash, and the run exits 1 with PAGE_CLOSED or PAGE_CRASHED.
 * Anything else throws, above all the two ways a closed tab ended before Q17:
 * Remotion's replacement browser (then cancelled with REPLACED_BROWSER), and a
 * frame left waiting for Remotion's ready timeout (about 123 s).
 *
 * Not a test file: crash.gpu.ts uses it on the RTX 3080, and
 * test/pageLoss.test.ts replays recorded stderr through it in CI.
 */
import { PAGE_CLOSED, PAGE_CRASHED } from '../../scripts/cli'

export const REMOTION_REPLACES = /The browser crashed while rendering frame \d+, retrying \d+ more times/
/** Remotion's ready timeout, of any length; its title names the frame only in the second of seekToFrame's two waits. */
const REMOTION_READY_TIMEOUT = /TimeoutError: waiting for the page to render the React component(?: at frame \d+)? failed: timeout \d+ms exceeded/

export type PageLoss = 'closed' | 'crashed'

const LOSSES: readonly (readonly [PageLoss, string])[] = [
  ['closed', PAGE_CLOSED],
  ['crashed', PAGE_CRASHED],
]

/** The one page loss the run's stderr names; any other stderr throws. */
export function pageLossOf(stderr: string): PageLoss {
  if (REMOTION_REPLACES.test(stderr)) throw new Error(`Remotion replaced the proved browser instead of onNvidia cancelling at once:\n${stderr}`)
  if (REMOTION_READY_TIMEOUT.test(stderr)) throw new Error(`a frame waited for Remotion's ready timeout instead of onNvidia cancelling at once:\n${stderr}`)
  const named = LOSSES.filter(([, message]) => stderr.includes(`Error: ${message}`))
  if (named.length !== 1) throw new Error(`the run did not end with exactly one of PAGE_CLOSED and PAGE_CRASHED:\n${stderr || '(no stderr)'}`)
  return named[0][0]
}
