import { BANDS, fmtVital, latest, NAMES, rating } from './FieldVitals'
import { fmtInt } from './format'
import { devicesLine } from './GlobeReach'
import { Explain, Panel } from './Panel'
import { changeLine } from './SearchGoogle'
import type { ContentData, FieldVitalsData, GlobeData, ProblemsData, SearchData } from './types'
import type { Loaded } from './useStats'

/** How many problems the summary names; the Problems panel ranks all of them. */
const PROBLEM_LINES = 3
/** How many dead search terms are quoted before the rest is counted. */
const DEAD_TERMS = 4

export interface AttentionLine {
  key: string
  text: string
  /** 'bad' breaks something for a visitor, 'warn' slows or misses them. */
  tone: 'bad' | 'warn' | 'ok'
}

/**
 * The page's answer in a few lines, from what the other panels already loaded:
 * how Google's clicks move, whether the globe comes up, the worst problems,
 * the speed numbers Google rates below good, the searches that found nothing.
 * Many panels answer many questions; a founder opening the page wants to know
 * first whether any of them needs doing (2026-09-25).
 */
export function attentionLines(
  problems: ProblemsData | null,
  globe: GlobeData | null,
  content: ContentData | null,
  search: SearchData | null = null,
  vitals: FieldVitalsData | null = null,
): AttentionLine[] {
  const lines: AttentionLine[] = []
  if (search?.current && search.previous) {
    const clicks = changeLine(search.current.clicks, search.previous.clicks)
    const position = search.current.position === null ? '' : `, average position ${search.current.position.toFixed(1)}`
    lines.push({
      key: 'google',
      text: `Google: ${fmtInt(search.current.clicks)} clicks in 28 days, ${clicks.text}${position}.`,
      tone: search.current.clicks >= search.previous.clicks ? 'ok' : 'warn',
    })
  }
  if (globe && globe.loads > 0) {
    const share = globe.reached / globe.loads
    lines.push({
      key: 'globe',
      text: `Globe: ${fmtInt(globe.reached)} of ${fmtInt(globe.loads)} loads reached it. ${devicesLine(globe.by_device)}`.trim(),
      tone: share >= 0.9 ? 'ok' : share >= 0.7 ? 'warn' : 'bad',
    })
  }
  for (const p of (problems?.problems ?? []).slice(0, PROBLEM_LINES)) {
    const broken = p.kind === 'js_error' || p.kind === 'webgl_lost' || p.kind === 'broken_link'
    lines.push({ key: `problem:${p.kind}:${p.label}`, text: `${p.label} — ${p.detail}`, tone: broken ? 'bad' : 'warn' })
  }
  for (const [name, ff] of [['Phone', vitals?.phone], ['Desktop', vitals?.desktop]] as const) {
    if (!ff) continue
    for (const metric of ['lcp', 'inp', 'cls'] as const) {
      const now = latest(ff[metric])
      if (!now) continue
      const r = rating(metric, now.value)
      if (r === 'good') continue
      lines.push({
        key: `vital:${name}:${metric}`,
        text: `${name} · ${NAMES[metric]} ${fmtVital(metric, now.value)} — Google rates it ${r === 'poor' ? 'poor' : 'needs improvement'}, good is up to ${fmtVital(metric, BANDS[metric].good)}.`,
        tone: r === 'poor' ? 'bad' : 'warn',
      })
    }
  }
  const dead = (content?.searches ?? []).filter(s => s.results === 0).map(s => `“${s.label}”`)
  if (dead.length > 0) {
    const named = dead.slice(0, DEAD_TERMS).join(', ')
    const more = dead.length > DEAD_TERMS ? ` and ${fmtInt(dead.length - DEAD_TERMS)} more` : ''
    lines.push({ key: 'dead-searches', text: `Searches that found nothing: ${named}${more}.`, tone: 'warn' })
  }
  return lines
}

/** What needs doing, before every other question. */
export function Attention({
  problems,
  globe,
  content,
  search,
  vitals,
}: {
  problems: Loaded<ProblemsData>
  globe: Loaded<GlobeData>
  content: Loaded<ContentData>
  search: Loaded<SearchData>
  vitals: Loaded<FieldVitalsData>
}) {
  const loading = !problems.data && !globe.data && !content.data && !search.data && !vitals.data
  const lines = attentionLines(problems.data, globe.data, content.data, search.data, vitals.data)
  return (
    <Panel question="What needs attention?" wide>
      {loading ? (
        <p className="dash-status">Loading…</p>
      ) : lines.length === 0 ? (
        <p className="dash-empty">Nothing in this window.</p>
      ) : (
        <ul className="dash-attention">
          {lines.map(l => (
            <li key={l.key} className={`dash-attention-item dash-attention-item--${l.tone}`}>
              {l.text}
            </li>
          ))}
        </ul>
      )}
      <Explain>
        <p className="dash-note">
          These lines come from the panels further down: Google's clicks of the last 28 days against the 28
          before (Search Console), whether the globe comes up, up to {PROBLEM_LINES} of the worst problems, every
          speed number Google's own field data rates below good, and the searches that found nothing. Red breaks
          something for a visitor, amber slows or misses them, green is Google's clicks holding or growing and a
          globe that came up for at least 9 in 10 loads.
        </p>
      </Explain>
    </Panel>
  )
}
