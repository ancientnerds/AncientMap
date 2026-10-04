import { join } from 'node:path'

import { describe, expect, it } from 'vitest'

import { SITE_PUBLIC_DIR, drawableRange, formatUnicodeRange, woff2Cmap } from '../scripts/fontCoverage'
import { FONTS, FONT_FILES, HEADING } from '../src/theme/fonts'
import { DRAWABLE, LATIN_EXT_RANGE, LATIN_RANGE, glyphReason, parseUnicodeRange, unsupportedChar } from '../src/theme/glyphs'

const cmap = (file: string) => woff2Cmap(join(SITE_PUBLIC_DIR, 'fonts', file))

describe('the brand fonts draw only the code points their files map (DRAWABLE)', () => {
  it('parses and formats a CSS unicode-range', () => {
    expect(parseUnicodeRange('U+0000-00FF, U+0131, U+A720-A7FF')).toEqual([
      [0x0, 0xff],
      [0x131, 0x131],
      [0xa720, 0xa7ff],
    ])
    expect(formatUnicodeRange([0x131, 0x20, 0x21, 0x22, 0xa0])).toBe('U+0020-0022, U+00A0, U+0131')
  })
  it('reads each woff2 cmap as fontTools 4.65 does (glyph counts measured 2026-09-27)', () => {
    const counts = Object.fromEntries(FONT_FILES.map((file) => [file, cmap(file.slice('fonts/'.length)).size]))
    expect(counts).toEqual({
      'fonts/orbitron-600.woff2': 183,
      'fonts/orbitron-700.woff2': 183,
      'fonts/jetbrains-mono-400.woff2': 229,
      'fonts/jetbrains-mono-400-latin-ext.woff2': 190,
      'fonts/jetbrains-mono-500.woff2': 229,
      'fonts/cormorant-garamond-400-latin.woff2': 229,
      'fonts/cormorant-garamond-400-latin-ext.woff2': 306,
    })
    // the gaps Google's subsets leave in their declared range: ẞ is there, Ḫ and the non-breaking hyphen are not
    expect(cmap('jetbrains-mono-400-latin-ext.woff2').has(0x1e9e)).toBe(true)
    expect(cmap('jetbrains-mono-400-latin-ext.woff2').has(0x1e2a)).toBe(false)
    expect(cmap('jetbrains-mono-400.woff2').has(0x2011)).toBe(false)
    expect(cmap('cormorant-garamond-400-latin-ext.woff2').has(0x1e2a)).toBe(true)
  })
  it('DRAWABLE is what the loaded files map, recomputed from ancient-nerds-map/public/fonts (npx tsx scripts/glyphs.ts prints it)', () => {
    expect(DRAWABLE).toBe(drawableRange())
  })
  it('accepts the transliterations the files map and layout white space', () => {
    for (const text of ['Vinča', 'Enūma Eliš', 'Mahābhārata', 'Çatalhöyük', 'Şanlıurfa', 'Ħal Saflieni', 'ÿ ß ſ ŉ', '1,000–1,650 t × 2 — “quoted” …', 'one\ntwo\tthree'])
      expect(unsupportedChar(text), text).toBeNull()
  })
  it('refuses other scripts, the gaps of the subsets and letters whose upper case leaves the fonts', () => {
    expect(unsupportedChar('Κνωσός')).toBe('Κ')
    expect(unsupportedChar('Baalbek → Rome')).toBe('→')
    // inside the declared latin-ext and latin ranges, but in no loaded file: a system font would draw them
    expect(unsupportedChar('Ḫattuša')).toBe('Ḫ')
    expect(unsupportedChar('Kṛṣṇa')).toBe('ṛ')
    expect(unsupportedChar('Ḥatḥor')).toBe('Ḥ')
    expect(unsupportedChar('Baʿal')).toBe('ʿ')
    expect(unsupportedChar('non‑breaking')).toBe('‑')
    expect(unsupportedChar('5‰')).toBe('‰')
    expect(unsupportedChar('Smaller than 1 µm?')).toBe('µ')
    expect(unsupportedChar('ẖ')).toBe('ẖ')
    // heading() and hud() draw upper case: "ƒ" becomes "Ƒ", which no loaded file maps
    expect(unsupportedChar('ƒ')).toBe('ƒ')
    expect(glyphReason('ƒ')).toBe('"ƒ" (U+0192) draws as "Ƒ" (U+0191) in upper case, which has no glyph in the brand fonts (latin and latin-ext only)')
    expect(glyphReason('Ḫ')).toBe('"Ḫ" (U+1E2A) has no glyph in the brand fonts (latin and latin-ext only)')
    expect(glyphReason('Κ')).toBe('"Κ" (U+039A) has no glyph in the brand fonts (latin and latin-ext only)')
  })
  it('loads a latin-ext file next to the latin files of JetBrains Mono and Cormorant Garamond', () => {
    const faces = (range: string) =>
      FONTS.filter((f) => f.unicodeRange === range)
        .map((f) => `${f.family} ${f.weight}`)
        .sort()
    expect(faces(LATIN_EXT_RANGE)).toEqual(['Cormorant Garamond 400', 'JetBrains Mono 400', 'JetBrains Mono 500'])
    expect(faces(LATIN_RANGE)).toEqual(['Cormorant Garamond 400', 'JetBrains Mono 400', 'JetBrains Mono 500', 'Orbitron 600', 'Orbitron 700'])
    expect(FONT_FILES).toHaveLength(7)
    // Orbitron has no latin-ext file: a heading falls back per character to JetBrains Mono, whose files DRAWABLE reflects
    expect(HEADING.split(',')[1].trim()).toBe("'JetBrains Mono'")
  })
})
