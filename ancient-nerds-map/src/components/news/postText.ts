/**
 * post_text is the text Lyra writes for POSTING — a tweet. It ends with the
 * bare source URL, which is right for a timeline and wrong in an article:
 * the story page renders the same field as its body, so the link sat in the
 * middle of the prose as plain, unclickable text (reported 2026-08-21).
 *
 * Splitting it here keeps the prose readable and hands the URL back to the
 * caller, which can render it as an actual link instead of dropping it.
 */

/** A URL at the very end of the text, with the whitespace in front of it. */
const TRAILING_URL = /\s*(https?:\/\/\S+)\s*$/

export interface SplitPostText {
  /** The prose, split on newlines, without the trailing link(s). */
  paragraphs: string[]
  /** Trailing URLs in the order they appeared. */
  links: string[]
}

/**
 * Only TRAILING urls are pulled out. A link inside a sentence is part of the
 * sentence and stays where the author put it; the tweet convention is to
 * append the source, and that is the only case this touches.
 */
export function splitPostText(postText: string): SplitPostText {
  let body = postText.trim()
  const links: string[] = []

  for (let match = body.match(TRAILING_URL); match; match = body.match(TRAILING_URL)) {
    // Trailing sentence punctuation is not part of the URL.
    links.unshift(match[1].replace(/[.,;:)]+$/, ''))
    body = body.slice(0, match.index).trimEnd()
  }

  return {
    paragraphs: body.split('\n').map(p => p.trim()).filter(Boolean),
    links,
  }
}
