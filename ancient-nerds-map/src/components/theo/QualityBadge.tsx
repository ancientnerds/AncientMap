/**
 * QualityBadge — shows a colored quality-score badge with a CSS tooltip.
 * Only rendered when quality_score has a numeric total.
 */

export interface AuditGateFailures {
  audit_passed?: boolean
  invalid_markers?: number
  orphaned_refs?: number
  uncited_paragraphs?: number
  placeholder_markers?: number
  language_bleed?: number
  non_numeric_markers?: number
  hallucination_final?: number
  high_contradictions?: number
  undefined_title_terms?: number
}

export interface QualityScore {
  total: number
  badge: string
  dimensions: Record<string, number>
  /** Per-gate breakdown — populated by judge.py since 2026-05-12, optional
   *  on older results. Use to explain why a badge got demoted to Unverified
   *  even though the mechanical score is high. */
  audit_gate_failures?: AuditGateFailures
}

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
    `Evidence Honesty: ${d.evidence_honesty ?? d.hedging ?? '—'}/10`,
    `Coherence: ${d.coherence ?? '—'}/10`,
    `Relevance: ${d.question_fidelity ?? '—'}/10`,
  ].join('\n')
}

interface QualityBadgeProps {
  qualityScore: QualityScore | null | undefined
}

export default function QualityBadge({ qualityScore }: QualityBadgeProps) {
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
