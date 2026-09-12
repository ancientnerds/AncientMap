import { describe, expect, it } from 'vitest'

import { blurb, collapse, cut, stripCitations } from '../text'

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

describe('stripCitations — Fußnotenmarker aus Snippet-Text', () => {
  it('entfernt Marker samt führendem Leerzeichen, Satzzeichen bleibt', () => {
    expect(stripCitations('an ancient site in Egypt [1]. It is known [1].')).toBe(
      'an ancient site in Egypt. It is known.',
    )
  })

  it('entfernt mehrstellige und aufeinanderfolgende Marker', () => {
    expect(stripCitations('Beleg [12][3] folgt')).toBe('Beleg folgt')
  })

  it('lässt Text ohne Marker vollständig unverändert', () => {
    expect(stripCitations('kein  Marker hier')).toBe('kein  Marker hier')
  })

  it('erhält Absatzumbrüche — das JSON-LD der Referenz-Heads trägt sie', () => {
    expect(stripCitations('Satz eins [1].\nSatz zwei [2].')).toBe('Satz eins.\nSatz zwei.')
  })

  it('rührt Jahreszahlen in Klammern und Maßangaben nicht an', () => {
    expect(stripCitations('ein 40 m [1] hohes Bauwerk (1200 v. Chr.)')).toBe(
      'ein 40 m hohes Bauwerk (1200 v. Chr.)',
    )
  })
})

describe('collapse — " ".join(s.split())', () => {
  it('kollabiert Whitespace-Läufe und trimmt', () => {
    expect(collapse('  a\t b \n c ')).toBe('a b c')
  })
})
