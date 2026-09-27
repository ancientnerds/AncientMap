/**
 * Pure helpers of the node scripts (no Remotion imports; test/args.test.ts):
 * strict flag parsing, render chunk ranges, the lint violation lines
 * LayoutGuard writes to the browser console, progress reporting in steps, and
 * the two GPU rules of spec section 4.11: the render browser must draw on the
 * NVIDIA, and every video encode must be h264_nvenc on GPU 0.
 */
import path from 'node:path'

import { VIOLATION_TYPE } from '../src/layout/LayoutGuard'

export type FlagSpec = Record<string, { required: boolean; kind: 'path' | 'int' | 'number' | 'string' }>
export type Flags = Record<string, string | number>

/** Parse `--name value` pairs; unknown flags, missing values and missing required flags throw. */
export function parseFlags(argv: readonly string[], spec: FlagSpec): Flags {
  const out: Flags = {}
  for (let i = 0; i < argv.length; i++) {
    const arg = argv[i]
    if (!arg.startsWith('--')) throw new Error(`unexpected argument "${arg}"`)
    const name = arg.slice(2)
    const def = spec[name]
    if (!def) throw new Error(`unknown flag --${name} (known: ${Object.keys(spec).map((k) => `--${k}`).join(', ')})`)
    const value = argv[++i]
    if (value === undefined || value.startsWith('--')) throw new Error(`--${name} needs a value`)
    if (def.kind === 'int') {
      const n = Number(value)
      if (!Number.isInteger(n) || n < 0) throw new Error(`--${name} must be a non-negative integer, got "${value}"`)
      out[name] = n
    } else if (def.kind === 'number') {
      const n = Number(value)
      if (!Number.isFinite(n) || n <= 0) throw new Error(`--${name} must be a positive number, got "${value}"`)
      out[name] = n
    } else {
      out[name] = def.kind === 'path' ? path.resolve(value) : value
    }
  }
  for (const [name, def] of Object.entries(spec)) {
    if (def.required && !(name in out)) throw new Error(`missing required flag --${name}`)
  }
  return out
}

/** [start, end] inclusive frame ranges of at most `size` frames covering the episode. */
export function chunkRanges(durationInFrames: number, size: number): [number, number][] {
  if (size < 1) throw new Error('chunk size must be >= 1')
  const out: [number, number][] = []
  for (let s = 0; s < durationInFrames; s += size) out.push([s, Math.min(durationInFrames, s + size) - 1])
  return out
}

export const VIOLATION_PREFIX = `{"type":"${VIOLATION_TYPE}"`

export type LintViolation = { type: typeof VIOLATION_TYPE; frame: number; a: string; b: string | null; reason: string }

/** The violation carried by one browser console line, or null for any other log line. */
export function parseViolation(text: string): LintViolation | null {
  if (!text.startsWith(VIOLATION_PREFIX)) return null
  return JSON.parse(text) as LintViolation
}

/** A progress callback that prints "<label> NN%" once per `step` percent, one line each. */
export function progressPrinter(label: string, step = 10, write: (line: string) => void = (l) => console.log(l)): (fraction: number) => void {
  let next = 0
  return (fraction) => {
    const pct = Math.floor(fraction * 100)
    while (pct >= next && next <= 100) {
      write(`${label} ${next}%`)
      next += step
    }
  }
}

/** Renderer strings that are not the NVIDIA: the integrated AMD, software rasterisers, the fallback adapter. */
const NOT_NVIDIA = /AMD|Radeon|SwiftShader|Basic Render|llvmpipe|Intel/i

/** Why a WebGL renderer string (src/gpu.ts) is not the NVIDIA, or null when it is. */
export function nvidiaProblem(renderer: string): string | null {
  if (!/NVIDIA/.test(renderer) || NOT_NVIDIA.test(renderer)) {
    return `the render browser draws on "${renderer || 'no renderer'}", not the NVIDIA GPU (spec 4.11); run \`python -m pipeline.studio doctor\``
  }
  return null
}

export type FfmpegStep = { type: 'pre-stitcher' | 'stitcher'; args: string[] }

/**
 * Remotion's ffmpegOverride for every render: each video encode must be
 * h264_nvenc; it runs on GPU 0 (the NVIDIA, the only CUDA device) and without
 * B-frames, so render.ts can join its chunks by stream copy. Stream copies
 * pass; any other encoder is a software encode and fails the render.
 */
export function nvencOverride({ args }: FfmpegStep): string[] {
  const i = args.indexOf('-c:v')
  if (i < 0) return args
  const encoder = args[i + 1]
  if (encoder === 'copy') return args
  if (encoder !== 'h264_nvenc') throw new Error(`Remotion chose the video encoder "${encoder}"; only h264_nvenc is allowed (spec 4.11)`)
  return [...args.slice(0, i + 2), '-gpu', '0', '-bf', '0', ...args.slice(i + 2)]
}

/** The ffconcat list of the rendered chunks (forward slashes, quotes escaped). */
export function concatList(files: readonly string[]): string {
  return files.map((f) => `file '${f.replace(/\\/g, '/').replace(/'/g, "'\\''")}'`).join('\n') + '\n'
}

/**
 * Where a script bundles: `bundle/` next to the per-render public dir
 * (<episode>/render/bundle). Remotion's bundle() copies the whole public dir
 * into its output (on Windows always as a copy), so the default output in the
 * system temp dir would put a second copy of every capture on C: per script.
 */
export function bundleDir(publicDir: string): string {
  return path.join(path.dirname(path.resolve(publicDir)), 'bundle')
}
