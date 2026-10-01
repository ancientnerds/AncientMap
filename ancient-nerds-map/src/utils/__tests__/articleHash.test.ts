import { describe, it, expect } from 'vitest'
import { articleForHash } from '../articleHash'
import { slugify } from '../../seo/meta'

// Real titles from production (journals 77, 72, 52 and an ASCII one). On
// 2026-10-01 the first three could not be opened on /articles.html: the
// browser hands location.hash back percent-encoded, the slug carries the
// letter itself.
const SACSAYHUAMAN = 'Week of September 21: Teotihuacan Trophy Ornaments Found, Sacsayhuamán Waterworks, and More'
const SAYBURC = 'Week of August 17: Denisovan Leg Bones Reveal Exceptional Height, Sayburç Chamber, and More'
const GOBEKLI = 'Week of March 30: 12th Century Sword in Stone Verified Genuine, Göbekli Tepe Porthole Door, and More'
const ASCII = 'Week of September 14: 17,000 Artifacts at Sanxingdui, 557M-Year Cnidarian, and More'

const articles = [SACSAYHUAMAN, SAYBURC, GOBEKLI, ASCII].map((title, id) => ({ id, title }))

/** What a browser reports for location.hash after `location.hash = slug`. */
function browserHash(title: string): string {
  return '#' + encodeURIComponent(slugify(title))
}

describe('articleForHash', () => {
  it.each([SACSAYHUAMAN, SAYBURC, GOBEKLI])('opens a journal whose slug has an accent: %s', title => {
    expect(articleForHash(browserHash(title), articles)?.title).toBe(title)
  })

  it('still opens a journal whose slug is plain ASCII', () => {
    expect(articleForHash(browserHash(ASCII), articles)?.title).toBe(ASCII)
  })

  it('accepts a hash that was never encoded (typed or pasted)', () => {
    expect(articleForHash('#' + slugify(SACSAYHUAMAN), articles)?.title).toBe(SACSAYHUAMAN)
  })

  it('finds nothing for an unknown slug', () => {
    expect(articleForHash('#no-such-journal', articles)).toBeUndefined()
  })

  it('finds nothing for an empty hash', () => {
    expect(articleForHash('', articles)).toBeUndefined()
    expect(articleForHash('#', articles)).toBeUndefined()
  })

  it('treats a malformed percent sequence as "no journal", not as an error', () => {
    // The fragment is user-editable; decodeURIComponent throws URIError on these.
    expect(() => articleForHash('#%', articles)).not.toThrow()
    expect(articleForHash('#%E0%A4%A', articles)).toBeUndefined()
  })
})
