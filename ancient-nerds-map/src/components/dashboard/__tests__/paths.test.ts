import { describe, expect, it } from 'vitest'

import { chainChips, entryItem, exitItem, outboundItem, outboundRest } from '../Paths'

describe('Paths rows', () => {
  it('warns only when a landing page held every session it got', () => {
    const dead = entryItem({ page: 'story', sessions: 4, stopped: 4 })
    expect(dead.value).toBe(4)
    expect(dead.hint).toBe('4 went no further')
    expect(dead.tone).toBe('warn')
    const moving = entryItem({ page: 'story', sessions: 4, stopped: 3 })
    expect(moving.hint).toBe('3 went no further')
    expect(moving.tone).toBeUndefined()
  })

  it('leaves out the hint when nobody stopped there', () => {
    const row = entryItem({ page: 'site', sessions: 9, stopped: 0 })
    expect(row.hint).toBeUndefined()
    expect(row.tone).toBeUndefined()
  })

  it('reads an exit against how often that page type was seen', () => {
    expect(exitItem({ page: 'story', sessions: 12, views: 31 }).hint).toBe('of 31 views')
  })

  it('counts a single outbound visitor in the singular', () => {
    expect(outboundItem({ host: 'getty.edu', clicks: 1, visitors: 1 }).hint).toBe('1 visitor')
    expect(outboundItem({ host: 'youtube.com', clicks: 5, visitors: 4 }).hint).toBe('4 visitors')
  })

  it('namespaces the keys so one page type can sit in three lists at once', () => {
    expect(entryItem({ page: 'story', sessions: 1, stopped: 0 }).key).toBe('entry:story')
    expect(exitItem({ page: 'story', sessions: 1, views: 1 }).key).toBe('exit:story')
    expect(outboundItem({ host: 'story', clicks: 1, visitors: 1 }).key).toBe('out:story')
  })
})

describe('journey chips', () => {
  it('splits a chain into entry, page and action chips', () => {
    expect(chainChips('google → story → site_open → site')).toEqual([
      { label: 'google', tone: 'entry' },
      { label: 'story', tone: 'page' },
      { label: 'site_open', tone: 'action' },
      { label: 'site', tone: 'page' },
    ])
  })

  it('keeps a lone entry as the whole chain', () => {
    expect(chainChips('direct')).toEqual([{ label: 'direct', tone: 'entry' }])
  })

  // "search" is both a page type (/search.html) and an event name; the chain is
  // a plain string, so the colour cannot tell them apart. Both read as an action.
  it('paints every step that carries an action name as an action', () => {
    expect(chainChips('direct → search → search').map(c => c.tone)).toEqual([
      'entry',
      'action',
      'action',
    ])
  })
})

describe('outboundRest', () => {
  it('counts the long tail past the listed hosts', () => {
    const links = Array.from({ length: 14 }, (_, i) => ({ host: `h${i}.org`, clicks: 1, visitors: 1 }))
    expect(outboundRest(links)).toBe('…and 4 more hosts, one visitor each.')
    expect(outboundRest(links.slice(0, 11))).toBe('…and 1 more host, one visitor.')
    expect(outboundRest(links.slice(0, 10))).toBe('')
    const mixed = [...links.slice(0, 10), { host: 'x.org', clicks: 3, visitors: 2 }]
    expect(outboundRest(mixed)).toBe('…and 1 more host.')
  })
})
