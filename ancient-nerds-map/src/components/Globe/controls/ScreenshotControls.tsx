/**
 * ScreenshotControls - Screenshot and fullscreen toggle buttons
 * Shown when HUD is hidden (screenshot mode)
 */

interface ScreenshotControlsProps {
  onScreenshot: () => void
  onShowHud: () => void
}

export function ScreenshotControls({
  onScreenshot,
  onShowHud
}: ScreenshotControlsProps) {
  return (
    <div className="screenshot-mode-buttons">
      <button className="screenshot-mode-btn" onClick={onScreenshot} title="Screenshot">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z" />
          <circle cx="12" cy="13" r="4" />
        </svg>
      </button>
      <button className="screenshot-mode-btn" onClick={onShowHud} title="Show HUD">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
          <circle cx="12" cy="12" r="3" />
        </svg>
      </button>
    </div>
  )
}
