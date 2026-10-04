/**
 * Which code points the brand fonts really draw. Google's subset files do not cover
 * their whole declared unicode-range: JetBrains Mono latin-ext maps no Ḫ, Ḥ, Ṣ or Ṭ,
 * its latin file no U+2011 or ‰. Chrome draws a character the matching face lacks in the
 * next family of the stack and at last in a Windows system font, without an error. So
 * src/theme/glyphs.ts DRAWABLE comes from the woff2 files fonts.ts loads (each file's
 * cmap, read with Node's own brotli), never from their unicode-range alone:
 * test/glyphs.test.ts recomputes it and fails on drift, `npx tsx scripts/glyphs.ts`
 * (cwd video/) prints the constant.
 */
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { brotliDecompressSync } from 'node:zlib'

import { BODY, FONTS, HEADING, SERIF } from '../src/theme/fonts'
import { parseUnicodeRange } from '../src/theme/glyphs'

/** The site's public dir: `npm run studio` serves it, plan C's render step links its fonts/*.woff2. */
export const SITE_PUBLIC_DIR = fileURLToPath(new URL('../../ancient-nerds-map/public/', import.meta.url))

/** Tab, line feed and carriage return: CSS lays them out as white space or a line break, never as a glyph. */
const LAYOUT_WHITESPACE = [0x09, 0x0a, 0x0d]

// Indices in the WOFF2 known-table-tag list (WOFF2 spec 5.1); 63 means a four-byte tag follows.
const KNOWN_CMAP = 0
const KNOWN_GLYF = 10
const KNOWN_LOCA = 11
const ARBITRARY_TAG = 63

/** A WOFF2 UIntBase128 at `at.pos` (WOFF2 spec 4.1), advancing `at.pos`. */
function uintBase128(data: Buffer, at: { pos: number }): number {
  let value = 0
  for (let i = 0; i < 5; i++) {
    const byte = data[at.pos++]
    if (i === 0 && byte === 0x80) throw new Error('WOFF2 UIntBase128 with a leading zero byte')
    if (value > 0x1ffffff) throw new Error('WOFF2 UIntBase128 exceeds 32 bits')
    value = value * 128 + (byte & 0x7f)
    if ((byte & 0x80) === 0) return value
  }
  throw new Error('WOFF2 UIntBase128 longer than five bytes')
}

/**
 * The cmap table of a WOFF2 file: the table directory lists every table with its length,
 * then one brotli stream holds the tables in directory order without padding (WOFF2 spec 5).
 * glyf and loca are transformed unless their version is 3, any other table when its version
 * is not 0; cmap never is.
 */
function woff2CmapTable(path: string): Buffer {
  const file = readFileSync(path)
  if (file.toString('latin1', 0, 4) !== 'wOF2') throw new Error(`${path}: not a WOFF2 file`)
  if (file.toString('latin1', 4, 8) === 'ttcf') throw new Error(`${path}: a font collection, not a single font`)
  const numTables = file.readUInt16BE(12)
  const compressedLength = file.readUInt32BE(20)
  const at = { pos: 48 }
  let offset = 0
  let cmap: { offset: number; length: number } | undefined
  for (let i = 0; i < numTables; i++) {
    const flags = file[at.pos++]
    const known = flags & 0x3f
    const version = flags >> 6
    let tag = ''
    if (known === ARBITRARY_TAG) {
      tag = file.toString('latin1', at.pos, at.pos + 4)
      at.pos += 4
    }
    const origLength = uintBase128(file, at)
    const glyfOrLoca = known === KNOWN_GLYF || known === KNOWN_LOCA || tag === 'glyf' || tag === 'loca'
    const transformed = glyfOrLoca ? version !== 3 : version !== 0
    const length = transformed ? uintBase128(file, at) : origLength
    if (known === KNOWN_CMAP || tag === 'cmap') {
      if (transformed) throw new Error(`${path}: a transformed cmap table (version ${version})`)
      cmap = { offset, length }
    }
    offset += length
  }
  if (cmap === undefined) throw new Error(`${path}: no cmap table`)
  const tables = brotliDecompressSync(file.subarray(at.pos, at.pos + compressedLength))
  return tables.subarray(cmap.offset, cmap.offset + cmap.length)
}

/** Unicode cmap subtables (platform/encoding) in the order fontTools' getBestCmap prefers them. */
const UNICODE_SUBTABLES = ['3/10', '0/4', '3/1', '0/3']

