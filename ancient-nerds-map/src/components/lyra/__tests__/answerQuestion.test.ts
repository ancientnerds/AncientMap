import { describe, expect, it } from 'vitest'

import { questionBefore } from '../answerQuestion'

const msg = (role: string, content: string) => ({ role, content })

describe('questionBefore', () => {
  it('takes the nearest question before the answer, not the newest one', () => {
    const messages = [
      msg('user', 'where is giza'),
      msg('assistant', 'in egypt'),
      msg('user', 'and stonehenge?'),
      msg('assistant', 'in england'),
    ]
    expect(questionBefore(messages, 1)).toBe('where is giza')
    expect(questionBefore(messages, 3)).toBe('and stonehenge?')
  })

  it('returns an empty string when the chat opens with an answer', () => {
    expect(questionBefore([msg('assistant', 'restored')], 0)).toBe('')
  })
})
