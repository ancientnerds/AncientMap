import { describe, expect, it } from 'vitest'

import { actItem } from '../Members'
import type { MemberAct } from '../types'

describe('Members actItem', () => {
  it('carries the raw count and names the accounts behind it', () => {
    // The live row on 2026-09-19: 126 Lyra answers from two accounts. Without
    // the "by 2" the number reads as member activity and is one person's week.
    const act: MemberAct = { act: 'Lyra answers', n: 126, by: 2, at: '2026-09-19T06:26:02+00:00' }
    const row = actItem(act)
    expect(row.key).toBe('Lyra answers')
    expect(row.label).toBe('Lyra answers')
    expect(row.value).toBe(126)
    expect(row.hint).toBe('by 2 accounts, last 19 Sep 06:26')
  })

  it('says account, singular, for one actor', () => {
    const row = actItem({ act: 'Likes', n: 2, by: 1, at: '2026-08-31T23:05:27+00:00' })
    expect(row.hint).toBe('by 1 account, last 31 Aug 23:05')
  })

  it('says never when the act has no date at all', () => {
    const row = actItem({ act: 'Bookmarks', n: 0, by: 0, at: null })
    expect(row.hint).toBe('never')
    expect(row.value).toBe(0)
  })
})
