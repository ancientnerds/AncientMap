import { describe, expect, it } from 'vitest'

import { answerFeedbackProps, questionBefore } from '../AnswerFeedback'

describe('answerFeedbackProps', () => {
  it('sends the verdict, the question length and the page — never the question', () => {
    expect(answerFeedbackProps('no', 'where is göbekli tepe', '/lyra.html')).toEqual({
      prompt: 'lyra_answer',
      answer: 'no',
      chars: 21,
      page: 'lyra',
    })
  })

  it('counts the trimmed question', () => {
    expect(answerFeedbackProps('yes', '  hi  ', '/globe.html').chars).toBe(2)
  })
})

describe('questionBefore', () => {
  const messages = [
    { role: 'user', content: 'first question' },
    { role: 'assistant', content: 'first answer' },
    { role: 'user', content: 'second question' },
    { role: 'assistant', content: 'second answer' },
  ]

  it('returns the user message nearest before the answer, not the latest one', () => {
    expect(questionBefore(messages, 1)).toBe('first question')
    expect(questionBefore(messages, 3)).toBe('second question')
  })

  it('is empty when no user message precedes the answer', () => {
    expect(questionBefore([{ role: 'assistant', content: 'hello' }], 0)).toBe('')
  })
})
