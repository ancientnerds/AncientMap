import { describe, expect, it } from 'vitest'

import { FEEDBACK_TEXT_MAX, feedbackPayload } from '../feedback'

describe('feedbackPayload', () => {
  it('carries prompt, answer, clipped text and the page type', () => {
    const payload = feedbackPayload('story_end', 'no', '  too   short \n and no sources ', '/news-archive/x-1')
    expect(payload).toEqual({ prompt: 'story_end', answer: 'no', text: 'too short and no sources', page: 'story' })
  })

  it('omits an empty text and a missing answer', () => {
    expect(feedbackPayload('search_empty', null, '   ', '/search.html')).toEqual({
      prompt: 'search_empty',
      answer: undefined,
      text: undefined,
      page: 'search',
    })
  })

  it('clips the text to the limit', () => {
    const payload = feedbackPayload('not_found', null, 'x'.repeat(500), '/nope')
    expect((payload.text as string).length).toBe(FEEDBACK_TEXT_MAX)
  })
})
