/**
 * Layout lint pass (plan C contract C9), cwd video/:
 *   node --import tsx scripts/lint.ts --timeline <timeline.json> --public-dir <dir>
 *        [--every 6] [--scale 0.5] [--report <lint.json>] [--concurrency N]
 * Renders every Nth frame at reduced scale with inputProps.lint = true (no
 * audio, clips not decoded); LayoutGuard logs each violation as a
 * console.error JSON line, collected here through onBrowserLog. Then the
 * teaser of each thumbnail candidate (the Thumbnail composition in lint mode,
 * one frame each; its violations carry the candidate's episode frame). Every
 * browser is proved to draw on the NVIDIA first (cli.ts onNvidia, spec 4.11).
 * Every violation is printed to stderr as that JSON line; the exit code is 1
 * when there is at least one. --report also writes {frames, every, scale,
 * violations}; frames counts the episode frames and the thumbnails checked.
 */
import { mkdirSync, writeFileSync } from 'node:fs'
import path from 'node:path'

import { renderFrames } from '@remotion/renderer'

import { type LintViolation, parseFlags, parseViolation } from './args'
import { RENDER_CHROMIUM, assertAssets, loadTimeline, onNvidia, run, withBundle } from './cli'

export const DEFAULT_EVERY = 6
export const DEFAULT_SCALE = 0.5

run(async () => {
  const flags = parseFlags(process.argv.slice(2), {
    timeline: { required: true, kind: 'path' },
    'public-dir': { required: true, kind: 'path' },
    every: { required: false, kind: 'int' },
    scale: { required: false, kind: 'number' },
    report: { required: false, kind: 'path' },
    concurrency: { required: false, kind: 'int' },
  })
  const timeline = loadTimeline(flags.timeline as string)
  const publicDir = flags['public-dir'] as string
  assertAssets(timeline, publicDir)
  const every = (flags.every as number | undefined) ?? DEFAULT_EVERY
  const scale = (flags.scale as number | undefined) ?? DEFAULT_SCALE
  if (every < 1) throw new Error('--every must be >= 1')
  const inputProps = { timeline, lint: true, narrationSpans: [], imageSizes: {}, gpu: '' }
  const violations: LintViolation[] = []
  let frames = 0
  // The frames themselves are thrown away: only LayoutGuard's console output matters.
  // chromiumOptions: a crash-replacement browser must draw on the NVIDIA too (cli.ts RENDER_CHROMIUM).
  const discard = {
    imageFormat: 'jpeg',
    jpegQuality: 50,
    muted: true,
    outputDir: null,
    onFrameBuffer: () => undefined,
    timeoutInMilliseconds: 120_000,
    chromiumOptions: RENDER_CHROMIUM,
  } as const
  await withBundle(publicDir, async (serveUrl) => {
    await onNvidia(serveUrl, 'Episode', inputProps, (browser, composition) =>
      renderFrames({
        ...discard,
        composition,
        serveUrl,
        inputProps,
        puppeteerInstance: browser,
        everyNthFrame: every,
        scale,
        concurrency: (flags.concurrency as number | undefined) ?? null,
        onStart: ({ frameCount }) => console.log(`lint: ${frameCount} frames (every ${every}, scale ${scale})`),
        onFrameUpdate: (rendered) => {
          frames = rendered
        },
        onBrowserLog: (log) => {
          const v = parseViolation(log.text)
          if (v) violations.push(v)
        },
      }),
    )
    for (const [i, thumb] of timeline.thumbnails.entries()) {
      const thumbProps = { timeline, candidate: i + 1, frame: thumb.frame, lint: true, imageSizes: {}, gpu: '' }
      await onNvidia(serveUrl, 'Thumbnail', thumbProps, (browser, composition) =>
        renderFrames({
          ...discard,
          composition,
          serveUrl,
          inputProps: thumbProps,
          puppeteerInstance: browser,
          scale,
          concurrency: 1,
          onStart: () => console.log(`lint: thumbnail ${i + 1} (frame ${thumb.frame})`),
          onFrameUpdate: () => undefined,
          onBrowserLog: (log) => {
            const v = parseViolation(log.text)
            if (v) violations.push({ ...v, frame: thumb.frame })
          },
        }),
      )
      frames += 1
    }
  })
  if (flags.report) {
    const report = flags.report as string
    mkdirSync(path.dirname(report), { recursive: true })
    writeFileSync(report, JSON.stringify({ frames, every, scale, violations }, null, 2))
  }
  for (const v of violations) console.error(JSON.stringify(v))
  if (violations.length) throw new Error(`${violations.length} layout violation(s) in ${frames} checked frames`)
  console.log(`lint clean: ${frames} frames checked`)
})
