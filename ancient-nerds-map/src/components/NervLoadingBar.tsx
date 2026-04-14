import './nerv-loading-bar.css'

interface NervLoadingBarProps {
  label?: string       // stamp label, e.g. "LOADING" or "RANDOM"
  sublabel?: string    // text shown inside the track, e.g. "FETCHING SITES"
  progress?: number    // 0–100 for determinate; omit for indeterminate
  counter?: string     // e.g. "47 / 200 sites"
  compact?: boolean    // true = track only, no header/LEDs
}

const LED_COUNT = 7

export function NervLoadingBar({ label = 'LOADING', sublabel, progress, counter, compact }: NervLoadingBarProps) {
  const det = progress != null

  return (
    <div className={`nerv-lb${compact ? ' nerv-lb--compact' : ''}`}>
      {!compact && <div className="nerv-lb-inner" />}
      {!compact && (
        <div className="nerv-lb-header">
          <span className="nerv-lb-stamp">{label}</span>
          {counter && <span className="nerv-lb-counter">{counter}</span>}
          {det && <span className="nerv-lb-pct">{Math.round(progress!)}%</span>}
        </div>
      )}
      <div className={`nerv-lb-track${det ? '' : ' nerv-lb-track--indet'}`}>
        <div className="nerv-lb-fill" style={det ? { width: `${progress}%` } : undefined} />
        {sublabel && <span className="nerv-lb-track-label">{sublabel}</span>}
      </div>
      {!compact && det && (
        <div className="nerv-lb-leds">
          {Array.from({ length: LED_COUNT }, (_, i) => (
            <div
              key={i}
              className={`nerv-lb-led${progress! >= ((i + 1) / LED_COUNT) * 100 ? ' nerv-lb-led--on' : ''}`}
            />
          ))}
        </div>
      )}
    </div>
  )
}
