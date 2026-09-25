import { describe, expect, it } from 'vitest'

import { emptyNote, item, readablePath } from '../TopContent'
import type { ContentRow } from '../types'

const row = (over: Partial<ContentRow>): ContentRow => ({
  event_name: 'site_open',
  label: 'Machu Picchu',
  country: null,
  results: null,
  n: 7,
  ...over,
})

describe('TopContent item', () => {
  it('puts the country next to a site name', () => {
    expect(item(row({ country: 'Peru' })).label).toBe('Machu Picchu · Peru')
  })

  it('marks a search that found nothing, and says what a productive one found', () => {
    const dead = item(row({ event_name: 'search', label: 'zzqq', results: 0 }))
    expect(dead.hint).toBe('no results')
    expect(dead.tone).toBe('warn')
    const alive = item(row({ event_name: 'search', label: 'giza', results: 12 }))
    expect(alive.hint).toBe('12 results')
    expect(alive.tone).toBeUndefined()
    expect(item(row({ event_name: 'search', label: 'petra', results: 1 })).hint).toBe('1 result')
  })

  it('ranks by people and names the opens behind them', () => {
    // 2026-09-25: 24 opens of one site were six sessions of one laptop
    const busy = item(row({ n: 24, visitors: 6 }))
    expect(busy.value).toBe(6)
    expect(busy.hint).toBe('24 opens')
    expect(item(row({ n: 3, visitors: 3 })).hint).toBeUndefined()
    // An API older than the bundle sends no visitors: the opens rank
    expect(item(row({ n: 7 })).value).toBe(7)
  })

  it('reads a story or paper path as its title and still links it', () => {
    const story = item(row({ event_name: 'story_open', label: '/news-archive/howard-vyses-1837-excavation-8395' }))
    expect(story.label).toBe('Howard vyses 1837 excavation')
    expect(story.href).toBe('https://ancientnerds.com/news-archive/howard-vyses-1837-excavation-8395')
    expect(readablePath('/research/the-phaeton-hypothesis/')).toBe('The phaeton hypothesis')
  })

  it('links paths to the main site and leaves plain names unlinked', () => {
    expect(item(row({ event_name: 'paper_open', label: '/research/p' })).href).toBe(
      'https://ancientnerds.com/research/p'
    )
    expect(item(row({})).href).toBeUndefined()
  })

  it('survives a row without a label', () => {
    expect(item(row({ label: '' })).label).toBe('—')
  })
})

describe('TopContent note', () => {
  it('names only the lists that are actually empty', () => {
    const note = emptyNote(['Stories', 'Papers'])
    expect(note).toContain('Stories: nobody opened a story from a list in this window')
    expect(note).toContain('Papers: nobody opened a paper from a list in this window')
    expect(note).not.toContain('Search terms')
  })

  it('says nothing about an event whose list has rows', () => {
    // The sentence used to be a constant: "story_open, paper_open and search
    // have never fired, not once" rendered directly under the ranked lists of
    // those very events — the state the repo's own screenshot fixture draws.
    const note = emptyNote([])
    expect(note).toBe('Only what the site actually reports is listed.')
    expect(note).not.toContain('never fired')
  })

  it('calls an empty search list a quiet window', () => {
    expect(emptyNote(['Search terms'])).toContain('Search terms: nobody searched in this window')
  })
})
