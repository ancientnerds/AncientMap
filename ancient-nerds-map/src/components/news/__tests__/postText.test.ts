import { describe, it, expect } from 'vitest'
import { splitPostText } from '../postText'

describe('splitPostText', () => {
  it('hängt die Quell-URL am Ende ab — der Fall aus der Praxis (Story 7926)', () => {
    const { paragraphs, links } = splitPostText(
      'Yet reconstructions still show people pulling sarsen stones, not cattle dragging them. 🐂🪨 ' +
        'https://www.english-heritage.org.uk/visit/places/stonehenge/',
    )
    expect(links).toEqual(['https://www.english-heritage.org.uk/visit/places/stonehenge/'])
    expect(paragraphs).toHaveLength(1)
    expect(paragraphs[0]).not.toContain('http')
    expect(paragraphs[0].endsWith('🐂🪨')).toBe(true)
  })

  it('ein Link MITTEN im Satz bleibt stehen — nur Angehängtes wird abgetrennt', () => {
    const text = 'Der Bericht auf https://example.org/report nennt drei Fundstellen.'
    const { paragraphs, links } = splitPostText(text)
    expect(links).toEqual([])
    expect(paragraphs).toEqual([text])
  })

  it('mehrere angehängte Links kommen in ursprünglicher Reihenfolge zurück', () => {
    const { paragraphs, links } = splitPostText(
      'Text.\nhttps://a.example/one https://b.example/two',
    )
    expect(links).toEqual(['https://a.example/one', 'https://b.example/two'])
    expect(paragraphs).toEqual(['Text.'])
  })

  it('Satzzeichen hinter der URL gehören nicht zur URL', () => {
    expect(splitPostText('Mehr dazu hier: https://example.org/x.').links).toEqual([
      'https://example.org/x',
    ])
  })

  it('Absätze bleiben Absätze, Leerzeilen fallen weg', () => {
    const { paragraphs } = splitPostText('Erster.\n\n  Zweiter.  \nDritter.')
    expect(paragraphs).toEqual(['Erster.', 'Zweiter.', 'Dritter.'])
  })

  it('ohne angehängten Link ändert sich nichts', () => {
    const { paragraphs, links } = splitPostText('Nur Prosa, kein Link.')
    expect(links).toEqual([])
    expect(paragraphs).toEqual(['Nur Prosa, kein Link.'])
  })

  it('nur https/http — ein javascript:-Anhang wird nie zu einem Link', () => {
    const { paragraphs, links } = splitPostText('Text. javascript:alert(1)')
    expect(links).toEqual([])
    expect(paragraphs[0]).toContain('javascript:alert(1)')
  })
})
