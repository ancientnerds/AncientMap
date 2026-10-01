/**
 * Every block fits its own limits (workstation only, not CI: it needs the RTX
 * 3080, spec 4.11). Run from video/: `npm run test:gpu`.
 *
 * blocks/schemas.ts promises that "length limits are per block, where the text
 * must fit", and `episode check` accepts exactly what the schemas accept. A limit
 * above what the layout can draw therefore fails only at `episode render`, after
 * the voice and the captures. test/capacity.ts builds an episode with every
 * block on both stages and every drawn string at its maxLength; this runs the
 * real scripts/lint.ts on it (the NVIDIA proved by the script, the brand fonts
 * in) and requires that nothing overflows, overlaps or leaves the safe area.
 * When it fails, lower the limit in schemas.ts (or give the text more room), run
 * `npm run registry`, and mirror the registry in tests/pipeline/studio/script_fixtures.py.
 */
import { spawnSync } from 'node:child_process'
import { cpSync, existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

import { afterAll, beforeAll, describe, expect, it } from 'vitest'

import { SITE_PUBLIC_DIR } from '../../scripts/fontCoverage'
import type { LintViolation } from '../../scripts/args'
import { FONT_FILES } from '../../src/theme/fonts'
import { capacityTimeline, solidPng } from '../capacity'

const VIDEO_ROOT = fileURLToPath(new URL('../..', import.meta.url))
const SLOW = 900_000

let work = ''

beforeAll(() => {
  work = mkdtempSync(path.join(os.tmpdir(), 'studio-capacity-'))
})

afterAll(() => {
  rmSync(work, { recursive: true, force: true, maxRetries: 10, retryDelay: 500 })
})

/** The violations of scripts/lint.ts on the capacity episode, grouped by the scene they were found in. */
function lintCapacity(): { status: number | null; output: string; byScene: Map<string, string[]> } {
  const publicDir = path.join(work, 'public')
  const { timeline, assets } = capacityTimeline()
  for (const file of FONT_FILES) {
    mkdirSync(path.dirname(path.join(publicDir, file)), { recursive: true })
    cpSync(path.join(SITE_PUBLIC_DIR, file), path.join(publicDir, file))
  }
  for (const asset of assets) {
    mkdirSync(path.dirname(path.join(publicDir, asset)), { recursive: true })
    // Lint mode never decodes a clip, but every image is drawn (and measured) for real.
    writeFileSync(path.join(publicDir, asset), asset.endsWith('.png') ? solidPng(960, 540) : '')
  }
  const timelineFile = path.join(work, 'timeline.json')
  const report = path.join(work, 'lint.json')
  writeFileSync(timelineFile, JSON.stringify(timeline))
  const run = spawnSync(process.execPath, ['--import', 'tsx', 'scripts/lint.ts', '--timeline', timelineFile, '--public-dir', publicDir, '--report', report], {
    cwd: VIDEO_ROOT,
    encoding: 'utf-8',
    maxBuffer: 256 * 1024 * 1024,
  })
  const output = `${run.stdout}\n${run.stderr}`
  // lint.ts writes its report before it fails on the violations; no report means it failed before linting
  if (!existsSync(report)) throw new Error(`scripts/lint.ts wrote no report (exit ${run.status}):\n${output}`)
  const violations = (JSON.parse(readFileSync(report, 'utf-8')) as { violations: LintViolation[] }).violations
  const byScene = new Map<string, string[]>()
  for (const v of violations) {
    const scene = v.a.split(':')[0]
    const line = `${v.a}${v.b ? ` x ${v.b}` : ''}: ${v.reason}`
    byScene.set(scene, [...new Set([...(byScene.get(scene) ?? []), line])])
  }
  return { status: run.status, output, byScene }
}

describe('the capacity episode in a real browser', () => {
  it('draws every block, on the full and on the hook stage, with every drawn string at its maxLength, without one layout violation', () => {
    const { status, output, byScene } = lintCapacity()
    expect(output).toMatch(/^gpu: ANGLE \(NVIDIA, NVIDIA GeForce RTX 3080/m)
    expect(Object.fromEntries(byScene)).toEqual({})
    expect(status, output).toBe(0)
  }, SLOW)
})
