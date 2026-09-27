import { spawnSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'

import { describe, expect, it } from 'vitest'

const VIDEO_ROOT = fileURLToPath(new URL('..', import.meta.url))
/** A cold `node --import tsx` compiles the scripts first (about 10 s on the workstation). */
const SLOW = 60_000

/** Run a node script the way pipeline/studio/render.py does (tsx), without a browser. */
function run(script: string, args: string[]) {
  return spawnSync(process.execPath, ['--import', 'tsx', `scripts/${script}`, ...args], { cwd: VIDEO_ROOT, encoding: 'utf-8', timeout: 60_000 })
}

describe('the node scripts fail with exit code 1 and a precise message (plan C contract C9)', () => {
  it.each([
    ['lint.ts', []],
    ['render.ts', ['--out', 'out.mp4']],
    ['still.ts', ['--out-dir', 'out', '--candidate', '1']],
  ])('%s refuses a timeline that does not exist', (script, extra) => {
    const result = run(script, ['--timeline', 'no-such-timeline.json', '--public-dir', '.', ...extra])
    expect(result.status).toBe(1)
    expect(result.stderr).toMatch(/timeline not found: .*no-such-timeline\.json/)
  }, SLOW)
  it('refuses unknown and missing flags', () => {
    const unknown = run('render.ts', ['--timeline', 't.json', '--public-dir', '.', '--out', 'o.mp4', '--crf', '18'])
    expect(unknown.status).toBe(1)
    expect(unknown.stderr).toMatch(/unknown flag --crf/)
    const missing = run('still.ts', ['--timeline', 't.json', '--public-dir', '.'])
    expect(missing.status).toBe(1)
    expect(missing.stderr).toMatch(/missing required flag --out-dir/)
  }, SLOW)
  it('still.ts renders one of the three thumbnail candidates (owner decision 24)', () => {
    const noCandidate = run('still.ts', ['--timeline', 't.json', '--public-dir', '.', '--out-dir', 'o'])
    expect(noCandidate.status).toBe(1)
    expect(noCandidate.stderr).toMatch(/missing required flag --candidate/)
    const fourth = run('still.ts', ['--timeline', 't.json', '--public-dir', '.', '--out-dir', 'o', '--candidate', '4'])
    expect(fourth.status).toBe(1)
    expect(fourth.stderr).toMatch(/--candidate must be 1\.\.3, got 4/)
  }, SLOW)
})
