/**
 * Guard: mapbox-gl (463 kB gzip) must never be part of the static import graph
 * of the globe entry or the site entry. Mapbox is loaded on demand through
 * `import('./MapboxGlobeService')` in mapboxLoader.ts, and EmpireMinimap is a
 * React.lazy chunk. A single value import anywhere on the way pulls the whole
 * library back into the entry (Rollup keeps a module static when it is
 * imported both statically and dynamically), and size-limit cannot see it
 * because mapbox-gl sits in its own shared chunk.
 *
 * The walker follows `import … from`, `export … from` and side-effect
 * imports, skips `import type` / `export type` and specifier lists made of
 * `type X` entries only, and resolves relative paths to .ts/.tsx/index files.
 * Dynamic `import()` is not followed: it is exactly the lazy edge we want.
 */

import { existsSync, readFileSync, statSync } from 'node:fs'
import { dirname, join, relative, resolve, sep } from 'node:path'
import { fileURLToPath } from 'node:url'

import { describe, expect, it } from 'vitest'

const SRC = resolve(dirname(fileURLToPath(import.meta.url)), '../..')

const FROM_RE = /^[ \t]*(import|export)\s+(type\s+)?([^'"`;]*?)\s*from\s*['"]([^'"]+)['"]/gm
const SIDE_EFFECT_RE = /^[ \t]*import\s*['"]([^'"]+)['"]/gm

function isTypeOnlyClause(clause: string): boolean {
  const braces = clause.match(/^\{([\s\S]*)\}$/)
  if (!braces) return false
  const names = braces[1].split(',').map(s => s.trim()).filter(Boolean)
  return names.length > 0 && names.every(n => n.startsWith('type '))
}

/** Value-import specifiers of one module (type-only imports removed). */
function valueSpecifiers(source: string): string[] {
  const out: string[] = []
  for (const m of source.matchAll(FROM_RE)) {
    const [, , typeKeyword, clause, spec] = m
    if (typeKeyword) continue
    if (isTypeOnlyClause(clause.trim())) continue
    out.push(spec)
  }
  for (const m of source.matchAll(SIDE_EFFECT_RE)) out.push(m[1])
  return out
}

function resolveRelative(fromFile: string, spec: string): string {
  const base = resolve(dirname(fromFile), spec)
  const candidates = [base, `${base}.ts`, `${base}.tsx`, join(base, 'index.ts'), join(base, 'index.tsx')]
  for (const c of candidates) {
    if (existsSync(c) && statSync(c).isFile()) return c
  }
  throw new Error(`Cannot resolve '${spec}' from ${relative(SRC, fromFile)}`)
}

const isMapbox = (spec: string) => spec === 'mapbox-gl' || spec.startsWith('mapbox-gl/')

/** Returns the import chain from `entry` to the first mapbox-gl import, or null. */
function chainToMapbox(entry: string): string[] | null {
  const parent = new Map<string, string | null>([[entry, null]])
  const queue = [entry]
  while (queue.length > 0) {
    const file = queue.shift()!
    if (!/\.tsx?$/.test(file)) continue
    for (const spec of valueSpecifiers(readFileSync(file, 'utf8'))) {
      if (isMapbox(spec)) {
        const chain = [spec]
        for (let f: string | null = file; f; f = parent.get(f) ?? null) chain.unshift(relative(SRC, f).split(sep).join('/'))
        return chain
      }
      if (!spec.startsWith('.')) continue
      const target = resolveRelative(file, spec)
      if (parent.has(target)) continue
      parent.set(target, file)
      queue.push(target)
    }
  }
  return null
}

describe('valueSpecifiers', () => {
  it('skips type-only imports and keeps value, mixed and side-effect imports', () => {
    const src = [
      "import type { A } from './typeOnly'",
      "import { type B, type C } from './allTypes'",
      "import { type D, e } from './mixed'",
      'import {',
      '  f,',
      '  g,',
      "} from './multiLine'",
      "export { h } from './reExport'",
      "export type { I } from './typeReExport'",
      "import 'side-effect.css'",
      "const lazy = import('./dynamic')",
    ].join('\n')
    expect(valueSpecifiers(src)).toEqual(['./mixed', './multiLine', './reExport', 'side-effect.css'])
  })
})

describe('mapbox-gl stays out of the static entry graphs', () => {
  it('the walker finds mapbox-gl when a value import reaches it', () => {
    // Positive control: the service itself imports mapbox-gl statically.
    expect(chainToMapbox(join(SRC, 'services/MapboxGlobeService.ts'))).toEqual([
      'services/MapboxGlobeService.ts',
      'mapbox-gl',
    ])
  })

  it('globe entry (src/main.tsx) never reaches mapbox-gl', () => {
    expect(chainToMapbox(join(SRC, 'main.tsx'))).toBeNull()
  })

  it('site entry (src/siteMain.tsx) never reaches mapbox-gl', () => {
    expect(chainToMapbox(join(SRC, 'siteMain.tsx'))).toBeNull()
  })
})
