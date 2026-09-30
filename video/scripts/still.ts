/**
 * Thumbnail candidates (plan C contract C9; owner decisions 24-25), cwd video/:
 *   node --import tsx scripts/still.ts --timeline <timeline.json> --public-dir <dir> --out-dir <dir>
 *        --candidate K [--frame N]
 * Renders candidate K (1-3) of timeline.thumbnails: the Thumbnail composition
 * (the episode frame without captions, ticker or chapter tag; with the scene's
 * in-frame credit line (spec 4.8), bottom left, and the candidate's teaser) at
 * the candidate's frame, or at --frame N (plan C's
 * `episode thumbnail SLUG --candidate K --frame N`), as thumbnail_<K>_3840.png
 * (scale 2, 3840x2160 master) and thumbnail_<K>_1280.jpg (1280x720; quality
 * steps down from 92 until the file is under 2 MB, YouTube's limit), in a
 * browser proved to draw on the NVIDIA (cli.ts onNvidia, spec 4.11). lint.ts
 * checks each teaser's layout; the teaser does not depend on the frame.
 */
import { mkdirSync, statSync } from 'node:fs'
import path from 'node:path'

import { renderStill } from '@remotion/renderer'

import { THUMBNAIL_CANDIDATES } from '../src/timeline'
import { parseFlags } from './args'
import { RENDER_CHROMIUM, assertAssets, loadTimeline, onNvidia, run, withBundle } from './cli'

export const masterName = (candidate: number) => `thumbnail_${candidate}_3840.png`
export const jpegName = (candidate: number) => `thumbnail_${candidate}_1280.jpg`
export const MAX_JPEG_BYTES = 2 * 1024 * 1024
export const JPEG_QUALITIES = [92, 88, 84, 80, 76, 72, 68] as const

run(async () => {
  const flags = parseFlags(process.argv.slice(2), {
    timeline: { required: true, kind: 'path' },
    'public-dir': { required: true, kind: 'path' },
    'out-dir': { required: true, kind: 'path' },
    candidate: { required: true, kind: 'int' },
    frame: { required: false, kind: 'int' },
  })
  const candidate = flags.candidate as number
  if (candidate < 1 || candidate > THUMBNAIL_CANDIDATES) throw new Error(`--candidate must be 1..${THUMBNAIL_CANDIDATES}, got ${candidate}`)
  const timeline = loadTimeline(flags.timeline as string)
  const publicDir = flags['public-dir'] as string
  assertAssets(timeline, publicDir)
  const outDir = flags['out-dir'] as string
  const frame = (flags.frame as number | undefined) ?? timeline.thumbnails[candidate - 1].frame
  const inputProps = { timeline, candidate, frame, lint: false, imageSizes: {}, gpu: '' }
  mkdirSync(outDir, { recursive: true })
  const master = path.join(outDir, masterName(candidate))
  const jpeg = path.join(outDir, jpegName(candidate))
  const fitted = await withBundle(publicDir, (serveUrl) =>
    // cancelSignal: onNvidia cancels a still whose page is closed from outside or crashes (owner decision Q17).
    onNvidia(serveUrl, 'Thumbnail', inputProps, async (browser, composition, cancelSignal) => {
      const onBrowser = { serveUrl, inputProps, puppeteerInstance: browser, chromiumOptions: RENDER_CHROMIUM, cancelSignal }
      await renderStill({ ...onBrowser, composition, output: master, imageFormat: 'png', scale: 3840 / composition.width })
      for (const quality of JPEG_QUALITIES) {
        await renderStill({ ...onBrowser, composition, output: jpeg, imageFormat: 'jpeg', jpegQuality: quality, scale: 1280 / composition.width })
        if (statSync(jpeg).size < MAX_JPEG_BYTES) return true
      }
      return false
    }),
  )
  if (!fitted) throw new Error(`${jpeg} stays above 2 MB even at quality ${JPEG_QUALITIES[JPEG_QUALITIES.length - 1]}`)
  console.log(`candidate ${candidate}, frame ${frame}\n${master}\n${jpeg}`)
})
