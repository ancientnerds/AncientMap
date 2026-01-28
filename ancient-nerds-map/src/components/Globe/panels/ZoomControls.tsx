/**
 * ZoomControls - Vertical zoom slider with play/pause and fullscreen buttons
 * Controls the globe zoom level and rotation playback
 */

interface ZoomControlsProps {
  zoom: number
  setZoom: (updater: number | ((prev: number) => number)) => void
  isPlaying: boolean
  onTogglePlay: () => void
  isFullscreen: boolean
  onToggleFullscreen: () => void
}

export function ZoomControls({
  zoom,
  setZoom,
  isPlaying,
  onTogglePlay,
  isFullscreen,
  onToggleFullscreen,
}: ZoomControlsProps) {
  return (
    <div className="zoom-slider-top">
      <div className="zoom-percent-display">
        {zoom}%
      </div>
      <button
        className="zoom-btn"
        onClick={() => setZoom(z => Math.min(100, z + 1))}
      >+</button>
      <div className="zoom-slider-wrapper">
        <div className="zoom-slider-labels">
          <span className="zoom-label zoom-label-map">Map</span>
          <span className="zoom-label zoom-label-3d">3D Globe</span>
        </div>
        <div className="zoom-slider-container">
          <div className="zoom-66-marker" />
          <input
            type="range"
            min="0"
            max="100"
            step="1"
            value={zoom}
            onChange={(e) => setZoom(Number(e.target.value))}
            className="zoom-range-vertical"
          />
        </div>
      </div>
      <button
        className="zoom-btn"
        onClick={() => setZoom(z => Math.max(0, z - 1))}
      >−</button>
      <button className="zoom-btn" onClick={onTogglePlay}>
        {isPlaying ? (
          <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
            <rect x="6" y="4" width="4" height="16" rx="1" />
            <rect x="14" y="4" width="4" height="16" rx="1" />
          </svg>
        ) : (
          <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
            <polygon points="5,3 19,12 5,21" />
          </svg>
        )}
      </button>
      <button className="zoom-btn" onClick={onToggleFullscreen} title={isFullscreen ? 'Exit Fullscreen' : 'Enter Fullscreen'}>
        {isFullscreen ? (
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M8 3v3a2 2 0 0 1-2 2H3m18 0h-3a2 2 0 0 1-2-2V3m0 18v-3a2 2 0 0 1 2-2h3M3 16h3a2 2 0 0 1 2 2v3" />
          </svg>
        ) : (
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M8 3H5a2 2 0 0 0-2 2v3m18 0V5a2 2 0 0 0-2-2h-3m0 18h3a2 2 0 0 0 2-2v-3M3 16v3a2 2 0 0 0 2 2h3" />
          </svg>
        )}
      </button>
    </div>
  )
}
