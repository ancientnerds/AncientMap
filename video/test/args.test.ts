import path from 'node:path'

import { describe, expect, it } from 'vitest'

import { VIOLATION_TYPE, violationLine } from '../src/layout/LayoutGuard'
import { VIOLATION_PREFIX, bundleDir, chunkRanges, concatList, nvencOverride, nvidiaProblem, parseFlags, parseViolation, progressPrinter } from '../scripts/args'

const spec = {
  timeline: { required: true, kind: 'path' as const },
  every: { required: false, kind: 'int' as const },
  scale: { required: false, kind: 'number' as const },
}

describe('parseFlags', () => {
  it('parses paths absolute and numbers typed', () => {
    expect(parseFlags(['--timeline', 't.json', '--every', '6', '--scale', '0.5'], spec)).toEqual({
      timeline: path.resolve('t.json'),
      every: 6,
      scale: 0.5,
    })
  })
  it.each([
    [['--every', '6'], /missing required flag --timeline/],
    [['--timeline'], /--timeline needs a value/],
    [['--timeline', 't.json', '--bogus', '1'], /unknown flag --bogus/],
    [['--timeline', 't.json', '--every', '1.5'], /--every must be a non-negative integer/],
    [['--timeline', 't.json', '--scale', '0'], /--scale must be a positive number/],
    [['t.json'], /unexpected argument "t\.json"/],
  ])('rejects %j', (argv, message) => {
    expect(() => parseFlags(argv, spec)).toThrow(message)
  })
})

describe('chunkRanges', () => {
  it('covers every frame exactly once', () => {
    expect(chunkRanges(600, 300)).toEqual([
      [0, 299],
      [300, 599],
    ])
    expect(chunkRanges(601, 300)).toEqual([
      [0, 299],
      [300, 599],
      [600, 600],
    ])
    expect(chunkRanges(100, 3600)).toEqual([[0, 99]])
  })
})

describe('parseViolation', () => {
  it('reads LayoutGuard lines and ignores every other log line', () => {
    expect(VIOLATION_PREFIX).toBe(`{"type":"${VIOLATION_TYPE}"`)
    const line = violationLine(12, { a: 'captions', b: 'b01:lt', reason: 'overlap' })
    expect(parseViolation(line)).toEqual({ type: 'layout-violation', frame: 12, a: 'captions', b: 'b01:lt', reason: 'overlap' })
    expect(parseViolation('Warning: something else')).toBeNull()
  })
})

describe('the GPU rule (spec 4.11)', () => {
  it('accepts only a render browser on the NVIDIA', () => {
    expect(nvidiaProblem('ANGLE (NVIDIA, NVIDIA GeForce RTX 3080 Laptop GPU (0x0000249C) Direct3D11 vs_5_0 ps_5_0, D3D11)')).toBeNull()
    for (const other of [
      'ANGLE (AMD, AMD Radeon(TM) Graphics (0x00001681) Direct3D11 vs_5_0 ps_5_0, D3D11)',
      'ANGLE (Google, Vulkan 1.3.0 (SwiftShader Device (Subzero) (0x0000C0DE)), SwiftShader driver)',
      'ANGLE (Microsoft, Microsoft Basic Render Driver (0x0000008C) Direct3D11 vs_5_0 ps_5_0, D3D11)',
      '',
    ]) {
      expect(nvidiaProblem(other)).toMatch(/not the NVIDIA GPU/)
    }
  })
  it('pins h264_nvenc to GPU 0 without B-frames, passes stream copies and refuses software encoders', () => {
    const pre = ['-r', '60', '-i', '-', '-c:v', 'h264_nvenc', '-pix_fmt', 'yuv420p', '-b:v', '16M', 'out.mp4']
    expect(nvencOverride({ type: 'pre-stitcher', args: pre })).toEqual(['-r', '60', '-i', '-', '-c:v', 'h264_nvenc', '-gpu', '0', '-bf', '0', '-pix_fmt', 'yuv420p', '-b:v', '16M', 'out.mp4'])
    const copy = ['-i', 'pre.mp4', '-c:v', 'copy', 'out.mp4']
    expect(nvencOverride({ type: 'stitcher', args: copy })).toEqual(copy)
    expect(nvencOverride({ type: 'stitcher', args: ['-i', 'a.wav', 'b.aac'] })).toEqual(['-i', 'a.wav', 'b.aac'])
    expect(() => nvencOverride({ type: 'pre-stitcher', args: ['-c:v', 'libx264', 'out.mp4'] })).toThrow(/only h264_nvenc is allowed/)
  })
})

describe('concatList', () => {
  it('lists the chunks for the ffmpeg concat demuxer, forward slashes and quotes escaped', () => {
    const windows = ['C:', 'ep', 'render', 'raw.mp4.parts', 'video-000.mp4'].join('\\')
    expect(concatList([windows, "C:/it's/video-001.mp4"])).toBe(["file 'C:/ep/render/raw.mp4.parts/video-000.mp4'", "file 'C:/it'\\''s/video-001.mp4'", ''].join('\n'))
  })
})

describe('progressPrinter', () => {
  it('prints each step once, however often progress is reported', () => {
    const lines: string[] = []
    const report = progressPrinter('render', 25, (l) => lines.push(l))
    for (const f of [0, 0.1, 0.1, 0.3, 0.8, 1]) report(f)
    expect(lines).toEqual(['render 0%', 'render 25%', 'render 50%', 'render 75%', 'render 100%'])
  })
})

describe('bundleDir', () => {
  it('bundles next to the public dir (the episode drive), never into the system temp dir', () => {
    expect(bundleDir(path.join('ep', 'render', 'public'))).toBe(path.resolve('ep', 'render', 'bundle'))
  })
})
