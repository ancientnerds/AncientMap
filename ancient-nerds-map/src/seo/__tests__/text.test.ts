import { describe, expect, it } from 'vitest'

import { blurb, collapse, cut } from '../text'

describe('blurb — Portierung von seo_pages.blurb', () => {
  it('lässt kurze Texte unangetastet, kollabiert aber Whitespace', () => {
    expect(blurb('a  b\nc', 180)).toBe('a b c')
  })

  it('schneidet an der Wortgrenze und hängt … an', () => {
    expect(blurb('alpha beta gamma', 12)).toBe('alpha beta…')
  })

  it('null/leer → leerer String', () => {
    expect(blurb(null, 10)).toBe('')
    expect(blurb('', 10)).toBe('')
    expect(blurb(undefined, 10)).toBe('')
  })

  it('zählt Codepoints wie Python, nicht UTF-16-Einheiten', () => {
    // '𐤀' (U+10900) belegt 2 UTF-16-Einheiten, ist aber 1 Zeichen.
    expect(blurb('𐤀𐤀𐤀', 3)).toBe('𐤀𐤀𐤀')
  })
})

describe('cut — Python-Slicing s[:n]', () => {
  it('harter Schnitt nach Codepoints', () => {
    expect(cut('abcdef', 4)).toBe('abcd')
    expect(cut('𐤀𐤀𐤀', 2)).toBe('𐤀𐤀')
  })

  it('kürzere Strings bleiben unverändert', () => {
    expect(cut('ab', 5)).toBe('ab')
  })
})

describe('collapse — " ".join(s.split())', () => {
  it('kollabiert Whitespace-Läufe und trimmt', () => {
    expect(collapse('  a\t b \n c ')).toBe('a b c')
  })
})
