import { describe, expect, it } from 'vitest'

import { isCriticism, target } from '../FeedbackInbox'
import type { FeedbackItem } from '../types'

const item = (over: Partial<FeedbackItem>): FeedbackItem => ({
  created_at: '2026-09-17T20:00:00Z',
  url_path: null,
  prompt: 'site_page',
  answer: null,
  text: null,
  site: null,
  country: null,
  paper: null,
  journal: null,
  story: null,
  ...over,
})

describe('feedback target', () => {
  it('names a paper and links to it', () => {
    expect(target(item({ prompt: 'paper_end', paper: 'hard-stone' }))).toEqual({
      label: 'hard-stone',
      href: 'https://ancientnerds.com/research/hard-stone',
    })
  })

  it('names a journal and links to it', () => {
    expect(target(item({ prompt: 'journal_end', journal: 'week-of-september-7' })).href).toBe(
      'https://ancientnerds.com/articles/week-of-september-7'
    )
  })

  it('shows a site with its country and links to the globe', () => {
    const t = target(item({ site: 'a1662bc9-f57d-40d0-99d8-0a70a1c617a8', country: 'Albania' }))
    expect(t.label).toBe('Albania · a1662bc9')
    expect(t.href).toBe('https://ancientnerds.com/globe.html#focus=a1662bc9-f57d-40d0-99d8-0a70a1c617a8')
  })

  it('falls back to the page when the event carried no id', () => {
    expect(target(item({ prompt: 'search_empty', url_path: '/search.html' }))).toEqual({
      label: 'search',
      href: 'https://ancientnerds.com/search.html',
    })
    expect(target(item({})).label).toBe('—')
  })
})

describe('criticism filter', () => {
  it('keeps thumbs down and anything written, drops a bare yes', () => {
    expect(isCriticism(item({ answer: 'no' }))).toBe(true)
    expect(isCriticism(item({ answer: 'yes', text: 'more maps please' }))).toBe(true)
    expect(isCriticism(item({ answer: 'yes' }))).toBe(false)
    expect(isCriticism(item({ text: '   ' }))).toBe(false)
  })
})
