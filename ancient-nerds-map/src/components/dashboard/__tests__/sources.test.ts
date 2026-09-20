import { describe, expect, it } from 'vitest'

import { bucketTotals, familyItem, hostItem, sourceBucket, spamLine, statusItem } from '../Sources'

describe('source buckets', () => {
  it('folds the API families into the six founder buckets', () => {
    expect(sourceBucket('google')).toBe('search')
    expect(sourceBucket('search')).toBe('search')
    expect(sourceBucket('ai')).toBe('ai')
    expect(sourceBucket('direct')).toBe('direct')
    expect(sourceBucket('discord.com')).toBe('discord')
    expect(sourceBucket('discord')).toBe('discord')
    expect(sourceBucket('youtube')).toBe('youtube')
    expect(sourceBucket('m.youtube.com')).toBe('youtube')
    expect(sourceBucket('reddit.com')).toBe('other')
  })

  it('sums sessions per bucket in the fixed display order', () => {
    // `views` is required on SourceRow since the log coverage landed; bucketTotals
    // sums sessions and never reads it, so the numbers below stay the assertion.
    const rows = [
      { source: 'google.com', family: 'google', sessions: 10, views: 14 },
      { source: 'bing.com', family: 'search', sessions: 2, views: 2 },
      { source: 'direct', family: 'direct', sessions: 7, views: 19 },
      { source: 'youtube', family: 'youtube', sessions: 3, views: 4 },
      { source: 'reddit.com', family: 'reddit.com', sessions: 1, views: 1 },
    ]
    expect(bucketTotals(rows)).toEqual([
      ['search', 'Search', 12],
      ['ai', 'AI assistants', 0],
      ['discord', 'Discord', 0],
      ['youtube', 'YouTube', 3],
      ['direct', 'Direct', 7],
      ['other', 'Other', 1],
    ])
  })

  it('returns no row at all without sessions, so the empty sentence can show', () => {
    // Six rows reading 0 is not what "no data" looks like, and the `empty`
    // prop next to this list was unreachable code while it was.
    expect(bucketTotals([])).toEqual([])
  })
})

describe('nginx log rows', () => {
  it('counts bots beside the humans, and says nothing when there are none', () => {
    expect(familyItem({ family: 'google', visits: 189, bots: 12 }).hint).toBe('+ 12 bots')
    // One is the live value on the ai family (2026-09-19): BOT_UA_RE matches
    // exactly one line of the log, so "+ 1 bots" is what the panel shipped.
    expect(familyItem({ family: 'ai', visits: 21, bots: 1 }).hint).toBe('+ 1 bot')
    const clean = familyItem({ family: 'discord', visits: 4, bots: 0 })
    expect(clean.hint).toBeUndefined()
    expect(clean.key).toBe('log:discord')
    expect(clean.value).toBe(4)
  })

  it('leaves a host row bare, so it reads against the Umami list above it', () => {
    const row = hostItem({ host: 'google.com', visits: 189 })
    expect(row).toEqual({ key: 'loghost:google.com', label: 'google.com', value: 189 })
  })

  it('warns on what is ours and stays quiet on what is theirs', () => {
    expect(statusItem({ status: 410, visits: 21 }).tone).toBe('warn')
    expect(statusItem({ status: 500, visits: 1 }).tone).toBe('warn')
    expect(statusItem({ status: 503, visits: 1 }).tone).toBe('warn')
    // 499 is the visitor closing the tab before nginx answered. Red would
    // blame us for someone else's impatience.
    expect(statusItem({ status: 499, visits: 4 }).tone).toBeUndefined()
  })

  it('always carries a hint, because BarList paints tone on nothing else', () => {
    for (const status of [410, 499, 500, 502, 503, 504, 507]) {
      expect(statusItem({ status, visits: 1 }).hint).toBeTruthy()
    }
    expect(statusItem({ status: 410, visits: 21 }).hint).toBe('story withdrawn on purpose')
    // referral_log.is_bad_answer() admits every status >= 500, so a code the
    // table has never seen must still say something rather than render blank.
    expect(statusItem({ status: 507, visits: 1 }).hint).toBe('unexpected')
    expect(statusItem({ status: 507, visits: 1 }).tone).toBe('warn')
  })

  it('states the rule that keeps referrer spam out, in the singular too', () => {
    // The panel used to promise "Bots ... are out of every list" while its
    // third-largest family was 17 forged-referer hits on GET /.
    expect(spamLine(17)).toContain('17 arrivals in this window')
    expect(spamLine(1)).toContain('1 arrival in this window')
    expect(spamLine(0)).toContain('0 arrivals in this window')
  })
})
