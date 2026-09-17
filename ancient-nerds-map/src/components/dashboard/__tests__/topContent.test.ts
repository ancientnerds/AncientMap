import { describe, expect, it } from 'vitest'

import { item } from '../TopContent'
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

  it('marks a search that found nothing, and leaves a productive one alone', () => {
    const dead = item(row({ event_name: 'search', label: 'zzqq', results: 0 }))
    expect(dead.hint).toBe('0 Treffer')
    expect(dead.tone).toBe('warn')
    const alive = item(row({ event_name: 'search', label: 'giza', results: 12 }))
    expect(alive.hint).toBeUndefined()
    expect(alive.tone).toBeUndefined()
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
