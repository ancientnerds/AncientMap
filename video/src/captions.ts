/**
 * Hook captions: timeline.captions holds one entry per displayed word
 * ({text, from, to}, the script's spelling, uppercase). They are grouped into
 * short lines; a line stays up until the next one starts (or HOLD_FRAMES after
 * its last word) and the word being spoken is highlighted. Also the evidence
 * ticker's counter and the in-frame credit line.
 */
import type { Caption, TickerStep } from './timeline'

export type CaptionLine = { words: Caption[]; from: number; to: number }

/**
 * The longest hook caption line in characters, its words joined by single spaces.
 * HookCaptions draws a line on one row (nowrap) in ZONES.caption, 1440 px wide, in
 * heading(64): Orbitron 700, upper case, 0.06em spacing, about 56 px per capital.
 * Plan C's script check reads this line with a regex and refuses a hook word longer
 * than this, the one line no break can shorten; lint.ts stays the final guard.
 */
export const HOOK_LINE_MAX_CHARS = 24
const MAX_WORDS = 4
/** A pause longer than this between two words starts a new line. */
const GAP_FRAMES = 12
const HOLD_FRAMES = 10

/** Characters of a line: its words joined by single spaces. */
const lineChars = (words: readonly Caption[]) => words.map((w) => w.text).join(' ').length

export function captionLines(captions: readonly Caption[], maxWords = MAX_WORDS, maxChars = HOOK_LINE_MAX_CHARS): CaptionLine[] {
  const lines: CaptionLine[] = []
  let current: Caption[] = []
  const flush = () => {
    if (current.length) lines.push({ words: current, from: current[0].from, to: current[current.length - 1].to })
    current = []
  }
  captions.forEach((c, i) => {
    const prev = captions[i - 1]
    const full = current.length >= maxWords || lineChars([...current, c]) > maxChars
    if (current.length && (full || c.from - prev.to > GAP_FRAMES)) flush()
    current.push(c)
    if (/[.!?,;:]$/.test(c.text)) flush()
  })
  flush()
  return lines
}

/** The line on screen at `frame`, or null. */
export function lineAt(lines: readonly CaptionLine[], frame: number): CaptionLine | null {
  for (let i = 0; i < lines.length; i++) {
    const next = lines[i + 1]
    const end = Math.min(lines[i].to + HOLD_FRAMES, next ? next.from : Number.POSITIVE_INFINITY)
    if (frame >= lines[i].from && frame < end) return lines[i]
  }
  return null
}

/** Evidence counter at `frame`: the count so far, the count before the last change and when it changed. */
export function tickerAt(steps: readonly TickerStep[], frame: number): { n: number; previous: number; since: number } {
  let n = 0
  let previous = 0
  let since = -1
  for (const s of steps) {
    if (s.frame > frame) break
    if (s.n !== n) {
      previous = n
      since = s.frame
    }
    n = s.n
  }
  return { n, previous, since }
}

/**
 * One credit line from a scene's credits. "©" statements are split into their
 * parts and repeated parts dropped, so the capture's "© Mapbox © OpenStreetMap
 * © Maxar" and the script's "© Mapbox © Maxar" read "© Mapbox © OpenStreetMap
 * © Maxar"; other credits (photo licences, source pages) come first, separated
 * by " · ".
 */
export function mergeCredits(texts: readonly string[]): string {
  const others: string[] = []
  const copyrights: string[] = []
  for (const text of texts) {
    for (const part of text.split(/(?=©)/)) {
      const clean = part.trim()
      const list = clean.startsWith('©') ? copyrights : others
      if (clean && !list.includes(clean)) list.push(clean)
    }
  }
  return [...others, copyrights.join(' ')].filter(Boolean).join(' · ')
}
