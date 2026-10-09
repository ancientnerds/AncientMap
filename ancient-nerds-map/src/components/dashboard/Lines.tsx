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
