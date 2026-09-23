/**
 * One source of truth for every vector layer URL: the loader, the background tiers and the
 * offline download all resolve through config/vectorLayers.ts, so offline mode (an exact-URL
 * Cache API match) finds byte-identical keys. The coastline and border tiers come from the
 * manifest scripts/build_globe_layers.py writes (content-hashed file names, contract C1).
 */

import { existsSync, readdirSync, readFileSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

import { describe, expect, it } from 'vitest'

import manifest from '../../data/globeLayers.generated.json'
import { DETAIL_SCALE, type DetailLevel } from '../globeConstants'
import {
  GLOBE_LAYER_KEYS,
  LAYER_CONFIG,
  getGlobeLayerUrl,
  getLayerFiles,
  getLayerUrl,
  tierRank,
  type VectorLayerKey,
} from '../vectorLayers'

const HERE = dirname(fileURLToPath(import.meta.url))
const SRC = resolve(HERE, '../..')
const REPO_PUBLIC = resolve(SRC, '../../public')
const DETAILS = Object.keys(DETAIL_SCALE) as DetailLevel[]
const KEYS = Object.keys(LAYER_CONFIG) as VectorLayerKey[]

describe('globe layer tiers', () => {
  it('resolve start and detail from the generated manifest', () => {
    expect(getGlobeLayerUrl('coastlines', 'start')).toBe(manifest.coastlines.start)
    expect(getGlobeLayerUrl('coastlines', 'detail')).toBe(manifest.coastlines.detail)
    expect(getGlobeLayerUrl('countryBorders', 'start')).toBe(manifest.countryBorders.start)
    expect(getGlobeLayerUrl('countryBorders', 'detail')).toBe(manifest.countryBorders.detail)
  })

  it('reach coast_hires only through the coastline hires tier', () => {
    expect(getGlobeLayerUrl('coastlines', 'hires')).toBe('/data/layers/coast_hires.geojson')
    expect(() => getGlobeLayerUrl('countryBorders', 'hires')).toThrow(/countryBorders/)
    for (const key of KEYS) {
      for (const detail of DETAILS) expect(getLayerUrl(key, detail)).not.toMatch(/coast_hires/)
    }
  })

  it('start every globe layer at its start tier, whatever the zoom', () => {
    for (const key of GLOBE_LAYER_KEYS) {
      for (const detail of DETAILS) expect(getLayerUrl(key, detail)).toBe(getGlobeLayerUrl(key, 'start'))
    }
  })

  it('carry no cache-busting query: the file name is the version', () => {
    for (const key of GLOBE_LAYER_KEYS) {
      expect(getGlobeLayerUrl(key, 'start')).not.toContain('?')
      expect(getGlobeLayerUrl(key, 'detail')).not.toContain('?')
    }
  })

  it('rank start < detail < hires, and nothing below start', () => {
    expect(tierRank(null)).toBeLessThan(tierRank('start'))
    expect(tierRank('start')).toBeLessThan(tierRank('detail'))
    expect(tierRank('detail')).toBeLessThan(tierRank('hires'))
  })
})

describe('LOD layers', () => {
  it('never ask for a _hires file (rivers_hires and lakes_hires are too large; the others do not exist)', () => {
    for (const key of KEYS) {
      const config = LAYER_CONFIG[key]
      if (!('hasLOD' in config && config.hasLOD)) continue
      for (const detail of DETAILS) expect(getLayerUrl(key, detail)).not.toMatch(/_hires/)
    }
    expect(getLayerUrl('rivers', 'ultra-low')).toBe('/data/layers/ne_110m_rivers.geojson')
    expect(getLayerUrl('lakes', 'high')).toBe('/data/layers/ne_10m_lakes.geojson')
  })
})

describe('getLayerFiles', () => {
  it('lists every URL the loader can request for a layer, once', () => {
    for (const key of KEYS) {
      const files = getLayerFiles(key)
      expect(new Set(files).size).toBe(files.length)
      for (const detail of DETAILS) expect(files).toContain(getLayerUrl(key, detail))
    }
    expect(getLayerFiles('coastlines')).toEqual([
      manifest.coastlines.start, manifest.coastlines.detail, '/data/layers/coast_hires.geojson',
    ])
    expect(getLayerFiles('countryBorders')).toEqual([manifest.countryBorders.start, manifest.countryBorders.detail])
    expect(getLayerFiles('plateBoundaries')).toContain('/data/layers/tectonic_plate_labels.geojson')
    expect(getLayerFiles('glaciers')).toContain('/data/layers/glacier_labels.geojson')
    expect(getLayerFiles('coralReefs')).toContain('/data/layers/coral_reef_labels.geojson')
  })

  it('names only files that exist in the repository', () => {
    for (const key of KEYS) {
      for (const url of getLayerFiles(key)) {
        expect(url.startsWith('/data/layers/'), url).toBe(true)
        expect(existsSync(join(REPO_PUBLIC, url)), url).toBe(true)
      }
    }
  })
})

describe('config and services', () => {
  it('reference no Natural Earth file on GitHub any more', () => {
    for (const dir of ['config', 'services']) {
      for (const name of readdirSync(join(SRC, dir))) {
        if (!/\.tsx?$/.test(name)) continue
        expect(readFileSync(join(SRC, dir, name), 'utf8'), `${dir}/${name}`).not.toContain('raw.githubusercontent.com')
      }
    }
  })
})
