/**
 * Shared plumbing of render.ts, lint.ts and still.ts: loading and checking
 * timeline.json, checking the per-render public dir, bundling with it (into
 * bundle/ next to it, removed afterwards), the render browser on the NVIDIA
 * (proved, spec 4.11) and ffmpeg/ffprobe (the binaries pipeline/video/media.py
 * uses: $FFMPEG_BIN / $FFPROBE_BIN, else PATH). Every failure throws; run()
 * turns it into exit code 1 with the message on stderr.
 */
import { execFileSync } from 'node:child_process'
import { existsSync, readFileSync, rmSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

import { bundle } from '@remotion/bundler'
import { type ChromiumOptions, type HeadlessBrowser, openBrowser, selectComposition } from '@remotion/renderer'

import { checkBlocks } from '../src/blocks'
import { FONT_FILES } from '../src/theme/fonts'
import { type Timeline, collectSrcs, parseTimeline } from '../src/timeline'
import { bundleDir, nvidiaProblem, progressPrinter } from './args'

export const VIDEO_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
export const FFMPEG = process.env.FFMPEG_BIN ?? 'ffmpeg'
export const FFPROBE = process.env.FFPROBE_BIN ?? 'ffprobe'

export function loadTimeline(file: string): Timeline {
  if (!existsSync(file)) throw new Error(`timeline not found: ${file}`)
  const timeline = parseTimeline(JSON.parse(readFileSync(file, 'utf-8')))
  checkBlocks(timeline)
  return timeline
}

/** Every file the timeline references, and the brand fonts, must exist in the public dir before Chrome starts. */
export function assertAssets(timeline: Timeline, publicDir: string): void {
  if (!existsSync(publicDir)) throw new Error(`public dir not found: ${publicDir}`)
  const wanted = new Set<string>([...FONT_FILES, ...collectSrcs([timeline.audio, timeline.scenes])])
  const missing = [...wanted].filter((rel) => !existsSync(path.join(publicDir, rel)))
  if (missing.length) throw new Error(`public dir ${publicDir} lacks: ${missing.join(', ')}`)
}

/**
 * Bundle with the public dir into bundleDir(publicDir), run `work` on the bundle and
 * delete the bundle when `work` ends, successfully or not. bundle() copies the whole
 * public dir into its output; its default output, a fresh directory in the system temp
 * dir, is never deleted, so every script run would leave a copy of every capture on C:.
 */
export async function withBundle<T>(publicDir: string, work: (serveUrl: string) => Promise<T>): Promise<T> {
  const outDir = bundleDir(publicDir)
  rmSync(outDir, { recursive: true, force: true })
  try {
    const report = progressPrinter('bundle', 25)
    const serveUrl = await bundle({ entryPoint: path.join(VIDEO_ROOT, 'src', 'index.ts'), publicDir, outDir, onProgress: (p) => report(p / 100) })
    return await work(serveUrl)
  } finally {
    rmSync(outDir, { recursive: true, force: true })
  }
}

type Composition = Awaited<ReturnType<typeof selectComposition>>

/**
 * The render browser's options: the ANGLE/D3D11 backend, which draws on the
 * NVIDIA (Remotion's default gl, null, puts the headless shell on SwiftShader).
 * onNvidia opens its browser with them, and every renderMedia, renderFrames and
 * renderStill call must pass them as its chromiumOptions too: when a frame fails
 * with Target closed (a browser or GPU-process crash), Remotion 4.0.529 replaces
 * the browser with one built from the render call's own chromiumOptions
 * (render-frames.js makeBrowser; one retry per frame), and without them that
 * replacement would finish the chunk on SwiftShader.
 */
export const RENDER_CHROMIUM: ChromiumOptions = { gl: 'angle' }

/**
 * Open a render browser with RENDER_CHROMIUM, resolve the composition in it and
 * prove from its WebGL renderer (the `gpu` prop calculateMetadata sets) that it
 * draws on the NVIDIA. The browser is closed when `work` ends, successfully or
 * not. A replacement browser Remotion opens after a crash (see RENDER_CHROMIUM)
 * uses the same options and executable but is neither re-proved nor closed here;
 * Remotion logs "The browser crashed while rendering frame N" when that happens.
 */
export async function onNvidia<T>(
  serveUrl: string,
  id: 'Episode' | 'Thumbnail',
  inputProps: Record<string, unknown>,
  work: (browser: HeadlessBrowser, composition: Composition) => Promise<T>,
): Promise<T> {
  const browser = await openBrowser('chrome', { chromiumOptions: RENDER_CHROMIUM })
  try {
    const composition = await selectComposition({ serveUrl, id, inputProps, puppeteerInstance: browser })
    const problem = nvidiaProblem(String(composition.props.gpu ?? ''))
    if (problem) throw new Error(problem)
    console.log(`gpu: ${composition.props.gpu}`)
    return await work(browser, composition)
  } finally {
    await browser.close({ silent: true })
  }
}

/** Run ffmpeg (quiet, overwrite); a non-zero exit throws with ffmpeg's stderr. */
export function ffmpeg(args: readonly string[]): void {
  execFileSync(FFMPEG, ['-hide_banner', '-loglevel', 'error', '-y', ...args], { stdio: ['ignore', 'ignore', 'pipe'] })
}

/** Frames of the first video stream, counted by decoding (the audit's count). */
export function countFrames(file: string): number {
  const out = execFileSync(FFPROBE, ['-v', 'error', '-count_frames', '-select_streams', 'v:0', '-show_entries', 'stream=nb_read_frames', '-of', 'csv=p=0', file], {
    encoding: 'utf-8',
  })
  return Number(out.trim())
}

export function run(main: () => Promise<void>): void {
  main().then(
    () => process.exit(0),
    (err: unknown) => {
      console.error(err instanceof Error ? (err.stack ?? err.message) : String(err))
      process.exit(1)
    },
  )
}
