import { forwardRef, useState } from 'react'

/**
 * FpsDisplay - Shows FPS counter and low FPS warning
 * Uses forwardRef to allow parent to update the FPS value directly
 */

interface FpsDisplayProps {
  gpuName?: string | null
  lowFps?: boolean
  lowFpsReady?: boolean
}

export const FpsDisplay = forwardRef<HTMLDivElement, FpsDisplayProps>(function FpsDisplay(
  { gpuName, lowFps, lowFpsReady },
  ref
) {
  const [lowFpsWarningShown, setLowFpsWarningShown] = useState(false)

  return (
    <div className="fps-display-container">
      <div ref={ref} className="fps-display" title={gpuName || 'GPU not detected'}>-- FPS</div>
      {lowFpsReady && lowFps && (
        <span
          className="fps-warning"
          onMouseEnter={() => setLowFpsWarningShown(true)}
        >
          <span className="fps-warning-icon">!</span>
          {(!lowFpsWarningShown) && (
            <span className="fps-warning-tooltip fps-warning-tooltip-auto">
              Low FPS detected! Enable hardware acceleration in your browser settings for better performance.
            </span>
          )}
          <span className="fps-warning-tooltip fps-warning-tooltip-hover">
            Low FPS detected! Enable hardware acceleration in your browser settings for better performance.
          </span>
        </span>
      )}
    </div>
  )
})
