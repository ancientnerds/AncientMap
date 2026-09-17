/**
 * ThumbsFeedback — one tap to rate a thing, one box to say why.
 *
 * The same control under every piece of content: a site page, a story, a
 * paper, a journal, a Lyra answer. Up records and thanks; down records and
 * opens a small box, because a complaint without a sentence is a number we
 * cannot act on. The vote is sent the moment it is given, so an unfinished
 * comment never costs us the verdict.
 *
 * One rating per thing per 24 hours (owner's rule, 2026-09-17): the marker
 * lives in localStorage and says nothing about the visitor — see
 * privacy.html §3. Nothing here touches the window during render, so the
 * server-rendered pages hydrate it without a mismatch.
 */
import { useState } from 'react'

import { type EventProps, track } from '../../analytics'
import {
  type FeedbackAnswer,
  FEEDBACK_TEXT_MAX,
  type FeedbackPromptKind,
  feedbackPayload,
  markRated,
  ratedRecently,
} from '../../analytics/feedback'
import '../../styles/feedback-prompt.css'

interface ThumbsFeedbackProps {
  prompt: FeedbackPromptKind
  /** What is being rated — a site id, a slug, a message key. Only used to
   *  throttle; it is not part of the event unless `extra` carries it. */
  target: string
  /** The question, e.g. "Was this page useful?". */
  question: string
  /** Placeholder of the box that opens on a thumbs down. */
  placeholder?: string
  /** Event props on top of prompt/answer/text/page (e.g. the site id). */
  extra?: EventProps
  /** `inline` sits in a line of text (Lyra answers); `block` is a panel. */
  variant?: 'block' | 'inline'
}

export default function ThumbsFeedback({
  prompt,
  target,
  question,
  placeholder = 'What was missing?',
  extra,
  variant = 'block',
}: ThumbsFeedbackProps) {
  // Lazy initial state: reads storage once, on the client, after hydration.
  const [muted] = useState(() => ratedRecently(prompt, target))
  const [stage, setStage] = useState<'ask' | 'comment' | 'done'>('ask')
  const [text, setText] = useState('')

  if (muted) return null

  const send = (answer: FeedbackAnswer, comment = '') => {
    track('feedback', { ...feedbackPayload(prompt, answer, comment, window.location.pathname), ...extra })
  }

  const vote = (answer: FeedbackAnswer) => {
    send(answer)
    markRated(prompt, target)
    setStage(answer === 'yes' ? 'done' : 'comment')
  }

  const submit = () => {
    if (text.trim()) send('no', text)
    setStage('done')
  }

  const cls = `thumbs-feedback thumbs-feedback--${variant}`

  if (stage === 'done') {
    return (
      <p className={`${cls} thumbs-feedback--done`} role="status">
        Thanks — noted.
      </p>
    )
  }

  if (stage === 'comment') {
    return (
      <form
        className={cls}
        onSubmit={e => {
          e.preventDefault()
          submit()
        }}
      >
        <label className="thumbs-feedback-q" htmlFor={`tf-${prompt}`}>
          What would have made it better?
        </label>
        <div className="thumbs-feedback-row">
          <input
            id={`tf-${prompt}`}
            type="text"
            maxLength={FEEDBACK_TEXT_MAX}
            value={text}
            onChange={e => setText(e.target.value)}
            placeholder={placeholder}
            autoComplete="off"
          />
          <button type="submit">{text.trim() ? 'Send' : 'Skip'}</button>
        </div>
      </form>
    )
  }

  return (
    <div className={cls} role="group" aria-label={question}>
      <span className="thumbs-feedback-q">{question}</span>
      <span className="thumbs-feedback-buttons">
        <button type="button" onClick={() => vote('yes')} aria-label="Yes">
          {'\u{1F44D}'}
        </button>
        <button type="button" onClick={() => vote('no')} aria-label="No">
          {'\u{1F44E}'}
        </button>
      </span>
    </div>
  )
}
