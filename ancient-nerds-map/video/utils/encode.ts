/**
 * ffmpeg encoding utility.
 * Re-encodes WebM (VP8) from StreamRecorder into MP4 (H.264) for web delivery.
 */

import { execSync } from 'child_process'
import { existsSync, mkdirSync } from 'fs'
import { join, dirname } from 'path'
import { fileURLToPath } from 'url'
import { createRequire } from 'module'

const require = createRequire(import.meta.url)
const __filename = fileURLToPath(import.meta.url)
const __dirname = dirname(__filename)

// ffmpeg-static provides a pre-built ffmpeg binary
let ffmpegPath: string
try {
  ffmpegPath = require('ffmpeg-static') as string
} catch {
  ffmpegPath = 'ffmpeg'
}

export interface EncodeOptions {
  webmPath: string
  fps?: number
  outputDir: string
  name: string
  /** Target duration in seconds. If set, frames are stretched/compressed to fit. */
  targetDuration?: number
}

/**
 * Count decoded frames in a WebM file.
 * ffmpeg's progress output uses \r (carriage return) so we parse
 * via stderr redirect and look for the final frame= line.
 */
function probeFrameCount(webmPath: string): number {
  // Run ffmpeg to null, capturing stderr where the progress counter lives.
  // The -progress flag outputs machine-readable stats to stdout.
  const output = execSync(
    `"${ffmpegPath}" -i "${webmPath}" -f null -progress pipe:1 -`,
    { encoding: 'utf-8', stdio: ['pipe', 'pipe', 'pipe'] }
  )
  // -progress outputs "frame=N" lines to stdout
  const lines = output.split('\n')
  let lastFrame = 0
  for (const line of lines) {
    const m = line.match(/^frame=(\d+)/)
    if (m) lastFrame = parseInt(m[1], 10)
  }
  if (lastFrame <= 0) {
    throw new Error(`Failed to probe frame count for ${webmPath}. Output: ${output.slice(0, 200)}`)
  }
  return lastFrame
}

/**
 * Calculate the setpts filter expression.
 *
 * When targetDuration is set, we probe the actual frame count in the WebM
 * (MediaRecorder may drop frames vs our capture count) and calculate
 * the rate that stretches all frames to exactly targetDuration seconds.
 * ffmpeg then duplicates frames as needed to fill the output fps.
 */
function getSetptsRate(webmPath: string, fps: number, targetDuration?: number): number {
  if (!targetDuration) return fps

  const frameCount = probeFrameCount(webmPath)
  const effectiveRate = frameCount / targetDuration
  console.log(`  WebM has ${frameCount} frames, target ${targetDuration}s → effective rate ${effectiveRate.toFixed(2)}fps`)
  return effectiveRate
}

/**
 * Encode a WebM file to MP4 (H.264) with near-lossless quality.
 * Also produces a fast preview version (540p, CRF 30) for progressive loading.
 *
 * Uses setpts to reassign frame timestamps, fixing the duration mismatch
 * caused by MediaRecorder using wall-clock timestamps and occasionally
 * dropping frames from our synthetic-time capture.
 */
export function encodeFrames(options: EncodeOptions): { mp4: string; fast: string } {
  const {
    webmPath,
    fps = 24,
    outputDir,
    name,
    targetDuration,
  } = options

  const mp4Output = join(outputDir, `${name}.mp4`)
  const fastOutput = join(outputDir, `${name}-fast.mp4`)

  mkdirSync(outputDir, { recursive: true })

  const rate = getSetptsRate(webmPath, fps, targetDuration)

  // Full HD quality
  console.log(`  Encoding MP4: ${name}.mp4`)
  execSync(
    `"${ffmpegPath}" -y -i "${webmPath}" ` +
    `-vf "setpts=N/${rate}/TB" -r ${fps} ` +
    `-c:v libx264 -preset medium -crf 22 -pix_fmt yuv420p ` +
    `-movflags +faststart ` +
    `-an "${mp4Output}"`,
    { stdio: 'inherit' }
  )

  // Fast preview (540p, smaller file for instant loading)
  console.log(`  Encoding fast preview: ${name}-fast.mp4`)
  execSync(
    `"${ffmpegPath}" -y -i "${webmPath}" ` +
    `-vf "setpts=N/${rate}/TB,scale=960:540" -r ${fps} ` +
    `-c:v libx264 -preset fast -crf 30 -pix_fmt yuv420p ` +
    `-movflags +faststart ` +
    `-an "${fastOutput}"`,
    { stdio: 'inherit' }
  )

  return { mp4: mp4Output, fast: fastOutput }
}

/**
 * Encode a single scene's WebM to MP4.
 */
export function encodeScene(
  sceneName: string,
  webmPath: string,
  outputDir: string,
  targetDuration?: number,
): { mp4: string; fast: string } {
  return encodeFrames({
    webmPath,
    outputDir,
    name: sceneName,
    targetDuration,
  })
}

/**
 * CLI entry point: encode all captured scenes.
 * Run with: npx tsx video/utils/encode.ts
 */
const isMain = process.argv[1] && fileURLToPath(import.meta.url).includes(process.argv[1])
if (isMain) {
  const webmBase = join(__dirname, '..', 'output')
  const outputDir = join(__dirname, '..', '..', 'public', 'landing', 'video')

  const scenes = [
    // Hero
    'hero',
    // Sections
    'globe-overview',
    'filters-showcase',
    'empires-showcase',
    // Tools
    'search',
    'proximity',
    'measure',
    'map-layers',
    'paleoshoreline',
    'satellite',
    'empires-tool',
    // Regional tours
    'tour-mediterranean',
    'tour-americas',
    'tour-asia',
    'tour-europe',
    'tour-near-east',
    // Empire spotlights
    'empire-roman',
    'empire-achaemenid',
    'empire-egyptian',
    'empire-han',
    'empire-byzantine',
    'empire-maya',
    'empire-inca',
    'empire-indus-valley',
    // Data stories
    'data-sources',
    'data-timeline',
    'data-categories',
    // B-roll
    'broll-dark-rotate',
    'broll-satellite-rotate',
    'broll-country-colors',
    'broll-source-rainbow',
    'broll-ice-age',
    'broll-layers-full',
  ]

  for (const name of scenes) {
    const webmPath = join(webmBase, `${name}.webm`)
    if (!existsSync(webmPath)) {
      console.log(`  Skipping ${name} (no WebM found)`)
      continue
    }

    console.log(`\nEncoding ${name}...`)
    const result = encodeScene(name, webmPath, outputDir)
    console.log(`  -> ${result.mp4}`)
    console.log(`  -> ${result.fast}`)
  }

  console.log('\nAll scenes encoded.')
}
