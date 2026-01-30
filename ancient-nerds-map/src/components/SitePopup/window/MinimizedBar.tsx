import type { MinimizedBarProps } from '../types'

export function MinimizedBar({
  title,
  siteId,
  coordinates,
  isEmpireMode = false,
  onRestore,
  onClose,
  onHighlight,
  onSelect,
  onFlyTo,
  tooltipPinnedRef
}: MinimizedBarProps) {
  return (
    <div
      className={`popup-minimized-bar ${isEmpireMode ? 'empire-mode' : ''}`}
      onMouseEnter={() => {
        tooltipPinnedRef.current = false // Reset pin on re-enter for hover behavior
        onHighlight?.(siteId)
      }}
      onMouseLeave={() => {
        // Only clear highlight if not pinned by click
        if (!tooltipPinnedRef.current) {
          onHighlight?.(null)
        }
      }}
      onClick={(e) => {
        tooltipPinnedRef.current = true // Pin the tooltip
        onSelect?.(siteId, e.ctrlKey || e.metaKey) // Select with multi-select support
        onFlyTo?.(coordinates)
      }}
    >
      <svg className="popup-minimized-icon" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <circle cx="12" cy="10" r="3"/>
        <path d="M12 21.7C17.3 17 20 13 20 10a8 8 0 1 0-16 0c0 3 2.7 7 8 11.7z"/>
      </svg>
      <span className="popup-minimized-title">{title}</span>
      <button
        className="popup-minimized-btn"
        onClick={onRestore}
        title="Restore"
      >
        <svg width="10" height="10" viewBox="0 0 10 10" fill="none" stroke="currentColor" strokeWidth="1.5">
          <rect x="1" y="1" width="8" height="8" rx="1" />
        </svg>
      </button>
      <button
        className="popup-minimized-btn close-btn"
        onClick={(e) => { e.stopPropagation(); onClose(e); }}
        title="Close"
      >
        <svg width="10" height="10" viewBox="0 0 10 10" fill="none" stroke="currentColor" strokeWidth="1.5">
          <line x1="2" y1="2" x2="8" y2="8" />
          <line x1="8" y1="2" x2="2" y2="8" />
        </svg>
      </button>
    </div>
  )
}
