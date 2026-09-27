import { describe, expect, it } from 'vitest'

import { HOOK_LINE_MAX_CHARS, captionLines, lineAt, mergeCredits, tickerAt } from '../src/captions'

const w = (text: string, from: number, to: number) => ({ text, from, to })
const texts = (lines: ReturnType<typeof captionLines>) => lines.map((l) => l.words.map((x) => x.text).join(' '))

describe('captionLines', () => {
  it('breaks after four words, after punctuation and at long pauses', () => {
    const lines = captionLines([
      w('THIS', 0, 10), w('STONE', 10, 20), w('WEIGHS', 20, 30), w('ABOUT', 30, 40), w('1,000', 40, 55), w('TONNES.', 55, 70),
      w('NOBODY', 100, 110), w('MOVED', 110, 120),
    ])
    expect(texts(lines)).toEqual(['THIS STONE WEIGHS ABOUT', '1,000 TONNES.', 'NOBODY MOVED'])
    expect(lines[1]).toMatchObject({ from: 40, to: 70 })
  })
  it('breaks before a word that would make the line longer than 24 characters (one row of the caption zone)', () => {
    expect(HOOK_LINE_MAX_CHARS).toBe(24)
    const lines = captionLines([w('ARCHAEOLOGISTS', 0, 20), w('FOUND', 20, 30), w('SOMETHING', 30, 45), w('IMPOSSIBLE', 45, 60)])
    expect(texts(lines)).toEqual(['ARCHAEOLOGISTS FOUND', 'SOMETHING IMPOSSIBLE'])
  })
})

describe('lineAt', () => {
  const lines = captionLines([w('ONE', 0, 10), w('TWO.', 10, 20), w('THREE', 25, 40)])
  it('holds a line until the next starts or 10 frames after its last word', () => {
    expect(lineAt(lines, 5)?.words[0].text).toBe('ONE')
    expect(lineAt(lines, 24)?.words[0].text).toBe('ONE')
    expect(lineAt(lines, 25)?.words[0].text).toBe('THREE')
    expect(lineAt(lines, 49)?.words[0].text).toBe('THREE')
    expect(lineAt(lines, 50)).toBeNull()
  })
})

describe('tickerAt', () => {
  it('counts the evidence shown so far and remembers the change', () => {
    const steps = [{ frame: 0, n: 0 }, { frame: 100, n: 1 }, { frame: 300, n: 3 }]
    expect(tickerAt(steps, 50)).toEqual({ n: 0, previous: 0, since: -1 })
    expect(tickerAt(steps, 150)).toEqual({ n: 1, previous: 0, since: 100 })
    expect(tickerAt(steps, 300)).toEqual({ n: 3, previous: 1, since: 300 })
  })
})

describe('mergeCredits', () => {
  it('merges repeated © parts and puts other credits first', () => {
    expect(mergeCredits(['© Mapbox © OpenStreetMap © Maxar', '© Mapbox © Maxar'])).toBe('© Mapbox © OpenStreetMap © Maxar')
    expect(mergeCredits(['© Mapbox © Maxar', 'Photo: Jane Doe (CC BY-SA 4.0)'])).toBe('Photo: Jane Doe (CC BY-SA 4.0) · © Mapbox © Maxar')
    expect(mergeCredits([])).toBe('')
  })
})
