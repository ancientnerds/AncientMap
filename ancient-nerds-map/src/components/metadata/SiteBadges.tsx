import { getCategoryColor, getPeriodColor } from '../../constants/colors'
import { categorizePeriod } from '../../data/sites'
import { MetadataBadge, type BadgeSize } from './MetadataBadge'
import './metadata.css'

interface SiteBadgesProps {
  category?: string | null
  period?: string | null
  periodStart?: number | null
  size?: BadgeSize
}

export function SiteBadges({ category, period, periodStart, size = 'sm' }: SiteBadgesProps) {
  const isGenericType = !category || ['site', 'unknown'].includes(category.toLowerCase())
  const resolvedPeriod = period || (periodStart != null ? categorizePeriod(periodStart) : null)
  const showPeriod = resolvedPeriod && resolvedPeriod !== 'Unknown'

  const categoryColor = !isGenericType ? getCategoryColor(category!) : null
  const periodColor = showPeriod ? getPeriodColor(resolvedPeriod!) : null

  if (!categoryColor && !periodColor) return null

  return (
    <div className="meta-badges">
      {categoryColor && <MetadataBadge label={category!} color={categoryColor} size={size} />}
      {periodColor && <MetadataBadge label={resolvedPeriod!} color={periodColor} size={size} />}
    </div>
  )
}
