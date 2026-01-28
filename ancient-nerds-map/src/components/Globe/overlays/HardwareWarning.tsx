/**
 * HardwareWarning - WebGL/GPU warning banner
 * Displays warning when software rendering is detected or FPS is consistently low
 */

interface HardwareWarningProps {
  softwareRendering: boolean
  warningDismissed: boolean
  onDismiss: () => void
  gpuName: string | null
}

export function HardwareWarning({
  softwareRendering,
  warningDismissed,
  onDismiss,
  gpuName
}: HardwareWarningProps) {
  if (!softwareRendering || warningDismissed) {
    return null
  }

  return (
    <div className="hardware-warning-banner">
      <div className="warning-icon">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
          <line x1="12" y1="9" x2="12" y2="13" />
          <line x1="12" y1="17" x2="12.01" y2="17" />
        </svg>
      </div>
      <div className="warning-content">
        <div className="warning-title">Hardware Acceleration Disabled</div>
        <div className="warning-message">
          The globe is using software rendering{gpuName && ` (${gpuName})`}, which may cause poor performance.
          Enable hardware acceleration in your browser settings for the best experience.
        </div>
      </div>
      <button className="warning-dismiss" onClick={onDismiss} title="Dismiss">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <line x1="18" y1="6" x2="6" y2="18" />
          <line x1="6" y1="6" x2="18" y2="18" />
        </svg>
      </button>
    </div>
  )
}
