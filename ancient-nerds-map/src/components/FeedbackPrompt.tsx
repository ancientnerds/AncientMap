/**
 * FeedbackPrompt — one question at a dead end, answered in a tap.
 *
 * Two shapes, one component: a yes/no pair with an optional line of text
 * (story end: "Was this useful?"), or the text alone (empty search: "What
 * were you looking for?"). A tap on Yes/No is recorded at once — most
 * people stop there — and the text, if any, follows as a second event.
 * Server-rendered pages hydrate it; nothing here touches the window during
 * render.
 */
import { useState } from 'react'

import { track } from '../analytics'
import { type FeedbackAnswer, type FeedbackPromptKind, FEEDBACK_TEXT_MAX, feedbackPayload } from '../analytics/feedback'
import '../styles/feedback-prompt.css'

interface FeedbackPromptProps {
  prompt: FeedbackPromptKind
  question: string
  placeholder?: string
  /** Show the Yes/No pair before the text line. */
  yesNo?: boolean
}

export default function FeedbackPrompt({
  prompt,
  question,
  placeholder = 'Optional: a few words',
  yesNo = false,
}: FeedbackPromptProps) {
  const [answer, setAnswer] = useState<FeedbackAnswer | null>(null)
  const [text, setText] = useState('')
  const [sent, setSent] = useState(false)

  const choose = (value: FeedbackAnswer) => {
    setAnswer(value)
    track('feedback', feedbackPayload(prompt, value, '', window.location.pathname))
  }
  const submit = () => {
    if (!text.trim()) return
    track('feedback', feedbackPayload(prompt, answer, text, window.location.pathname))
    setSent(true)
  }

  if (sent) {
    return (
      <div className="feedback-prompt feedback-prompt--sent" role="status">
        Thanks — noted.
      </div>
    )
  }

  return (
    <form
      className="feedback-prompt"
      onSubmit={e => {
        e.preventDefault()
        submit()
      }}
    >
      <p className="feedback-prompt-q">{answer ? 'Thanks. Anything to add?' : question}</p>
      {yesNo && !answer && (
        <div className="feedback-prompt-choice" role="group" aria-label={question}>
          <button type="button" onClick={() => choose('yes')}>
            Yes
          </button>
          <button type="button" onClick={() => choose('no')}>
            No
          </button>
        </div>
      )}
      {(!yesNo || answer) && (
        <div className="feedback-prompt-row">
          <input
            type="text"
            maxLength={FEEDBACK_TEXT_MAX}
            value={text}
            onChange={e => setText(e.target.value)}
            placeholder={placeholder}
            aria-label={question}
            autoComplete="off"
          />
          <button type="submit" disabled={!text.trim()}>
            Send
          </button>
        </div>
      )}
    </form>
  )
}
