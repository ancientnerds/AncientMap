/**
 * CitationPopover — Floating news card shown on citation [N] hover or click-pin.
 *
 * Wraps NewsCard (size="sm") in a fixed-position container anchored
 * to the citation link. Stays open when the user mouses into the card.
 * When pinned: shows X close button, is draggable, doesn't auto-dismiss.
 */

import { useRef, useEffect, useState, useCallback } from 'react'
import NewsCard from './NewsCard'
import type { NewsCardProps } from './NewsCard'

interface CitationPopoverProps {
  cardProps: NewsCardProps
  anchorRect: DOMRect
  onMouseEnter: () => void
  onMouseLeave: () => void
  pinned?: boolean
  onClose?: () => void
}

export default function CitationPopover({
  cardProps,
  anchorRect,
  onMouseEnter,
  onMouseLeave,
  pinned,
  onClose,
}: CitationPopoverProps) {
  const ref = useRef<HTMLDivElement>(null)
  const [pos, setPos] = useState<{ top: number; left: number; flipped: boolean }>({
    top: 0, left: 0, flipped: false,
  })
  const [dragOffset, setDragOffset] = useState<{ x: number; y: number }>({ x: 0, y: 0 })
  const dragging = useRef(false)
  const dragStart = useRef<{ x: number; y: number; ox: number; oy: number }>({ x: 0, y: 0, ox: 0, oy: 0 })

  useEffect(() => {
    const el = ref.current
    if (!el) return
    const popH = el.offsetHeight
    const popW = el.offsetWidth
    const gap = 8

    let top = anchorRect.top - popH - gap
    let flipped = false
    if (top < 8) {
      top = anchorRect.bottom + gap
      flipped = true
    }

    let left = anchorRect.left + anchorRect.width / 2 - popW / 2
    left = Math.max(8, Math.min(left, window.innerWidth - popW - 8))

    setPos({ top, left, flipped })
    setDragOffset({ x: 0, y: 0 })
  }, [anchorRect])

  const onDragStart = useCallback((e: React.MouseEvent) => {
    if (!pinned) return
    e.preventDefault()
    dragging.current = true
    dragStart.current = { x: e.clientX, y: e.clientY, ox: dragOffset.x, oy: dragOffset.y }

    const onMove = (ev: MouseEvent) => {
      if (!dragging.current) return
      setDragOffset({
        x: dragStart.current.ox + (ev.clientX - dragStart.current.x),
        y: dragStart.current.oy + (ev.clientY - dragStart.current.y),
      })
    }
    const onUp = () => {
      dragging.current = false
      document.removeEventListener('mousemove', onMove)
      document.removeEventListener('mouseup', onUp)
    }
    document.addEventListener('mousemove', onMove)
    document.addEventListener('mouseup', onUp)
  }, [pinned, dragOffset])

  const className = [
    'citation-popover',
    pos.flipped ? 'citation-popover--below' : '',
    pinned ? 'citation-popover--pinned' : '',
  ].filter(Boolean).join(' ')

  return (
    <div
      ref={ref}
      className={className}
      style={{
        top: pos.top + dragOffset.y,
        left: pos.left + dragOffset.x,
      }}
      onMouseEnter={pinned ? undefined : onMouseEnter}
      onMouseLeave={pinned ? undefined : onMouseLeave}
    >
      {pinned && (
        <div className="citation-popover-header" onMouseDown={onDragStart}>
          <button className="citation-popover-close" onClick={onClose} title="Close">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
              <line x1="18" y1="6" x2="6" y2="18" />
              <line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        </div>
      )}
      <NewsCard {...cardProps} size="sm" />
    </div>
  )
}
