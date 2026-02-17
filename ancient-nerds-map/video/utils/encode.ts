/**
 * ffmpeg encoding utility.
 * Re-encodes WebM (VP9) from StreamRecorder into MP4 (H.264) for web delivery.
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
}

/**
 * Encode a WebM file to MP4 (H.264) with near-lossless quality.
 * Also produces a fast preview version (540p, CRF 30) for progressive loading.
 *
 * The `-r fps` before `-i` forces ffmpeg to interpret the WebM at the target
 * framerate regardless of wall-clock timestamps from MediaRecorder.
 */
export function encodeFrames(options: EncodeOptions): { mp4: string; fast: string } {
  const {
    webmPath,
    fps = 24,
    outputDir,
    name,
  } = options

  const mp4Output = join(outputDir, `${name}.mp4`)
  const fastOutput = join(outputDir, `${name}-fast.mp4`)

  mkdirSync(outputDir, { recursive: true })

  // Full HD quality
  console.log(`  Encoding MP4: ${name}.mp4`)
  execSync(
    `"${ffmpegPath}" -y -r ${fps} -i "${webmPath}" ` +
    `-c:v libx264 -preset medium -crf 22 -pix_fmt yuv420p ` +
    `-movflags +faststart ` +
    `-an "${mp4Output}"`,
    { stdio: 'inherit' }
  )

  // Fast preview (540p, smaller file for instant loading)
  console.log(`  Encoding fast preview: ${name}-fast.mp4`)
  execSync(
    `"${ffmpegPath}" -y -r ${fps} -i "${webmPath}" ` +
    `-vf scale=960:540 ` +
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
): { mp4: string; fast: string } {
  return encodeFrames({
    webmPath,
    outputDir,
    name: sceneName,
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
