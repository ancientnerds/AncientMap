/**
 * ffmpeg encoding utility.
 * Converts captured PNG frames into MP4 (H.264) videos.
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
  framesDir: string
  prefix?: string
  fps?: number
  outputDir: string
  name: string
}

/**
 * Encode frames to MP4 (H.264) with near-lossless quality.
 * Also produces a fast preview version (540p, CRF 30) for progressive loading.
 */
export function encodeFrames(options: EncodeOptions): { mp4: string; fast: string } {
  const {
    framesDir,
    prefix = 'frame',
    fps = 24,
    outputDir,
    name,
  } = options

  const inputPattern = join(framesDir, `${prefix}_%06d.png`)
  const mp4Output = join(outputDir, `${name}.mp4`)
  const fastOutput = join(outputDir, `${name}-fast.mp4`)

  mkdirSync(outputDir, { recursive: true })

  // Full HD quality
  console.log(`  Encoding MP4: ${name}.mp4`)
  execSync(
    `"${ffmpegPath}" -y -framerate ${fps} -i "${inputPattern}" ` +
    `-c:v libx264 -preset medium -crf 22 -pix_fmt yuv420p ` +
    `-movflags +faststart ` +
    `-an "${mp4Output}"`,
    { stdio: 'inherit' }
  )

  // Fast preview (540p, smaller file for instant loading)
  console.log(`  Encoding fast preview: ${name}-fast.mp4`)
  execSync(
    `"${ffmpegPath}" -y -framerate ${fps} -i "${inputPattern}" ` +
    `-vf scale=960:540 ` +
    `-c:v libx264 -preset fast -crf 30 -pix_fmt yuv420p ` +
    `-movflags +faststart ` +
    `-an "${fastOutput}"`,
    { stdio: 'inherit' }
  )

  return { mp4: mp4Output, fast: fastOutput }
}

/**
 * Encode a single scene's frames.
 */
export function encodeScene(
  sceneName: string,
  framesDir: string,
  outputDir: string,
  _resolution: 'hero' | 'section' | 'tool' = 'section'
): { mp4: string; fast: string } {
  return encodeFrames({
    framesDir,
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
  const framesBase = join(__dirname, '..', 'output', 'frames')
  const outputDir = join(__dirname, '..', '..', 'public', 'landing', 'video')

  const scenes = [
    { name: 'hero',           resolution: 'hero' as const },
    { name: 'globe-overview', resolution: 'section' as const },
    { name: 'filters',        resolution: 'section' as const },
    { name: 'empires',        resolution: 'section' as const },
    { name: 'search',         resolution: 'tool' as const },
    { name: 'proximity',      resolution: 'tool' as const },
    { name: 'measure',        resolution: 'tool' as const },
    { name: 'map-layers',     resolution: 'tool' as const },
    { name: 'paleoshoreline',  resolution: 'tool' as const },
  ]

  for (const scene of scenes) {
    const sceneFramesDir = join(framesBase, scene.name)
    if (!existsSync(sceneFramesDir)) {
      console.log(`  Skipping ${scene.name} (no frames found)`)
      continue
    }

    console.log(`\nEncoding ${scene.name}...`)
    const result = encodeScene(scene.name, sceneFramesDir, outputDir, scene.resolution)
    console.log(`  -> ${result.mp4}`)
    console.log(`  -> ${result.fast}`)
  }

  console.log('\nAll scenes encoded.')
}
