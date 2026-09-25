import { fmtInt } from './format'
import { devicesLine } from './GlobeReach'
import { Panel } from './Panel'
import type { ContentData, GlobeData, ProblemsData } from './types'
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
 * whether the globe comes up, the worst problems, the searches that found
 * nothing. Fourteen panels answer fourteen questions; a founder opening the
 * page wants to know first whether any of them needs doing (2026-09-25).
 */
export function attentionLines(
  problems: ProblemsData | null,
  globe: GlobeData | null,
  content: ContentData | null,
): AttentionLine[] {
  const lines: AttentionLine[] = []
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
  const dead = (content?.searches ?? []).filter(s => s.results === 0).map(s => `“${s.label}”`)
  if (dead.length > 0) {
    const named = dead.slice(0, DEAD_TERMS).join(', ')
    const more = dead.length > DEAD_TERMS ? ` and ${fmtInt(dead.length - DEAD_TERMS)} more` : ''
    lines.push({ key: 'dead-searches', text: `Searches that found nothing: ${named}${more}.`, tone: 'warn' })
  }
  return lines
}

/** What needs doing, before the fourteen questions. */
export function Attention({
  problems,
  globe,
  content,
}: {
  problems: Loaded<ProblemsData>
  globe: Loaded<GlobeData>
  content: Loaded<ContentData>
}) {
  const loading = !problems.data && !globe.data && !content.data
  const lines = attentionLines(problems.data, globe.data, content.data)
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
    </Panel>
  )
}
