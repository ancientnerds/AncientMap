/**
 * AnswerFeedback — thumbs up / down under a finished Lyra answer.
 *
 * One tap records a `feedback` event with prompt `lyra_answer`; the event
 * carries the verdict and the length of the question, never its text
 * (privacy.html §2a). The window is only read in the click handler, so the
 * component is safe to render on the server.
 */
import { useState } from 'react'

import { type EventProps, pageType, track } from '../../analytics'
import type { FeedbackAnswer } from '../../analytics/feedback'
import '../../styles/feedback-prompt.css'

/** Props of the lyra_answer feedback event: verdict + question length only. */
export function answerFeedbackProps(answer: FeedbackAnswer, question: string, pathname: string): EventProps {
  return { prompt: 'lyra_answer', answer, chars: question.trim().length, page: pageType(pathname) }
}

/** The user message that produced the answer at `index`: the nearest one
 * before it in the list ('' when the answer opened the chat, e.g. a
 * restored conversation that starts with an assistant turn). */
export function questionBefore(messages: ReadonlyArray<{ role: string; content: string }>, index: number): string {
  for (let i = index - 1; i >= 0; i--) {
    if (messages[i].role === 'user') return messages[i].content
  }
  return ''
}

interface Props {
  question: string
}

/** Two small buttons under a finished answer; one tap, then "Thanks". */
export default function AnswerFeedback({ question }: Props) {
  const [done, setDone] = useState<FeedbackAnswer | null>(null)
  if (done) return <span className="lyra-answer-feedback lyra-answer-feedback--done">Thanks</span>
  const vote = (answer: FeedbackAnswer) => {
    track('feedback', answerFeedbackProps(answer, question, window.location.pathname))
    setDone(answer)
  }
  return (
    <span className="lyra-answer-feedback" role="group" aria-label="Was this answer helpful?">
      <button type="button" onClick={() => vote('yes')} aria-label="Helpful">
        {'👍'}
      </button>
      <button type="button" onClick={() => vote('no')} aria-label="Not helpful">
        {'👎'}
      </button>
    </span>
  )
}
