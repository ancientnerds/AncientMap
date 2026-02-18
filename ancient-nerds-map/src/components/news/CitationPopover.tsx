/**
 * CitationPopover — Floating news card shown on citation [N] hover.
 *
 * Wraps NewsCard (size="sm") in a fixed-position container anchored
 * to the citation link. Stays open when the user mouses into the card.
 */

import { useRef, useEffect, useState } from 'react'
import NewsCard from './NewsCard'
import type { NewsCardProps } from './NewsCard'

interface CitationPopoverProps {
  cardProps: NewsCardProps
  anchorRect: DOMRect
  onMouseEnter: () => void
  onMouseLeave: () => void
}

export default function CitationPopover({
  cardProps,
  anchorRect,
  onMouseEnter,
  onMouseLeave,
}: CitationPopoverProps) {
  const ref = useRef<HTMLDivElement>(null)
  const [pos, setPos] = useState<{ top: number; left: number; flipped: boolean }>({
    top: 0, left: 0, flipped: false,
  })

  useEffect(() => {
    const el = ref.current
    if (!el) return
    const popH = el.offsetHeight
    const popW = el.offsetWidth
    const gap = 8

    // Prefer showing above the citation
    let top = anchorRect.top - popH - gap
    let flipped = false
    if (top < 8) {
      // Not enough space above — show below
      top = anchorRect.bottom + gap
      flipped = true
    }

    // Center horizontally on the citation, clamped to viewport
    let left = anchorRect.left + anchorRect.width / 2 - popW / 2
    left = Math.max(8, Math.min(left, window.innerWidth - popW - 8))

    setPos({ top, left, flipped })
  }, [anchorRect])

  return (
    <div
      ref={ref}
      className={`citation-popover${pos.flipped ? ' citation-popover--below' : ''}`}
      style={{ top: pos.top, left: pos.left }}
      onMouseEnter={onMouseEnter}
      onMouseLeave={onMouseLeave}
    >
      <NewsCard {...cardProps} size="sm" />
    </div>
  )
}
