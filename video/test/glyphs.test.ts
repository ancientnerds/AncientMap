import { describe, expect, it } from 'vitest'

import { FONTS, FONT_FILES, HEADING } from '../src/theme/fonts'
import { LATIN_EXT_RANGE, LATIN_RANGE, glyphReason, parseUnicodeRange, unsupportedChar } from '../src/theme/glyphs'

describe('the brand fonts cover latin and latin-ext (fonts.css unicode-range)', () => {
  it('parses a CSS unicode-range', () => {
    expect(parseUnicodeRange('U+0000-00FF, U+0131, U+A720-A7FF')).toEqual([
      [0x0, 0xff],
      [0x131, 0x131],
      [0xa720, 0xa7ff],
    ])
  })
  it('accepts the transliterations of type-D topics, refuses other scripts and letters whose upper case leaves the fonts', () => {
    for (const text of ['Vinča', 'Enūma Eliš', 'Mahābhārata', 'Çatalhöyük', 'Ḫattuša', 'ÿ ß ſ ŉ', '1,000–1,650 t × 2 — “quoted” …']) expect(unsupportedChar(text), text).toBeNull()
    expect(unsupportedChar('Κνωσός')).toBe('Κ')
    expect(unsupportedChar('Baalbek → Rome')).toBe('→')
    // heading() and hud() draw upper case: "µ" becomes Greek "Μ", "ẖ" becomes "H" + U+0331
    expect(unsupportedChar('Smaller than 1 µm?')).toBe('µ')
    expect(unsupportedChar('ẖ')).toBe('ẖ')
    expect(glyphReason('µ')).toBe('"µ" (U+00B5) draws as "Μ" (U+039C) in upper case, which has no glyph in the brand fonts (latin and latin-ext only)')
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
    // Orbitron has no latin-ext file: headings fall back per character to JetBrains Mono's latin-ext face, never to a system font
    expect(HEADING.split(',')[1].trim()).toBe("'JetBrains Mono'")
  })
})
