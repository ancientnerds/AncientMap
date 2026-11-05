/**
 * QualityBadge — the one quality badge a paper shows: "Claim-checked".
 *
 * Owner decision D86 (2026-11-05): the old M3 judge's tiers ("Platinum",
 * "Gold", "Unverified" with a score out of 100) are not shown. The badge
 * appears only where the studio's claim check ran and passed; the API
 * (GET /theo/public/{slug}) hands over nothing else.
 */

const CLAIM_CHECKED_BADGE = 'Claim-checked'

export interface QualityScore {
  badge: string
}

interface QualityBadgeProps {
  qualityScore: QualityScore | null | undefined
}

export default function QualityBadge({ qualityScore }: QualityBadgeProps) {
  if (qualityScore?.badge !== CLAIM_CHECKED_BADGE) return null
  return (
    <span
      className="theo-badge theo-badge-quality"
      style={{ '--quality-color': '#2e7d32' } as React.CSSProperties}
      data-tooltip="The paper's claims were checked against the archived source texts."
    >
      {CLAIM_CHECKED_BADGE}
      <span className="theo-badge-quality-dot" aria-hidden="true">●</span>
    </span>
  )
}
