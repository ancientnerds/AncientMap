import { describe, expect, it } from 'vitest'

import { problemLabel, severity } from '../Problems'

describe('problem severity', () => {
  it('paints what breaks a page red, what slows it amber, the rest green-grey', () => {
    expect(severity('js_error')).toBe('high')
    expect(severity('broken_link')).toBe('high')
    expect(severity('slow_page')).toBe('mid')
    expect(severity('shallow_exit')).toBe('low')
    expect(severity('empty_search')).toBe('low')
  })

  it('names every kind the API can send', () => {
    for (const kind of ['js_error', 'slow_page', 'broken_link', 'shallow_exit', 'empty_search'] as const) {
      expect(problemLabel(kind)).not.toBe('')
    }
    expect(problemLabel('js_error')).toBe('JS error')
  })
})
