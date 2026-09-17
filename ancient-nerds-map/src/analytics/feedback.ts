/**
 * Micro-feedback: the one thing analytics cannot measure is *why*, so at
 * the dead ends the site asks — an empty search, a 404 — and under every
 * piece of content it offers a thumb: site page, story, paper, journal,
 * Lyra answer. The answer travels as a `feedback` event; the free text is
 * clipped to 100 characters and never joined with anything that identifies
 * the visitor (privacy.html §2a). One rating per thing per 24 hours, kept
 * in localStorage (§3).
 */

import { type EventProps, pageType } from './index'

export type FeedbackPromptKind =
  | 'search_empty'
  | 'story_end'
  | 'not_found'
  | 'site_page'
  | 'paper_end'
  | 'journal_end'
  | 'lyra_answer'
export type FeedbackAnswer = 'yes' | 'no'

export const FEEDBACK_TEXT_MAX = 100

/** One rating per thing per day (owner's rule, 2026-09-17). */
export const FEEDBACK_RATE_LIMIT_MS = 24 * 60 * 60 * 1000
const SEEN_KEY = 'an_feedback_seen'

/** Timestamps of the things this browser rated, pruned to the last 24 h.
 *  Never throws: private mode and disabled storage are normal states. */
function readSeen(now: number): Record<string, number> {
  if (typeof window === 'undefined') return {}
  try {
    const raw = window.localStorage.getItem(SEEN_KEY)
    if (!raw) return {}
    const parsed: unknown = JSON.parse(raw)
    if (!parsed || typeof parsed !== 'object') return {}
    const fresh: Record<string, number> = {}
    for (const [key, at] of Object.entries(parsed as Record<string, unknown>)) {
      if (typeof at === 'number' && now - at < FEEDBACK_RATE_LIMIT_MS) fresh[key] = at
    }
    return fresh
  } catch {
    return {}
  }
}

function seenKey(prompt: FeedbackPromptKind, target: string): string {
  return `${prompt}:${target}`
}

/** Whether this browser already rated this thing within the last 24 hours. */
export function ratedRecently(
  prompt: FeedbackPromptKind,
  target: string,
  now: number = Date.now()
): boolean {
  return seenKey(prompt, target) in readSeen(now)
}

/** Remember the rating; writing also prunes everything older than 24 hours. */
export function markRated(
  prompt: FeedbackPromptKind,
  target: string,
  now: number = Date.now()
): void {
  if (typeof window === 'undefined') return
  const seen = readSeen(now)
  seen[seenKey(prompt, target)] = now
  try {
    window.localStorage.setItem(SEEN_KEY, JSON.stringify(seen))
  } catch {
    // Full or disabled storage only costs the throttle, never the rating.
  }
}

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
