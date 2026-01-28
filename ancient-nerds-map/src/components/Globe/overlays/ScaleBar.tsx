/**
 * ScaleBar - Shows the map scale bar at the bottom of the globe
 * Pure presentational component for displaying map scale
 */

interface ScaleBarProps {
  scaleBar: { km: number; pixels: number } | null
  visible: boolean
}

export function ScaleBar({ scaleBar, visible }: ScaleBarProps) {
  if (!visible || !scaleBar) return null

  return (
    <div className="scale-bar">
      <div className="scale-bar-line" style={{ width: scaleBar.pixels }} />
      <div className="scale-bar-label">
        {scaleBar.km >= 1 ? `${scaleBar.km} km` : `${Math.round(scaleBar.km * 1000)} m`}
      </div>
    </div>
  )
}
