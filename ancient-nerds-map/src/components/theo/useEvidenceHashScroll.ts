/**
 * useEvidenceHashScroll — land a #ev-NN deep link on its paragraph for real.
 *
 * Video descriptions link evidence as /research/{slug}#ev-NN. The browser
 * jumps to the anchor while parsing the server HTML, but the hero and the
 * body images have no reserved height, so every image that loads above the
 * target pushes it down again (Chrome's scroll anchoring may compensate,
 * Safari has none). This effect waits until the images above the target that
 * are still loading have settled and scrolls once more. Effects never run
 * during server rendering, so the SSR markup is untouched.
 *
 * The re-scroll belongs to the link, never to the reader: it is dropped once
 * the reader scrolls, touches, clicks or types, and when the hash changes (an
 * in-page link such as "Corrected …" or a reference).
 */

import { useEffect } from 'react'

/**
 * The anchors a paper page hands out: evidence paragraphs and the corrections log.
 * The ev-NN part mirrors pipeline.lyra.theo_publishing.EVIDENCE_ID_RE (`ev-[0-9]{2,}`,
 * applied with fullmatch), the one definition of the evidence-id format; change both
 * together. A JavaScript `\d` always means [0-9], so it accepts exactly the same ids.
 */
const PAPER_HASH_RE = /^#(ev-\d{2,}|corrections)$/

/**
 * Every way a reader takes over the page: the wheel, a touch, a pointer press
 * (which includes dragging the scrollbar), a key (arrows, Page Down, Space,
 * Tab), and a hash change from an in-page link.
 */
const READER_INTENT_EVENTS = ['wheel', 'touchstart', 'pointerdown', 'keydown', 'hashchange'] as const

export function useEvidenceHashScroll(): void {
  useEffect(() => {
    const match = PAPER_HASH_RE.exec(window.location.hash)
    if (!match) return
    // A reload or a back/forward step is no exception: the paper scrolls inside
    // .theo-page (theo.css), whose position no browser restores, so those
    // start like a fresh visit and need the same re-scroll. A page restored
    // from the back/forward cache is not mounted again and runs no effect.
    // The hash comes from the address bar: an id the paper does not have is
    // a stale link, not an error — the browser's own jump did nothing either.
    const target = document.getElementById(match[1])
    if (target === null) return
    // Only an image before the target in document order can push it down, and
    // a lazy image off-screen never loads, so waiting for it would never end.
    const pending = Array.from(document.querySelectorAll<HTMLImageElement>('.theo-page img')).filter(
      img =>
        !img.complete &&
        img.getAttribute('loading') !== 'lazy' &&
        (img.compareDocumentPosition(target) & Node.DOCUMENT_POSITION_FOLLOWING) !== 0,
    )
    let cancelled = false
    const detachImages: Array<() => void> = []
    const stop = () => {
      cancelled = true
      for (const type of READER_INTENT_EVENTS) window.removeEventListener(type, stop, true)
      for (const detach of detachImages) detach()
    }
    for (const type of READER_INTENT_EVENTS) {
      window.addEventListener(type, stop, { capture: true, passive: true })
    }
    void Promise.all(
      pending.map(
        img =>
          new Promise<void>(resolve => {
            const settle = () => resolve()
            img.addEventListener('load', settle, { once: true })
            img.addEventListener('error', settle, { once: true })
            detachImages.push(() => {
              img.removeEventListener('load', settle)
              img.removeEventListener('error', settle)
            })
          }),
      ),
    ).then(() => {
      if (cancelled) return
      stop()
      target.scrollIntoView({ block: 'start' })
    })
    return stop
  }, [])
}
