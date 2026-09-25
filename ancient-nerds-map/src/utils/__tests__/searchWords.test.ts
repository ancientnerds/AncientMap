import { describe, expect, it } from 'vitest'

import { searchWords, startsAWord } from '../searchUtils'

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
