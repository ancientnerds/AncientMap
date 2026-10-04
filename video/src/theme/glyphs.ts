/**
 * The code points the brand fonts draw. LATIN_RANGE and LATIN_EXT_RANGE are the
 * unicode-range of the latin and latin-ext files fonts.ts loads, copied from
 * ancient-nerds-map/public/fonts/fonts.css. They decide which face Chrome tries for a
 * character, not whether that face has it: Google's subset files leave gaps in their
 * declared range (JetBrains Mono latin-ext has no Ḫ, Ḥ, Ṣ or Ṭ, its latin file no U+2011
 * or ‰), and Chrome draws such a character in a Windows system font without an error.
 *
 * DRAWABLE is therefore generated from the files themselves (scripts/fontCoverage.ts):
 * each loaded face's cmap within its unicode-range, the part common to the three stacks
 * of type.ts (heading, body/hud, serif), plus tab, line feed and carriage return, which
 * CSS lays out as white space. test/glyphs.test.ts recomputes it and fails on drift;
 * `npx tsx scripts/glyphs.ts` prints the new constant. blocks/index.ts checkBlocks refuses
 * every drawn timeline string with a character outside it, naming the scene, the prop
 * path and the character. heading() and hud() draw upper case (text-transform), which the
 * browser applies with the full Unicode mapping, so a character is drawable only when its
 * upper case is covered too ("ƒ" U+0192 turns into "Ƒ" U+0191, which no brand face maps).
 */
export const LATIN_RANGE =
  'U+0000-00FF, U+0131, U+0152-0153, U+02BB-02BC, U+02C6, U+02DA, U+02DC, U+0304, U+0308, U+0329, U+2000-206F, U+20AC, U+2122, U+2191, U+2193, U+2212, U+2215, U+FEFF, U+FFFD'
export const LATIN_EXT_RANGE =
  'U+0100-02BA, U+02BD-02C5, U+02C7-02CC, U+02CE-02D7, U+02DD-02FF, U+0304, U+0308, U+0329, U+1D00-1DBF, U+1E00-1E9F, U+1EF2-1EFF, U+2020, U+20A0-20AB, U+20AD-20C0, U+2113, U+2C60-2C7F, U+A720-A7FF'
export const DRAWABLE =
  'U+0009-000A, U+000D, U+0020-007E, U+00A0-00B4, U+00B6-0131, U+0134-017F, U+018F, U+0192, U+01A0-01A1, U+01AF-01B0, U+01CD-01CE, U+01E6-01E7, U+01EA-01EB, U+01FC-01FF, U+0218-021B, U+0232-0233, U+0237, U+0259, U+02BC, U+02C6-02C7, U+02DA, U+02DC-02DD, U+0304, U+0308, U+1E80-1E85, U+1E9E, U+1EF2-1EF9, U+2013-2014, U+2018-201A, U+201C-201E, U+2020, U+2022, U+2026, U+2032-2033, U+2039-203A, U+2044, U+20AB-20AC, U+20AE, U+20BD, U+2113, U+2122, U+2191, U+2193, U+2212, U+FEFF'

/** A CSS unicode-range ("U+0000-00FF, U+0131") as inclusive [first, last] code point pairs. */
export function parseUnicodeRange(css: string): [number, number][] {
  return css.split(',').map((part) => {
    const m = /^U\+([0-9A-F]+)(?:-([0-9A-F]+))?$/i.exec(part.trim())
    if (!m) throw new Error(`not a unicode-range entry: "${part.trim()}"`)
    const first = parseInt(m[1], 16)
    return [first, m[2] === undefined ? first : parseInt(m[2], 16)]
  })
}

const COVERED = parseUnicodeRange(DRAWABLE)

/** Whether the brand fonts draw every code point of `text` as written. */
function covered(text: string): boolean {
  return [...text].every((ch) => {
    const cp = ch.codePointAt(0) as number
    return COVERED.some(([first, last]) => cp >= first && cp <= last)
  })
}

/**
 * The first character of `text` the brand fonts cannot draw, as written or in upper
 * case (every code point of its full upper-case mapping), or null when they draw all of it.
 */
export function unsupportedChar(text: string): string | null {
  for (const ch of text) {
    if (!covered(ch) || !covered(ch.toUpperCase())) return ch
  }
  return null
}

const codes = (text: string) => [...text].map((ch) => `U+${(ch.codePointAt(0) as number).toString(16).toUpperCase().padStart(4, '0')}`).join(' ')

/** Why the brand fonts cannot draw `ch` (a character unsupportedChar returned): the written character or its upper case. */
export function glyphReason(ch: string): string {
  const upper = ch.toUpperCase()
  const turns = covered(ch) ? ` draws as "${upper}" (${codes(upper)}) in upper case, which` : ''
  return `"${ch}" (${codes(ch)})${turns} has no glyph in the brand fonts (latin and latin-ext only)`
}
