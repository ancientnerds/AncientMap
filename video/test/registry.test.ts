import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

import { describe, expect, it } from 'vitest'

import { CAPTURE_PROPS, REGISTRY_BLOCKS, registryJson } from '../src/blocks/schemas'
import { type Schema, unsupportedKeywords } from '../src/schema'

const REGISTRY_FILE = fileURLToPath(new URL('../src/blocks/registry.json', import.meta.url))

/** The schema a `drawn` pattern points at ('claims[].label': the label of every claim), or null. */
function schemaAt(schema: Schema, pattern: string): Schema | null {
  let at: Schema | undefined = schema
  for (const part of pattern.split('.')) {
    const key = part.endsWith('[]') ? part.slice(0, -2) : part
    at = at?.properties?.[key]
    if (at && part.endsWith('[]')) at = at.type === 'array' ? at.items : undefined
  }
  return at ?? null
}

/** Every property name anywhere in a schema. */
function propertyNames(schema: Schema): string[] {
  const own = Object.entries(schema.properties ?? {}).flatMap(([k, v]) => [k, ...propertyNames(v)])
  return schema.items ? [...own, ...propertyNames(schema.items)] : own
}

describe('blocks/registry.json (plan C contract C5)', () => {
  it('is exactly what `npm run registry` writes from schemas.ts', () => {
    expect(readFileSync(REGISTRY_FILE, 'utf-8').replace(/\r\n/g, '\n')).toBe(registryJson())
  })
  it('is {"blocks": {name: {map, platform, drawn, props}}} and nothing else', () => {
    const data = JSON.parse(readFileSync(REGISTRY_FILE, 'utf-8'))
    expect(Object.keys(data)).toEqual(['blocks'])
    for (const [name, entry] of Object.entries(data.blocks as Record<string, Record<string, unknown>>)) {
      expect(Object.keys(entry).sort(), name).toEqual(['drawn', 'map', 'platform', 'props'])
      expect(typeof entry.map, name).toBe('boolean')
      expect(typeof entry.platform, name).toBe('boolean')
      expect((entry.props as { type: string }).type, name).toBe('object')
      expect(Array.isArray(entry.drawn), name).toBe(true)
      for (const pattern of entry.drawn as unknown[]) expect(typeof pattern === 'string' && pattern.length > 0, name).toBe(true)
    }
  })
  it('lists the scene blocks of the four topic types', () => {
    expect(Object.keys(REGISTRY_BLOCKS).sort()).toEqual([
      'BarChart',
      'ClaimBoard',
      'Diagram',
      'EvidenceCard',
      'GlobeShot',
      'ListCard',
      'MapboxFlyover',
      'MapboxTopdown',
      'Meter',
      'PhotoPlate',
      'PlatformClip',
      'QuoteCard',
      'ScaleDrawing',
      'ScaleZoom',
      'ShareCard',
      'SourceViewer',
      'Timeline',
      'UnitGrid',
    ])
  })
  it('has no title card and no agent or character block (owner rules)', () => {
    for (const name of Object.keys(REGISTRY_BLOCKS)) expect(name).not.toMatch(/title|agent|character|avatar|presenter|host/i)
  })
  it('marks PlatformClip as the platform moment and the map blocks as map content', () => {
    const flagged = (key: 'map' | 'platform') =>
      Object.entries(REGISTRY_BLOCKS)
        .filter(([, e]) => e[key])
        .map(([n]) => n)
        .sort()
    expect(flagged('platform')).toEqual(['PlatformClip'])
    expect(flagged('map')).toEqual(['MapboxFlyover', 'MapboxTopdown', 'PlatformClip'])
  })
  it('uses only the JSON-schema keywords pipeline/studio/blocks.py supports', () => {
    for (const [name, entry] of Object.entries(REGISTRY_BLOCKS)) expect(unsupportedKeywords(entry.props), name).toEqual([])
  })
  it('makes every comparison block state its basis (owner rule)', () => {
    for (const name of ['ScaleDrawing', 'UnitGrid', 'BarChart', 'ScaleZoom']) expect(REGISTRY_BLOCKS[name].props.required, name).toContain('basis')
  })
  it('draws linear scales only: no block has a scale prop or a log axis (owner decision 31)', () => {
    for (const [name, entry] of Object.entries(REGISTRY_BLOCKS)) expect(propertyNames(entry.props), name).not.toContain('scale')
    expect(registryJson()).not.toMatch(/log10|logarithm/i)
  })
  it('points every drawn pattern at a string prop, never into a capture (owner decision 32)', () => {
    for (const [name, entry] of Object.entries(REGISTRY_BLOCKS)) {
      for (const pattern of entry.drawn) {
        expect(schemaAt(entry.props, pattern)?.type, `${name}: ${pattern}`).toBe('string')
        expect((CAPTURE_PROPS as readonly string[]).includes(pattern.split('.')[0]), `${name}: ${pattern}`).toBe(false)
      }
    }
    // blocks/index.ts captureStrings() walks the capture props: they are exactly the props with a capture schema
    const captures = Object.values(REGISTRY_BLOCKS).flatMap((e) =>
      Object.entries(e.props.properties ?? {})
        .filter(([, s]) => s.properties?.events !== undefined)
        .map(([k]) => k),
    )
    expect([...new Set(captures)].sort()).toEqual([...CAPTURE_PROPS].sort())
  })
})
