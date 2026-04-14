import './nerv-loading-bar.css'

interface NervLoadingBarProps {
  label?: string       // stamp label, e.g. "LOADING" or "RANDOM"
  sublabel?: string    // text shown inside the track, e.g. "FETCHING SITES"
  progress?: number    // 0–100 for determinate; omit for indeterminate
  counter?: string     // e.g. "47 / 200 sites"
  compact?: boolean    // true = track only, no header/LEDs
  ledsDone?: number    // subtask completion count (fills LEDs left→right)
  ledsTotal?: number   // subtask total count (determines LED count, capped at 10)
}

const MAX_LEDS = 10

export function NervLoadingBar({ label = 'LOADING', sublabel, progress, counter, compact, ledsDone, ledsTotal }: NervLoadingBarProps) {
  const det = progress != null

  // Dynamic LED count based on subtask info
  const hasSubtasks = ledsDone != null && ledsTotal != null && ledsTotal > 0
  const ledCount = hasSubtasks ? Math.min(ledsTotal, MAX_LEDS) : 7
  const litCount = hasSubtasks
    ? (ledsTotal <= MAX_LEDS
        ? Math.min(ledsDone, ledCount)            // 1:1 mapping
        : Math.floor((ledsDone / ledsTotal) * ledCount))  // proportional
    : -1  // fallback to percentage-based

  return (
    <div className={`nerv-lb${compact ? ' nerv-lb--compact' : ''}`}>
      {!compact && <div className="nerv-lb-inner" />}
      {!compact && (
        <div className="nerv-lb-header">
          <span className="nerv-lb-stamp">{label}</span>
          {counter && <span className="nerv-lb-counter">{counter}</span>}
        </div>
      )}
      <div className={`nerv-lb-track${det ? '' : ' nerv-lb-track--indet'}`}>
        <div className="nerv-lb-fill" style={det ? { width: `${progress}%` } : undefined} />
        {sublabel && <span className="nerv-lb-track-label">{sublabel}</span>}
      </div>
      {!compact && det && (
        <div className="nerv-lb-leds">
          {Array.from({ length: ledCount }, (_, i) => (
            <div
              key={i}
              className={`nerv-lb-led${
                hasSubtasks
                  ? (i < litCount ? ' nerv-lb-led--on' : '')
                  : (progress! >= ((i + 1) / ledCount) * 100 ? ' nerv-lb-led--on' : '')
              }`}
              style={{ animationDelay: `${i * 0.15}s` }}
            />
          ))}
        </div>
      )}
    </div>
  )
}
