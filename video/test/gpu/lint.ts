/**
 * The real scripts/lint.ts on a capacity timeline, for the real-browser checks of this folder
 * (capacity.gpu.ts): the episode is written to `work`, every image of it as a generated PNG, the
 * brand fonts beside it, and the lint runs in Remotion's Chrome on the NVIDIA.
 */
import { spawnSync } from 'node:child_process'
import { cpSync, existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

import { SITE_PUBLIC_DIR } from '../../scripts/fontCoverage'
import type { LintViolation } from '../../scripts/args'
import { FONT_FILES } from '../../src/theme/fonts'
import { type CapacityTimeline, solidPng } from '../capacity'

const VIDEO_ROOT = fileURLToPath(new URL('../..', import.meta.url))

/** The violations of scripts/lint.ts on a capacity timeline (the whole episode, or variants of one scene of it), grouped by the scene they were found in. */
export function lintEpisode(work: string, { timeline, assets }: CapacityTimeline): { status: number | null; output: string; byScene: Map<string, string[]> } {
  const publicDir = path.join(work, 'public')
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
