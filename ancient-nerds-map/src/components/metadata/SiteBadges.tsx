import { getCategoryColor, getPeriodColor, PERIOD_COLORS } from '../../constants/colors'
import { categorizePeriod } from '../../data/sites'
import { MetadataBadge, type BadgeSize } from './MetadataBadge'
import './metadata.css'

interface SiteBadgesProps {
  category?: string | null
  period?: string | null
  periodStart?: number | null
  size?: BadgeSize
  hideExactYear?: boolean
}

function formatPeriodYear(year: number): string {
  if (year < 0) return `${Math.abs(year)} BC`
  return `${year} AD`
}

export function SiteBadges({ category, period, periodStart, size = 'sm', hideExactYear }: SiteBadgesProps) {
  const isGenericType = !category || ['site', 'unknown'].includes(category.toLowerCase())

  // Resolve period: prefer canonical bucket, fall back to periodStart, then raw string
  let resolvedPeriod: string | null = null
  if (period && PERIOD_COLORS[period]) {
    resolvedPeriod = period  // already a canonical bucket
  } else if (periodStart != null) {
    resolvedPeriod = categorizePeriod(periodStart)  // derive from year
  } else if (period && period !== 'Unknown') {
    resolvedPeriod = period  // raw string (will get gray color)
  }
  const showPeriod = resolvedPeriod && resolvedPeriod !== 'Unknown'

  const categoryColor = !isGenericType ? getCategoryColor(category!) : null
  const periodColor = showPeriod ? getPeriodColor(resolvedPeriod!) : null

  if (!categoryColor && !periodColor) return null

  return (
    <div className="meta-badges">
      {categoryColor && <MetadataBadge label={category!} color={categoryColor} size={size} />}
      {periodColor && (
        <MetadataBadge
          label={periodStart != null && !hideExactYear
            ? `${resolvedPeriod!} (${formatPeriodYear(periodStart)})`
            : resolvedPeriod!}
          color={periodColor}
          size={size}
        />
      )}
    </div>
  )
}
