import type { WindowControlsProps } from '../types'

export function WindowControls({
  windowState,
  siteId,
  isEmpireMode,
  onMinimize,
  onMaximize,
  onClose
}: WindowControlsProps) {
  return (
    <div className="popup-window-controls">
      {siteId && !isEmpireMode && (
        <a
          href={`/site.html?id=${siteId}`}
          target="_blank"
          rel="noopener noreferrer"
          className="popup-window-btn"
          title="Open in new tab"
          onClick={(e) => e.stopPropagation()}
          onMouseDown={(e) => e.stopPropagation()}
        >
          <svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.5">
            <path d="M9 6.5v3a1 1 0 0 1-1 1H2.5a1 1 0 0 1-1-1V5a1 1 0 0 1 1-1H5.5" />
            <path d="M7 1.5h3.5V5" />
            <line x1="5" y1="7" x2="10.5" y2="1.5" />
          </svg>
        </a>
      )}
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
