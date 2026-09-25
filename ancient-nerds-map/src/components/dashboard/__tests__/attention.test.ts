import { describe, expect, it } from 'vitest'

import { attentionLines } from '../Attention'
import type { ContentData, GlobeData, ProblemsData } from '../types'

const globe = (loads: number, reached: number): GlobeData => ({
  loads,
  reached,
  gave_up: loads - reached,
  sessions: { all: loads, reached },
  ready_ms: { min: null, median: null, max: null, samples: 0 },
  not_reached: { unsupported: 0, error: 0, abandoned: 0, no_signal: loads - reached },
  abandon_ms: { min: null, median: null, max: null, samples: 0 },
  by_device: [{ device: 'mobile', loads, reached }],
})

const problems: ProblemsData = {
  problems: [
    { kind: 'slow_page', label: 'globe · INP', score: 246, detail: 'p75 768 ms against a 200 ms budget, 91 samples', at: null, last: null },
    { kind: 'js_error', label: 'NotFoundError', score: 9, detail: '3 visitors', at: null, last: null },
    { kind: 'slow_page', label: 'paper · LCP', score: 19, detail: 'p75 3108 ms', at: null, last: null },
    { kind: 'slow_page', label: 'radar · LCP', score: 19, detail: 'p75 6700 ms', at: null, last: null },
  ],
}

describe('attentionLines', () => {
  it('leads with the globe, then the three worst problems, then the dead searches', () => {
    const content: ContentData = {
      sites: [],
      stories: [],
      papers: [],
      searches: [
        { event_name: 'search', label: 'aeaea', country: null, results: 0, n: 1, visitors: 1 },
        { event_name: 'search', label: 'crete', country: null, results: 100, n: 2, visitors: 2 },
      ],
    }
    const lines = attentionLines(problems, globe(26, 21), content)
    expect(lines.map(l => l.key)).toEqual([
      'globe',
      'problem:slow_page:globe · INP',
      'problem:js_error:NotFoundError',
      'problem:slow_page:paper · LCP',
      'dead-searches',
    ])
    expect(lines[0].text).toBe('Globe: 21 of 26 loads reached it. Phones 21 of 26 loads reached the globe.')
    expect(lines[0].tone).toBe('warn')
    expect(lines[2].tone).toBe('bad')
    expect(lines[4].text).toBe('Searches that found nothing: “aeaea”.')
  })

  it('grades the globe by its share of loads', () => {
    expect(attentionLines(null, globe(10, 9), null)[0].tone).toBe('ok')
    expect(attentionLines(null, globe(10, 5), null)[0].tone).toBe('bad')
  })

  it('has nothing to say before anything loaded', () => {
    expect(attentionLines(null, null, null)).toEqual([])
  })
})
