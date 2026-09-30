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

/** Why onNvidia fails a run in which a page of the proved browser was closed by anyone but Remotion. */
export const PAGE_CLOSED = 'a render page of the proved browser was closed from outside mid-render; the render was cancelled at once (owner decision Q17)'

/** Why onNvidia fails a run in which a page of the proved browser crashed. */
export const PAGE_CRASHED = 'a render page of the proved browser crashed mid-render; the render was cancelled at once (owner decision Q17)'

type CdpConnection = HeadlessBrowser['connection']
type AttachedToTarget = { sessionId: string; targetInfo: { targetId: string; type: string } }
type DetachedFromTarget = { sessionId: string; targetId: string }

/**
 * Call `onLost` the moment a page of the browser behind `connection` is closed
 * by anyone but Remotion (PAGE_CLOSED) or crashes (PAGE_CRASHED); the returned
 * function ends the watch. Owner decision Q17: without it, a frame that waits
 * in Remotion's waitForReady (seek-to-frame.js) when its page is closed from
 * outside waits for Remotion's ready timeout, render.ts's 120 s plus 3 s,
 * because neither race that could end that wait ('disposed', 'closed-silent')
 * fires for such a page.
 *
 * Read in Remotion 4.0.529's browser/Connection.js, browser/BrowserPage.js and
 * render-frame-and-retry-target-close.js:
 * - Every page Remotion uses gets a CDP session attached over this connection
 *   (Target.attachToTarget, flatten), and only pages do; the connection emits
 *   the top-level Target.attachedToTarget right after creating the session,
 *   so the crash listener put on that session runs before the one Remotion's
 *   Page adds later, which fails the frame with "Page crashed!".
 * - When a page goes, the connection closes its session, which rejects the
 *   session's pending CDP calls, and then emits Target.detachedFromTarget in
 *   the same message handler. `onLost` runs there, before any of those
 *   rejections reaches Remotion. A cancel from `onLost` therefore stops the
 *   render before Remotion can answer a failed call with a replacement
 *   browser: the frame's race ends on the cancel, and a retry path sees the
 *   stopped signal first.
 * - Remotion closes its own pages with Page.close(), which sends
 *   Target.closeTarget over this connection (after selectComposition, at the
 *   end of renderFrames, in renderStill). The watch wraps `send` to note those
 *   targets, so their detach is no loss.
 */
export function watchPages(connection: CdpConnection, onLost: (why: string) => void): () => void {
  const send = connection.send
  const closedByRemotion = new Set<string>()
  connection.send = function (this: CdpConnection, ...args: Parameters<CdpConnection['send']>) {
    const [method, params] = args
    if (method === 'Target.closeTarget') closedByRemotion.add((params as { targetId: string }).targetId)
    return send.apply(this, args)
  } as CdpConnection['send']
  const pageSessions = new Map<string, NonNullable<ReturnType<CdpConnection['session']>>>()
  const crashed = () => onLost(PAGE_CRASHED)
  const attached = ({ sessionId, targetInfo }: AttachedToTarget) => {
    if (targetInfo.type !== 'page') return
    const session = connection.session(sessionId)
    if (!session) throw new Error(`Target.attachedToTarget named session ${sessionId}, which the connection does not have`)
    session.on('Inspector.targetCrashed', crashed)
    pageSessions.set(sessionId, session)
  }
  const detached = ({ sessionId, targetId }: DetachedFromTarget) => {
    if (!pageSessions.delete(sessionId)) return
    if (!closedByRemotion.has(targetId)) onLost(PAGE_CLOSED)
  }
  connection.on('Target.attachedToTarget', attached)
  connection.on('Target.detachedFromTarget', detached)
  return () => {
    connection.off('Target.attachedToTarget', attached)
    connection.off('Target.detachedFromTarget', detached)
    for (const session of pageSessions.values()) session.off('Inspector.targetCrashed', crashed)
    connection.send = send
  }
}

/**
 * Open a render browser with RENDER_CHROMIUM, resolve the composition in it and
 * prove from its WebGL renderer (the `gpu` prop calculateMetadata sets) that it
 * draws on the NVIDIA. The browser is closed when `work` ends, successfully or
 * not.
 *
 * onNvidia cancels `cancelSignal`, which `work` passes to each of its
 * renderMedia, renderFrames and renderStill calls, the moment the run can no
 * longer keep the GPU rule or finish, and then throws why:
 * - PAGE_CLOSED or PAGE_CRASHED (watchPages, owner decision Q17): a page of
 *   the proved browser was closed from outside or crashed.
 * - REPLACED_BROWSER: a browser Remotion opens in place of this one (see
 *   RENDER_CHROMIUM) is never proved, so a run that goes on in it breaks the
 *   GPU rule. The sign is the proved browser's 'closed-silent' event:
 *   Remotion's replaceBrowser (replace-browser.js) closes the browser it
 *   replaces with close({silent: true}) before it opens the new one, and
 *   nothing else closes this browser before the finally below
 *   (render-frames.js and renderStill close only their own pages when given a
 *   puppeteerInstance). A page lost from outside no longer gets that far (the
 *   page watch cancels first); a whole browser that dies still does.
 * Cancelling matters twice: a replacement renders no frame, and the render
 * does not hang (measured 2026-09-27: after a render tab was closed
 * mid-chunk, renderMedia made the replacement and then rendered nothing for
 * 3.5 minutes, until the process was killed). The first reason wins, and it
 * is thrown after any `work` in which one arose.
 */
export async function onNvidia<T>(
  serveUrl: string,
  id: 'Episode' | 'Thumbnail',
  inputProps: Record<string, unknown>,
  work: (browser: HeadlessBrowser, composition: Composition, cancelSignal: CancelSignal) => Promise<T>,
): Promise<T> {
  const browser = await openBrowser('chrome', { chromiumOptions: RENDER_CHROMIUM })
  const { cancelSignal, cancel } = makeCancelSignal()
  let failure: string | null = null
  const fail = (why: string) => {
    failure ??= why
    cancel()
  }
  const onReplaced = () => fail(REPLACED_BROWSER)
  browser.on('closed-silent', onReplaced)
  const stopWatching = watchPages(browser.connection, fail)
  try {
    const composition = await selectComposition({ serveUrl, id, inputProps, puppeteerInstance: browser })
    const problem = nvidiaProblem(String(composition.props.gpu ?? ''))
    if (problem) throw new Error(problem)
    console.log(`gpu: ${composition.props.gpu}`)
    const result = await work(browser, composition, cancelSignal).catch((err: unknown) => {
      throw failure ? new Error(failure, { cause: err }) : err
    })
    if (failure) throw new Error(failure)
    return result
  } finally {
    stopWatching()
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
