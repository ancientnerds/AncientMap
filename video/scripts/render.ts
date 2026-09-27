/**
 * Render an episode (plan C contract C9), cwd video/:
 *   node --import tsx scripts/render.ts --timeline <timeline.json> --public-dir <dir> --out <file.mp4>
 *        [--chunk-frames 3600] [--concurrency N]
 * H.264 (NVENC) + AAC 320k, 1920x1080 at the timeline's 60 fps, BT.709.
 *
 * GPU rule (spec 4.11): every chunk renders in a fresh browser whose WebGL
 * renderer is proved to be the NVIDIA (cli.ts onNvidia; a chunk in which
 * Remotion replaces that browser after a crash is cancelled and fails the
 * run), and encodes with
 * hardwareAcceleration 'required' (no software fallback) plus nvencOverride,
 * which pins h264_nvenc to GPU 0 and fails on any other encoder.
 *
 * Chunks: the episode renders in frameRange chunks of at most --chunk-frames
 * frames, each in its own browser (the angle GL backend leaks memory on long
 * renders). Each chunk writes its video without B-frames and its audio (the
 * narration clips and the ducked music bed) as a separate 16-bit PCM WAV: at
 * 48 kHz and 60 fps a frame is exactly 800 samples, so the WAV parts join
 * sample-exactly and the video parts frame-exactly, both by the ffmpeg concat
 * demuxer. The joined audio is encoded to AAC 320k once here;
 * pipeline/studio/render.py re-encodes it once at 320k after the loudness
 * gain. The frame count is checked against the timeline. Exit code 1 on any
 * failure.
 */
import { mkdirSync, rmSync, writeFileSync } from 'node:fs'
import path from 'node:path'

import { renderMedia } from '@remotion/renderer'

import { chunkRanges, concatList, nvencOverride, parseFlags, progressPrinter } from './args'
import { RENDER_CHROMIUM, assertAssets, countFrames, ffmpeg, loadTimeline, onNvidia, run, withBundle } from './cli'

export const VIDEO_BITRATE = '16M'
export const AUDIO_BITRATE = '320k'
export const DEFAULT_CHUNK_FRAMES = 3600

run(async () => {
  const flags = parseFlags(process.argv.slice(2), {
    timeline: { required: true, kind: 'path' },
    'public-dir': { required: true, kind: 'path' },
    out: { required: true, kind: 'path' },
    'chunk-frames': { required: false, kind: 'int' },
    concurrency: { required: false, kind: 'int' },
  })
  const timeline = loadTimeline(flags.timeline as string)
  const publicDir = flags['public-dir'] as string
  assertAssets(timeline, publicDir)
  const out = flags.out as string
  const chunkFrames = (flags['chunk-frames'] as number | undefined) ?? DEFAULT_CHUNK_FRAMES
  const concurrency = (flags.concurrency as number | undefined) ?? null
  const inputProps = { timeline, lint: false, narrationSpans: [], imageSizes: {}, gpu: '' }
  const parts = `${out}.parts`
  rmSync(parts, { recursive: true, force: true })
  mkdirSync(parts, { recursive: true })
  const ranges = chunkRanges(timeline.durationInFrames, chunkFrames)
  const videoFiles: string[] = []
  const audioFiles: string[] = []
  await withBundle(publicDir, async (serveUrl) => {
    for (const [i, range] of ranges.entries()) {
      const name = path.join(parts, `part-${String(i).padStart(3, '0')}`)
      const report = progressPrinter(`part ${i + 1}/${ranges.length}`, 25)
      await onNvidia(serveUrl, 'Episode', inputProps, (browser, composition, cancelSignal) =>
        renderMedia({
          composition,
          serveUrl,
          inputProps,
          puppeteerInstance: browser,
          chromiumOptions: RENDER_CHROMIUM,
          cancelSignal,
          codec: 'h264',
          frameRange: range,
          outputLocation: `${name}.mp4`,
          audioCodec: 'pcm-16',
          separateAudioTo: `${name}.wav`,
          enforceAudioTrack: true,
          hardwareAcceleration: 'required',
          videoBitrate: VIDEO_BITRATE,
          ffmpegOverride: nvencOverride,
          colorSpace: 'bt709',
          concurrency,
          timeoutInMilliseconds: 120_000,
          onProgress: ({ progress }) => report(progress),
        }),
      )
      videoFiles.push(`${name}.mp4`)
      audioFiles.push(`${name}.wav`)
    }
  })
  const videoList = path.join(parts, 'video.ffconcat')
  const audioList = path.join(parts, 'audio.ffconcat')
  writeFileSync(videoList, concatList(videoFiles))
  writeFileSync(audioList, concatList(audioFiles))
  mkdirSync(path.dirname(out), { recursive: true })
  ffmpeg([
    ...['-f', 'concat', '-safe', '0', '-i', videoList, '-f', 'concat', '-safe', '0', '-i', audioList],
    ...['-map', '0:v:0', '-map', '1:a:0', '-c:v', 'copy', '-c:a', 'aac', '-b:a', AUDIO_BITRATE, '-ar', '48000'],
    ...['-movflags', '+faststart', out],
  ])
  const frames = countFrames(out)
  if (frames !== timeline.durationInFrames) throw new Error(`${out} has ${frames} frames; the timeline has ${timeline.durationInFrames}`)
  rmSync(parts, { recursive: true, force: true })
  console.log(out)
})
