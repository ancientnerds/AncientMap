import { describe, expect, it } from 'vitest'

import { collapsePairs, isCriticism, target } from '../FeedbackInbox'
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

describe('vote and comment are one complaint', () => {
  const vote = item({ prompt: 'paper_end', answer: 'no', paper: 'p', created_at: '2026-09-17T20:00:00Z' })
  const comment = item({
    prompt: 'paper_end',
    answer: 'no',
    paper: 'p',
    text: 'sources missing',
    created_at: '2026-09-17T20:00:20Z',
  })

  it('keeps the sentence and drops the bare vote it belongs to', () => {
    expect(collapsePairs([comment, vote])).toEqual([comment])
  })

  it('keeps a bare vote that nobody explained', () => {
    const lonely = item({ prompt: 'site_page', answer: 'no', site: 'other' })
    expect(collapsePairs([comment, vote, lonely])).toEqual([comment, lonely])
  })

  it('keeps a vote whose comment came much later — that is a second visit', () => {
    const later = { ...comment, created_at: '2026-09-17T21:00:00Z' }
    expect(collapsePairs([later, vote])).toEqual([later, vote])
  })

  it('does not merge across different things or different verdicts', () => {
    const otherPaper = { ...comment, paper: 'q' }
    const upvote = { ...vote, answer: 'yes' as const }
    expect(collapsePairs([otherPaper, vote])).toEqual([otherPaper, vote])
    expect(collapsePairs([comment, upvote])).toEqual([comment, upvote])
  })
})

