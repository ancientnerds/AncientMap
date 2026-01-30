import type { WindowControlsProps } from '../types'

export function WindowControls({
  windowState,
  onMinimize,
  onMaximize,
  onClose
}: WindowControlsProps) {
  return (
    <div className="popup-window-controls">
      <button
        className="popup-window-btn"
        onClick={onMinimize}
        title="Minimize"
      >
        <svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.5">
          <line x1="2" y1="6" x2="10" y2="6" />
        </svg>
      </button>
      <button
        className="popup-window-btn"
        onClick={onMaximize}
        title={windowState === 'maximized' ? 'Restore' : 'Maximize'}
      >
        {windowState === 'maximized' ? (
          <svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.5">
            <rect x="3" y="1" width="7" height="7" rx="1" />
            <path d="M1 3v6a1 1 0 001 1h6" />
          </svg>
        ) : (
          <svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.5">
            <rect x="2" y="2" width="8" height="8" rx="1" />
          </svg>
        )}
      </button>
      <button
        className="popup-window-btn close-btn"
        onClick={onClose}
        title="Close"
      >
        <svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.5">
          <line x1="2" y1="2" x2="10" y2="10" />
          <line x1="10" y1="2" x2="2" y2="10" />
        </svg>
      </button>
    </div>
  )
}
