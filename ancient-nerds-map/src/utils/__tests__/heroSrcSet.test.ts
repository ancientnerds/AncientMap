import { describe, expect, it } from 'vitest'

import { heroSrcSet, srcsetPath } from '../heroSrcSet'

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

  it('encodes each path segment, never the slashes', () => {
    expect(srcsetPath('/data/images/wiki/7ee8535b/Змієві вали, 1.webp')).toBe(
      '/data/images/wiki/7ee8535b/%D0%97%D0%BC%D1%96%D1%94%D0%B2%D1%96%20%D0%B2%D0%B0%D0%BB%D0%B8%2C%201.webp',
    )
  })
})