/** Every code point a woff2 font file maps to a glyph other than .notdef (cmap formats 4 and 12). */
export function woff2Cmap(path: string): Set<number> {
  const cmap = woff2CmapTable(path)
  const records = new Map<string, number>()
  for (let i = 0; i < cmap.readUInt16BE(2); i++) {
    const rec = 4 + i * 8
    records.set(`${cmap.readUInt16BE(rec)}/${cmap.readUInt16BE(rec + 2)}`, cmap.readUInt32BE(rec + 4))
  }
  const key = UNICODE_SUBTABLES.find((k) => records.has(k))
  if (key === undefined) throw new Error(`${path}: no Unicode cmap subtable (${[...records.keys()].join(', ')})`)
  const at = records.get(key) as number
  const format = cmap.readUInt16BE(at)
  const points = new Set<number>()
  if (format === 4) {
    const segX2 = cmap.readUInt16BE(at + 6)
    const ends = at + 14
    const starts = ends + segX2 + 2
    const deltas = starts + segX2
    const rangeOffsets = deltas + segX2
    for (let s = 0; s < segX2; s += 2) {
      const start = cmap.readUInt16BE(starts + s)
      const end = cmap.readUInt16BE(ends + s)
      const delta = cmap.readUInt16BE(deltas + s)
      const rangeOffset = cmap.readUInt16BE(rangeOffsets + s)
      // U+FFFF only closes the segment list, it is never a character of the font
      for (let c = start; c <= end && c !== 0xffff; c++) {
        const indexed = rangeOffset === 0 ? c : cmap.readUInt16BE(rangeOffsets + s + rangeOffset + 2 * (c - start))
        const glyph = rangeOffset !== 0 && indexed === 0 ? 0 : (indexed + delta) & 0xffff
        if (glyph !== 0) points.add(c)
      }
    }
  } else if (format === 12) {
    const groups = cmap.readUInt32BE(at + 12)
    for (let g = 0; g < groups; g++) {
      const rec = at + 16 + g * 12
      const start = cmap.readUInt32BE(rec)
      const startGlyph = cmap.readUInt32BE(rec + 8)
      for (let c = start; c <= cmap.readUInt32BE(rec + 4); c++) if (startGlyph + c - start !== 0) points.add(c)
    }
  } else {
    throw new Error(`${path}: cmap subtable ${key} has format ${format}, only formats 4 and 12 are read`)
  }
  return points
}

function intersect(sets: Set<number>[]): Set<number> {
  const [first, ...rest] = sets
  return new Set([...first].filter((cp) => rest.every((set) => set.has(cp))))
}

/** The families a CSS font stack names, in order; the generic family at its end is the system font the glyph rule keeps text out of. */
function stackFamilies(stack: string): string[] {
  return stack
    .split(',')
    .map((family) => family.trim())
    .filter((family) => family.startsWith("'"))
    .map((family) => family.slice(1, -1))
}

/**
 * What one family draws at every weight fonts.ts loads for it: per weight, the union of its
 * faces' cmaps, each limited to the face's unicode-range (Chrome tries a face only for a
 * character inside its range); across weights, the common part.
 */
function familyCodePoints(family: string): Set<number> {
  const faces = FONTS.filter((face) => face.family === family)
  if (faces.length === 0) throw new Error(`fonts.ts FONTS loads no face of '${family}'`)
  const weights = [...new Set(faces.map((face) => face.weight))]
  return intersect(
    weights.map((weight) => {
      const points = new Set<number>()
      for (const face of faces.filter((f) => f.weight === weight)) {
        const ranges = parseUnicodeRange(face.unicodeRange)
        for (const cp of woff2Cmap(join(SITE_PUBLIC_DIR, face.file))) {
          if (ranges.some(([first, last]) => cp >= first && cp <= last)) points.add(cp)
        }
      }
      return points
    }),
  )
}

/**
 * The code points every stack of type.ts (HEADING for heading(), BODY for body() and hud(),
 * SERIF for serif()) draws with a loaded brand face, plus the layout white space.
 */
export function drawableCodePoints(): Set<number> {
  const stacks = [HEADING, BODY, SERIF].map((stack) => {
    const points = new Set<number>()
    for (const family of stackFamilies(stack)) for (const cp of familyCodePoints(family)) points.add(cp)
    return points
  })
  return new Set([...intersect(stacks), ...LAYOUT_WHITESPACE])
}

const hex = (cp: number) => cp.toString(16).toUpperCase().padStart(4, '0')

/** Code points as a CSS unicode-range ("U+0020-007E, U+00A0"), ascending, consecutive ones merged. */
export function formatUnicodeRange(points: Iterable<number>): string {
  const runs: [number, number][] = []
  for (const cp of [...new Set(points)].sort((a, b) => a - b)) {
    const last = runs[runs.length - 1]
    if (last !== undefined && last[1] === cp - 1) last[1] = cp
    else runs.push([cp, cp])
  }
  return runs.map(([first, last]) => (first === last ? `U+${hex(first)}` : `U+${hex(first)}-${hex(last)}`)).join(', ')
}

/** DRAWABLE of src/theme/glyphs.ts as the brand font files define it today. */
export const drawableRange = (): string => formatUnicodeRange(drawableCodePoints())
