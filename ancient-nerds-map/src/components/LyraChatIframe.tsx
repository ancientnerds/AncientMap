/**
 * LyraChatIframe — Opens Open WebUI in a modal iframe overlay.
 * Replaces the old custom LyraChatModal with the Open WebUI interface.
 */

import { createPortal } from 'react-dom'

interface Props {
  isOpen: boolean
  onClose: () => void
}

const CHAT_URL = '/chat/'

export default function LyraChatIframe({ isOpen, onClose }: Props) {
  if (!isOpen) return null

  return createPortal(
    <div
      className="lyra-iframe-overlay"
      onClick={(e) => { if (e.target === e.currentTarget) onClose() }}
    >
      <div className="lyra-iframe-container">
        <button className="lyra-iframe-close" onClick={onClose} title="Close">
          <svg width="14" height="14" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.5">
            <line x1="2" y1="2" x2="10" y2="10" /><line x1="10" y1="2" x2="2" y2="10" />
          </svg>
        </button>
        <iframe
          src={CHAT_URL}
          title="Lyra Chat"
          className="lyra-iframe"
          allow="clipboard-write"
        />
      </div>
    </div>,
    document.body,
  )
}
