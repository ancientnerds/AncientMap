/**
 * Draggable floating site popup for Lyra chat.
 * Unlike SitePopupOverlay, this doesn't block interaction with the chat behind it.
 */
import { lazy, Suspense, useCallback, useState, useRef, useEffect } from 'react'
import { createPortal } from 'react-dom'
import type { SiteData } from '../data/sites'

const SitePopup = lazy(() => import('./SitePopup'))

export function LyraSitePopup({ site, onClose }: { site: SiteData; onClose: () => void }) {
  const handleAskLyra = useCallback((_type: string, id: string) => {
    window.open(`/lyra.html?site=${id}`, '_blank')
  }, [])

  const [pos, setPos] = useState(() => ({
    x: Math.max(20, (window.innerWidth - 420) / 2),
    y: Math.max(20, window.innerHeight * 0.08),
  }))
  const [isDragging, setIsDragging] = useState(false)
  const dragStart = useRef({ mx: 0, my: 0, px: 0, py: 0 })

  const onDragStart = useCallback((e: React.MouseEvent | React.TouchEvent) => {
    e.preventDefault()
    setIsDragging(true)
    const clientX = 'touches' in e ? e.touches[0].clientX : e.clientX
    const clientY = 'touches' in e ? e.touches[0].clientY : e.clientY
    dragStart.current = { mx: clientX, my: clientY, px: pos.x, py: pos.y }
  }, [pos.x, pos.y])

  useEffect(() => {
    if (!isDragging) return
    const onMove = (e: MouseEvent | TouchEvent) => {
      const clientX = 'touches' in e ? e.touches[0].clientX : e.clientX
      const clientY = 'touches' in e ? e.touches[0].clientY : e.clientY
      const dx = clientX - dragStart.current.mx
      const dy = clientY - dragStart.current.my
      setPos({
        x: Math.max(0, dragStart.current.px + dx),
        y: Math.max(0, dragStart.current.py + dy),
      })
    }
    const onUp = () => setIsDragging(false)
    window.addEventListener('mousemove', onMove)
    window.addEventListener('mouseup', onUp)
    window.addEventListener('touchmove', onMove, { passive: false })
    window.addEventListener('touchend', onUp)
    return () => {
      window.removeEventListener('mousemove', onMove)
      window.removeEventListener('mouseup', onUp)
      window.removeEventListener('touchmove', onMove)
      window.removeEventListener('touchend', onUp)
    }
  }, [isDragging])

  return createPortal(
    <div
      className={`lyra-site-popup-float${isDragging ? ' dragging' : ''}`}
      style={{ left: pos.x, top: pos.y }}
    >
      <div className="lyra-site-popup-dragbar" onMouseDown={onDragStart} onTouchStart={onDragStart}>
        <span className="lyra-site-popup-dragbar-title">{site.title}</span>
        <button className="lyra-site-popup-dragbar-close" onClick={onClose}>
          <svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.5">
            <line x1="2" y1="2" x2="10" y2="10" /><line x1="10" y1="2" x2="2" y2="10" />
          </svg>
        </button>
      </div>
      <div className="lyra-site-popup-body">
        <Suspense fallback={null}>
          <SitePopup
            site={site}
            onClose={onClose}
            isStandalone={true}
            onAskLyra={handleAskLyra}
          />
        </Suspense>
      </div>
    </div>,
    document.body
  )
}
