import { describe, expect, it } from 'vitest'

import { heroSrcSet } from '../heroSrcSet'

describe('heroSrcSet', () => {
  it('names the copy at 800w and the original at its own width', () => {
    expect(
      heroSrcSet({ url: '/data/images/wiki/aaaaaaaa/a.webp', url_800: '/data/images/wiki-800/aaaaaaaa/a.webp', width: 2048 }),
    ).toBe('/data/images/wiki-800/aaaaaaaa/a.webp 800w, /data/images/wiki/aaaaaaaa/a.webp 2048w')
  })

  it('is undefined without a copy or without a known width', () => {
    expect(heroSrcSet({ url: '/x/a.webp', url_800: null, width: 1600 })).toBeUndefined()
    expect(heroSrcSet({ url: '/x/a.webp', url_800: '/y/a.webp', width: null })).toBeUndefined()
  })

  it('passes the server-encoded paths through untouched', () => {
    const url = '/data/images/wiki/7ee8535b/%D0%97%D0%BC%D1%96%D1%94%D0%B2%D1%96%20%D0%B2%D0%B0%D0%BB%D0%B8%2C%201.webp'
    const url_800 = url.replace('/wiki/', '/wiki-800/')
    expect(heroSrcSet({ url, url_800, width: 1600 })).toBe(`${url_800} 800w, ${url} 1600w`)
  })
})
