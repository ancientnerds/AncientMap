import { describe, expect, it } from 'vitest'

import { searchWords, startsAWord, trigramSimilarity, trigrams, TYPO_SIMILARITY } from '../searchUtils'

describe('searchWords', () => {
  it('drops the filler, the short words and the repeats', () => {
    expect(searchWords('the valley of kings, egypt')).toEqual(['valley', 'kings', 'egypt'])
    expect(searchWords('kv 62 valley')).toEqual(['valley'])
    expect(searchWords('temple temple of zeus')).toEqual(['temple', 'zeus'])
  })

  it('keeps letters of every script', () => {
    expect(searchWords('باتنة أريس')).toEqual(['باتنة', 'أريس'])
  })
})

describe('startsAWord', () => {
  it('matches at the start of any word, never inside one', () => {
    expect(startsAWord('valley of the kings', 'kings')).toBe(true)
    expect(startsAWord('afan valley, upper workings', 'kings')).toBe(false)
    expect(startsAWord('tell el-amarna', 'amarna')).toBe(true)
  })
})

describe('trigramSimilarity', () => {
  it('scores words like pg_trgm similarity()', () => {
    expect(trigrams('giza')).toEqual(new Set(['  g', ' gi', 'giz', 'iza', 'za ']))
    expect(trigramSimilarity(trigrams('gize'), trigrams('giza'))).toBeCloseTo(3 / 7)
    expect(trigramSimilarity(trigrams('baalk'), trigrams('baalbek'))).toBeCloseTo(0.4)
    expect(trigramSimilarity(trigrams('crerre'), trigrams('crete'))).toBeCloseTo(0.3)
    expect(trigramSimilarity(trigrams('giza'), trigrams('giza'))).toBe(1)
  })

  it('draws the typo line between the searches it should and should not rescue', () => {
    expect(trigramSimilarity(trigrams('baalk'), trigrams('baalbek'))).toBeGreaterThanOrEqual(TYPO_SIMILARITY)
    expect(trigramSimilarity(trigrams('notswa'), trigrams('botswana'))).toBeLessThan(TYPO_SIMILARITY)
  })
})
