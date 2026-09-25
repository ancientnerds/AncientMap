/**
 * How Globe wires the satellite state, which no render test reaches (Globe
 * needs WebGL, the data and the whole page). The active satellite (switched on
 * and loaded, satelliteReady) drives Mapbox's style, the page style and the
 * back layers and stays on through a context loss of the Three.js canvas; the
 * shader samples it only while its texture is on the GPU (satelliteOnGpu), so
 * a restore shows the gray until the satellite is back, not an empty texture.
 * useTextureLoading.test.tsx and useSatelliteMode.test.tsx prove the hooks.
 */

import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

import { describe, expect, it } from 'vitest'

const SRC = resolve(dirname(fileURLToPath(import.meta.url)), '../../..')
const globe = readFileSync(resolve(SRC, 'components/Globe.tsx'), 'utf-8')

describe('Globe: the satellite state', () => {
  it('counts the satellite as active once it is loaded, through a context loss', () => {
    expect(globe).toContain('const satelliteActive = requestedTileLayers.satellite && satelliteReady')
  })

  it('lets the shader sample it only while its texture is on the GPU', () => {
    expect(globe).toMatch(/useSatelliteMode\(\{\s*refs,\s*satellite: tileLayers\.satellite,\s*satelliteShown: tileLayers\.satellite && satelliteOnGpu,/)
  })
})
