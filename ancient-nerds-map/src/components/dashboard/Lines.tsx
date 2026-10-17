/** Height of a line chart's viewBox; the CSS scales it to the panel's width. */
export const LINE_HEIGHT = 100

/** One polyline's `points`: point i at x = i, the value measured up from the
 *  baseline against `max`. A zero max draws the line on the baseline. */
export function linePoints(values: number[], max: number, height = LINE_HEIGHT): string {
  const unit = height / Math.max(max, 1)
  return values.map((v, i) => `${i},${height - v * unit}`).join(' ')
}

/** The unbroken runs of a series with gaps, each as `points`: a week CrUX had
 *  too few samples for is a hole in the line, not a zero. A run of one point
 *  is dropped - a polyline needs two. */
export function lineRuns(values: (number | null)[], max: number, height = LINE_HEIGHT): string[] {
  const unit = height / Math.max(max, 1)
  const runs: string[][] = [[]]
  values.forEach((v, i) => {
    if (v === null) runs.push([])
    else runs[runs.length - 1].push(`${i},${height - v * unit}`)
  })
  return runs.filter(r => r.length > 1).map(r => r.join(' '))
}

export interface Series {
  /** The legend's name for the line. */
  label: string
  values: (number | null)[]
  /** dash-line-all (pale) or dash-line-human (bright). */
  className: string
}

interface LineChartProps {
  series: Series[]
  /** One tooltip per x position, in order. */
  titles: string[]
  /** The axis row under the chart: first label, middle text, last label.
   *  Left out, the chart is a bare sparkline. */
  axis?: [string, string, string]
  /** What a screen reader hears instead of the picture. */
  label: string
  /** Scale shared by every series; defaults to the largest value drawn. */
  max?: number
  small?: boolean
}

/**
 * The page's line chart: one polyline per series on a shared scale, a
 * transparent column per point that carries its tooltip, the axis row under
 * it and a legend that says which line is which - the colour key is part of
 * the reading, so it is never behind the panel's explanation click.
 */
export function LineChart({ series, titles, axis, label, max, small = false }: LineChartProps) {
  const top =
    max ?? Math.max(...series.flatMap(s => s.values.filter((v): v is number => v !== null)), 1)
  const width = Math.max(titles.length - 1, 1)
  return (
    <>
      <svg
        className={small ? 'dash-line dash-line--small' : 'dash-line'}
        viewBox={`0 0 ${width} ${LINE_HEIGHT}`}
        preserveAspectRatio="none"
        role="img"
        aria-label={label}
      >
        {series.flatMap(s =>
          lineRuns(s.values, top).map((points, i) => (
            <polyline key={`${s.label}:${i}`} className={s.className} points={points} />
          ))
        )}
        {titles.map((title, i) => (
          <rect key={i} className="dash-line-hit" x={i - 0.5} width={1} y={0} height={LINE_HEIGHT}>
            <title>{title}</title>
          </rect>
        ))}
      </svg>
      {axis && (
        <div className="dash-spark-axis">
          <span>{axis[0]}</span>
          <span>{axis[1]}</span>
          <span>{axis[2]}</span>
        </div>
      )}
      {series.length > 1 && (
        <ul className="dash-line-legend">
          {series.map(s => (
            <li key={s.label} className={`${s.className}-key`}>
              {s.label}
            </li>
          ))}
        </ul>
      )}
    </>
  )
}

/** The axis top for `v`: four steps of 1, 2, 2.5 or 5 times a power of ten,
 *  so every tick is a round number and the highest value fits under the top. */
export function niceMax(v: number): number {
  if (v <= 0) return 4
  const raw = v / 4
  const pow = 10 ** Math.floor(Math.log10(raw))
  const step = [1, 2, 2.5, 5, 10].map(m => m * pow).find(s => s >= raw - 1e-9) as number
  return step * 4
}

/** The trailing mean over `window` points; null until the window is full, so
 *  the trend starts where it means something. */
export function rollingMean(values: (number | null)[], window = 7): (number | null)[] {
  return values.map((_, i) => {
    if (i < window - 1) return null
    const part = values.slice(i - window + 1, i + 1)
    if (part.some(v => v === null)) return null
    return (part as number[]).reduce((a, b) => a + b, 0) / window
  })
}

export interface AxisScale {
  max: number
  format: (v: number) => string
}

export interface ChartLine {
  label: string
  values: (number | null)[]
  className: string
  /** Which axis the line is read against; the left one by default. */
  side?: 'left' | 'right'
  /** Left out of the legend (a thin daily line under its own average). */
  unlisted?: boolean
}

export interface ChartBars {
  label: string
  values: number[]
  className: string
}

interface AxisChartProps {
  titles: string[]
  axis: [string, string, string]
  label: string
  left: AxisScale
  right?: AxisScale
  lines?: ChartLine[]
  /** Stacked from the baseline in this order, read against the left axis. */
  bars?: ChartBars[]
  small?: boolean
}

const TICKS = [4, 3, 2, 1, 0]

function Ticks({ scale, side }: { scale: AxisScale; side: 'left' | 'right' }) {
  return (
    <div className={`dash-chart-ticks dash-chart-ticks--${side}`} aria-hidden="true">
      {TICKS.map(i => (
        <span key={i} style={{ top: `${(4 - i) * 25}%` }}>
          {scale.format((scale.max * i) / 4)}
        </span>
      ))}
    </div>
  )
}

/**
 * A chart with real axes: ticks at a quarter of the round top on the left and,
 * for a second measure, on the right; gridlines; stacked bars and lines on top
 * of them. The ticks are HTML beside the picture, because text inside a
 * viewBox stretched to the panel's width would stretch with it.
 */
export function AxisChart({ titles, axis, label, left, right, lines = [], bars = [], small = false }: AxisChartProps) {
  const n = titles.length
  return (
    <>
      <div className={small ? 'dash-chart dash-chart--small' : 'dash-chart'}>
        <Ticks scale={left} side="left" />
        <svg viewBox={`-0.5 0 ${n} ${LINE_HEIGHT}`} preserveAspectRatio="none" role="img" aria-label={label}>
          {TICKS.map(i => (
            <line key={i} className="dash-chart-grid" x1={-0.5} x2={n - 0.5} y1={i * 25} y2={i * 25} />
          ))}
          {titles.map((_, i) => {
            let base = LINE_HEIGHT
            return bars.map(b => {
              const h = (b.values[i] / Math.max(left.max, 1)) * LINE_HEIGHT
              base -= h
              return <rect key={`${b.label}:${i}`} className={b.className} x={i - 0.35} width={0.7} y={base} height={h} />
            })
          })}
          {lines.flatMap(l =>
            lineRuns(l.values, (l.side === 'right' && right ? right : left).max).map((points, i) => (
              <polyline key={`${l.label}:${i}`} className={l.className} points={points} />
            ))
          )}
          {titles.map((title, i) => (
            <rect key={i} className="dash-line-hit" x={i - 0.5} width={1} y={0} height={LINE_HEIGHT}>
              <title>{title}</title>
            </rect>
          ))}
        </svg>
        {right && <Ticks scale={right} side="right" />}
      </div>
      <div className="dash-spark-axis dash-chart-axis">
        <span>{axis[0]}</span>
        <span>{axis[1]}</span>
        <span>{axis[2]}</span>
      </div>
      <ul className="dash-line-legend">
        {[...bars, ...lines.filter(l => !l.unlisted)].map(s => (
          <li key={s.label} className={`${s.className}-key`}>
            {s.label}
          </li>
        ))}
      </ul>
    </>
  )
}
