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
import { type CancelSignal, type ChromiumOptions, type HeadlessBrowser, makeCancelSignal, openBrowser, selectComposition } from '@remotion/renderer'

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
 * with Target closed or a flaky network error, Remotion 4.0.529 replaces the
 * browser with one built from the render call's own chromiumOptions
 * (render-frames.js makeBrowser; one retry per frame). onNvidia cancels the
 * render call as the replacement starts, and these options keep that browser
 * off SwiftShader until the process exits.
 */
export const RENDER_CHROMIUM: ChromiumOptions = { gl: 'angle' }

/** Why onNvidia fails a run in which Remotion replaced the proved browser. */
export const REPLACED_BROWSER =
  'the render browser crashed mid-render and Remotion replaced it with a browser that was never proved on the NVIDIA (spec 4.11)'

/**
 * Open a render browser with RENDER_CHROMIUM, resolve the composition in it and
 * prove from its WebGL renderer (the `gpu` prop calculateMetadata sets) that it
 * draws on the NVIDIA. The browser is closed when `work` ends, successfully or
 * not.
 *
 * A browser Remotion opens in place of this one (see RENDER_CHROMIUM) is never
 * proved, so a run that goes on in it breaks the GPU rule. The sign is the
 * proved browser's 'closed-silent' event: Remotion's replaceBrowser
 * (replace-browser.js) closes the browser it replaces with close({silent:
 * true}) before it opens the new one, and nothing else closes this browser
 * before the finally below (render-frames.js and renderStill close only their
 * own pages when given a puppeteerInstance). On that event onNvidia cancels
 * `cancelSignal`, which `work` passes to its renderMedia or renderFrames call,
 * and throws REPLACED_BROWSER. Cancelling matters twice: the replacement
 * renders no frame, and the render does not hang (measured 2026-09-27: after a
 * render tab was closed mid-chunk, renderMedia made the replacement and then
 * rendered nothing for 3.5 minutes, until the process was killed).
 * renderStill never replaces its browser in 4.0.529, so a `work`
 * made of renderStill calls may ignore the signal; REPLACED_BROWSER is thrown
 * after any `work` in which the event fired.
 */
export async function onNvidia<T>(
  serveUrl: string,
  id: 'Episode' | 'Thumbnail',
  inputProps: Record<string, unknown>,
  work: (browser: HeadlessBrowser, composition: Composition, cancelSignal: CancelSignal) => Promise<T>,
): Promise<T> {
  const browser = await openBrowser('chrome', { chromiumOptions: RENDER_CHROMIUM })
  const { cancelSignal, cancel } = makeCancelSignal()
  let replaced = false
  const onReplaced = () => {
    replaced = true
    cancel()
  }
  browser.on('closed-silent', onReplaced)
  try {
    const composition = await selectComposition({ serveUrl, id, inputProps, puppeteerInstance: browser })
    const problem = nvidiaProblem(String(composition.props.gpu ?? ''))
    if (problem) throw new Error(problem)
    console.log(`gpu: ${composition.props.gpu}`)
    const result = await work(browser, composition, cancelSignal).catch((err: unknown) => {
      throw replaced ? new Error(REPLACED_BROWSER, { cause: err }) : err
    })
    if (replaced) throw new Error(REPLACED_BROWSER)
    return result
  } finally {
    browser.off('closed-silent', onReplaced)
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
