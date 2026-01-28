/**
 * MapboxOfflineWarning - Warning banner shown when satellite tiles are not available offline
 */

import React from 'react'

interface MapboxOfflineWarningProps {
  visible: boolean
  onDownload?: () => void
  onDismiss: () => void
}

export function MapboxOfflineWarning({
  visible,
  onDownload,
  onDismiss,
}: MapboxOfflineWarningProps): React.ReactElement | null {
  if (!visible) return null

  return (
    <div className="mapbox-offline-warning">
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/>
        <line x1="12" y1="9" x2="12" y2="13"/>
        <line x1="12" y1="17" x2="12.01" y2="17"/>
      </svg>
      <span>Satellite tiles not available offline</span>
      {onDownload && (
        <button className="mapbox-warning-btn" onClick={onDownload}>
          Download Basemap
        </button>
      )}
      <button className="mapbox-warning-close" onClick={onDismiss}>
        ×
      </button>
    </div>
  )
}
