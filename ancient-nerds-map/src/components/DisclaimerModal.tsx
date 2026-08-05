import { memo, useEffect, useRef } from 'react'
import { createPortal } from 'react-dom'
import { getDisclaimerHTML } from '../shared/disclaimerContent'

declare const __BUILD_HASH__: string
declare const __BUILD_TIME__: string

interface DisclaimerModalProps {
  isOpen: boolean
  onClose: () => void
}

function DisclaimerModal({ isOpen, onClose }: DisclaimerModalProps) {
  const contentRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!isOpen || !contentRef.current) return
    // Toggle open class on <details> elements for chevron rotation
    const details = contentRef.current.querySelectorAll('details.disclaimer-section')
    const handler = (e: Event) => {
      const el = e.currentTarget as HTMLDetailsElement
      // Use timeout so the class applies after the browser toggles [open]
      setTimeout(() => el.classList.toggle('open', el.open), 0)
    }
    details.forEach(d => {
      d.addEventListener('toggle', handler)
      if ((d as HTMLDetailsElement).open) d.classList.add('open')
    })
    return () => { details.forEach(d => d.removeEventListener('toggle', handler)) }
  }, [isOpen])

  if (!isOpen) return null

  const modalContent = (
    <div className="disclaimer-modal-overlay" onClick={onClose}>
      <div className="disclaimer-modal" onClick={e => e.stopPropagation()}>
        <button className="popup-close" onClick={onClose} title="Close">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <line x1="18" y1="6" x2="6" y2="18"></line>
            <line x1="6" y1="6" x2="18" y2="18"></line>
          </svg>
        </button>
        <div
          className="disclaimer-content"
          ref={contentRef}
          dangerouslySetInnerHTML={/* nosemgrep: semgrep.tsx-dangerously-set-inner-html -- static HTML from build-time constants, no user input */ { __html: getDisclaimerHTML(__BUILD_HASH__, __BUILD_TIME__) }}
        />
      </div>
    </div>
  )

  return createPortal(modalContent, document.body)
}

export default memo(DisclaimerModal)
