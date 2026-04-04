/**
 * QualityBadge — shows a colored quality-score badge with a CSS tooltip.
 * Only rendered when quality_score has a numeric total.
 * Not shown for Brief/Note tiers (they skip quality scoring).
 */

export interface QualityScore {
  total: number
  badge: string
  dimensions: Record<string, number>
}

const SKIPPED_TIERS = new Set(['brief', 'note'])

function badgeColor(total: number): string {
  if (total >= 90) return '#2e7d32'  // green  — Verified
  if (total >= 72) return '#f57f17'  // amber  — Reviewed
  if (total >= 55) return '#e65100'  // orange — Provisional
  return '#c62828'                   // red    — Unverified
}

function buildTooltip(qs: QualityScore): string {
  const d = qs.dimensions
  return [
    `Quality: ${qs.total}/100`,
    `Citation: ${d.citation_coverage ?? '—'}/20`,
    `References: ${d.reference_integrity ?? '—'}/10`,
    `Attribution: ${d.attribution_accuracy ?? '—'}/10`,
    `Fidelity: ${d.source_fidelity ?? '—'}/10`,
    `Hedging: ${d.hedging ?? '—'}/10`,
    `Coherence: ${d.coherence ?? '—'}/10`,
    `Relevance: ${d.question_fidelity ?? '—'}/10`,
  ].join('\n')
}

interface QualityBadgeProps {
  qualityScore: QualityScore | null | undefined
  effort: string
}

export default function QualityBadge({ qualityScore, effort }: QualityBadgeProps) {
  if (SKIPPED_TIERS.has(effort)) return null
  if (!qualityScore || typeof qualityScore.total !== 'number') return null

  const color = badgeColor(qualityScore.total)
  const tooltip = buildTooltip(qualityScore)

  return (
    <span
      className="theo-badge theo-badge-quality"
      style={{ '--quality-color': color } as React.CSSProperties}
      data-tooltip={tooltip}
      aria-label={`Quality score: ${qualityScore.total}/100 — ${qualityScore.badge}`}
    >
      {qualityScore.badge}
      <span className="theo-badge-quality-dot" aria-hidden="true">●</span>
    </span>
  )
}
