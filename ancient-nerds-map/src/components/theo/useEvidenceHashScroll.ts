/**
 * useEvidenceHashScroll — land a #ev-NN deep link on its paragraph for real.
 *
 * Video descriptions link evidence as /research/{slug}#ev-NN. The browser
 * jumps to the anchor while parsing the server HTML, but the hero and the
 * body images have no reserved height, so every image that loads above the
 * target pushes it down again (Chrome's scroll anchoring may compensate,
 * Safari has none). This effect waits until the images that are still
 * loading have settled and scrolls once more. Effects never run during
 * server rendering, so the SSR markup is untouched.
 */

import { useEffect } from 'react'

/**
 * The anchors a paper page hands out: evidence paragraphs and the corrections log.
 * The ev-NN part mirrors pipeline.lyra.theo_publishing.EVIDENCE_ID_RE (`ev-[0-9]{2,}`,
 * applied with fullmatch), the one definition of the evidence-id format; change both
 * together. A JavaScript `\d` always means [0-9], so it accepts exactly the same ids.
 */
const PAPER_HASH_RE = /^#(ev-\d{2,}|corrections)$/

export function useEvidenceHashScroll(): void {
  useEffect(() => {
    const match = PAPER_HASH_RE.exec(window.location.hash)
    if (!match) return
    const targetId = match[1]
    // A lazy image off-screen never loads, so waiting for it would never end.
    const pending = Array.from(document.querySelectorAll<HTMLImageElement>('.theo-page img')).filter(
      img => !img.complete && img.getAttribute('loading') !== 'lazy',
    )
    let cancelled = false
    void Promise.all(
      pending.map(
        img =>
          new Promise<void>(resolve => {
            img.addEventListener('load', () => resolve(), { once: true })
            img.addEventListener('error', () => resolve(), { once: true })
          }),
      ),
    ).then(() => {
      if (cancelled) return
      // The hash comes from the address bar: an id the paper does not have is
      // a stale link, not an error — the browser's own jump did nothing either.
      document.getElementById(targetId)?.scrollIntoView({ block: 'start' })
    })
    return () => {
      cancelled = true
    }
  }, [])
}
