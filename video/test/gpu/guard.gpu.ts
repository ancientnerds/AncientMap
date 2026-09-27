/**
 * The layout lint fires in a real browser (workstation only, not CI: it needs
 * the RTX 3080, spec 4.11). Run from video/: `npm run test:gpu`.
 *
 * guardFixture.tsx plants violations and delays the brand fonts; these tests
 * render it the way scripts/lint.ts does (renderFrames at scale 0.5, the
 * violations read from onBrowserLog) and require exactly the planted lines:
 * the overflow of a teaser that needs three lines in Orbitron (on every tab's
 * first frame too), text outside the title-safe area, text in the YouTube
 * controls, and an overlap; and nothing from a render outside lint mode or
 * from a registry that does not measure.
 */
import { cpSync, mkdirSync, mkdtempSync, rmSync } from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

import { bundle } from '@remotion/bundler'
import { openBrowser, renderFrames, selectComposition } from '@remotion/renderer'
import { afterAll, beforeAll, describe, expect, it } from 'vitest'

import { SITE_PUBLIC_DIR } from '../../scripts/fontCoverage'
import type { Violation } from '../../src/layout/geometry'
import { VIOLATION_TYPE, violationLine } from '../../src/layout/LayoutGuard'
import { FONT_FILES } from '../../src/theme/fonts'

const NVIDIA = /^ANGLE \(NVIDIA, NVIDIA GeForce RTX 3080/
const SLOW = 180_000

let work = ''
let serveUrl = ''

beforeAll(async () => {
  work = mkdtempSync(path.join(os.tmpdir(), 'studio-guard-'))
  const publicDir = path.join(work, 'public')
  for (const file of FONT_FILES) {
    mkdirSync(path.dirname(path.join(publicDir, file)), { recursive: true })
    cpSync(path.join(SITE_PUBLIC_DIR, file), path.join(publicDir, file))
  }
  serveUrl = await bundle({ entryPoint: fileURLToPath(new URL('./guardFixture.tsx', import.meta.url)), publicDir, outDir: path.join(work, 'bundle') })
}, SLOW)

afterAll(() => {
  rmSync(work, { recursive: true, force: true })
})

/** Render every frame of `id` in a browser on the NVIDIA and return its renderer and its layout-violation console lines, sorted. */
async function lint(id: string, props: Record<string, unknown>, concurrency: number): Promise<{ gpu: string; lines: string[] }> {
  const browser = await openBrowser('chrome', { chromiumOptions: { gl: 'angle' } })
  try {
    const inputProps = { gpu: '', ...props }
    const composition = await selectComposition({ serveUrl, id, inputProps, puppeteerInstance: browser })
    const lines: string[] = []
    await renderFrames({
      composition,
      serveUrl,
      inputProps,
      puppeteerInstance: browser,
      imageFormat: 'jpeg',
      jpegQuality: 50,
      muted: true,
      outputDir: null,
      onFrameBuffer: () => undefined,
      onStart: () => undefined,
      onFrameUpdate: () => undefined,
      scale: 0.5,
      concurrency,
      timeoutInMilliseconds: 60_000,
      logLevel: 'error',
      onBrowserLog: (log) => {
        if (log.text.startsWith(`{"type":"${VIOLATION_TYPE}"`)) lines.push(log.text)
      },
    })
    return { gpu: String(composition.props.gpu), lines: lines.sort() }
  } finally {
    await browser.close({ silent: true })
  }
}

const expected = (entries: [number, Violation][]) => entries.map(([frame, v]) => violationLine(frame, v)).sort()

describe('LayoutGuard in a real browser (fonts arriving after the first frame)', () => {
  it('reports exactly the planted violations of every frame, each tab`s first frame included', async () => {
    const { gpu, lines } = await lint('Planted', { lint: true }, 2)
    expect(gpu).toMatch(NVIDIA)
    const want: [number, Violation][] = []
    for (let frame = 0; frame < 6; frame++) {
      want.push([frame, { a: 'teaser', b: null, reason: 'overflow' }])
      want.push([frame, { a: 'edge', b: null, reason: 'outside-safe' }])
      want.push([frame, { a: 'captions', b: 'lt', reason: 'overlap' }])
      if (frame >= 3) want.push([frame, { a: 'drop', b: null, reason: 'controls' }])
    }
    expect(lines).toEqual(expected(want))
  }, SLOW)

  it('measures nothing outside lint mode', async () => {
    const { gpu, lines } = await lint('Planted', { lint: false }, 2)
    expect(gpu).toMatch(NVIDIA)
    expect(lines).toEqual([])
  }, SLOW)

  it('checks a one-frame thumbnail teaser, and only the teaser', async () => {
    const overflowing = await lint('TeaserOnly', { lint: true, candidate: 1 }, 1)
    expect(overflowing.gpu).toMatch(NVIDIA)
    expect(overflowing.lines).toEqual(expected([[0, { a: 'thumbnail1:teaser', b: null, reason: 'overflow' }]]))
    const fitting = await lint('TeaserOnly', { lint: true, candidate: 2 }, 1)
    expect(fitting.lines).toEqual([])
  }, SLOW)
})
