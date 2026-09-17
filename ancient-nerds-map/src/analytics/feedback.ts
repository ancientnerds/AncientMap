/**
 * Micro-feedback: the one thing analytics cannot measure is *why*, so at
 * three dead ends the site asks — an empty search, a 404, the end of a
 * story. The answer travels as a `feedback` event; the free text is
 * clipped to 100 characters and never joined with anything that identifies
 * the visitor (privacy.html §2a).
 */

import { type EventProps, pageType } from './index'

export type FeedbackPromptKind = 'search_empty' | 'story_end' | 'not_found'
export type FeedbackAnswer = 'yes' | 'no'

export const FEEDBACK_TEXT_MAX = 100

/** Event props for one feedback submission; empty text and missing answer are omitted. */
export function feedbackPayload(
  prompt: FeedbackPromptKind,
  answer: FeedbackAnswer | null,
  text: string,
  pathname: string
): EventProps {
  const clipped = text.replace(/\s+/g, ' ').trim().slice(0, FEEDBACK_TEXT_MAX)
  return {
    prompt,
    answer: answer ?? undefined,
    text: clipped || undefined,
    page: pageType(pathname),
  }
}
