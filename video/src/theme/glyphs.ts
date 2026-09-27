/**
 * The code points the brand fonts draw: the unicode-range of the latin and
 * latin-ext files fonts.ts loads, copied from ancient-nerds-map/public/fonts/fonts.css.
 * Any other character (Greek, Cyrillic, an arrow, an emoji) would render in a
 * Windows system font without an error, so blocks/index.ts checkBlocks refuses
 * every timeline string that holds one, naming the scene, the prop path and
 * the character. heading() and hud() draw upper case (text-transform), which
 * the browser applies with the full Unicode mapping, so a character is drawable
 * only when its upper case is covered too ("µ" U+00B5 turns into Greek "Μ").
 */
export const LATIN_RANGE =
  'U+0000-00FF, U+0131, U+0152-0153, U+02BB-02BC, U+02C6, U+02DA, U+02DC, U+0304, U+0308, U+0329, U+2000-206F, U+20AC, U+2122, U+2191, U+2193, U+2212, U+2215, U+FEFF, U+FFFD'
export const LATIN_EXT_RANGE =
  'U+0100-02BA, U+02BD-02C5, U+02C7-02CC, U+02CE-02D7, U+02DD-02FF, U+0304, U+0308, U+0329, U+1D00-1DBF, U+1E00-1E9F, U+1EF2-1EFF, U+2020, U+20A0-20AB, U+20AD-20C0, U+2113, U+2C60-2C7F, U+A720-A7FF'

/** A CSS unicode-range ("U+0000-00FF, U+0131") as inclusive [first, last] code point pairs. */
export function parseUnicodeRange(css: string): [number, number][] {
  return css.split(',').map((part) => {
    const m = /^U\+([0-9A-F]+)(?:-([0-9A-F]+))?$/i.exec(part.trim())
    if (!m) throw new Error(`not a unicode-range entry: "${part.trim()}"`)
    const first = parseInt(m[1], 16)
    return [first, m[2] === undefined ? first : parseInt(m[2], 16)]
  })
}

const COVERED = [...parseUnicodeRange(LATIN_RANGE), ...parseUnicodeRange(LATIN_EXT_RANGE)]

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
