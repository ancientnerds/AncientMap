/**
 * SiteMetadata component
 *
 * Displays source-specific metadata fields from raw_data.
 * Only renders when there are displayable fields - returns null otherwise.
 */

import { useMemo } from 'react'
import { getDisplayableFields, hasMetadataFields } from '../config/sourceFields'

interface SiteMetadataProps {
  sourceId: string
  rawData: Record<string, unknown> | null | undefined
}

/**
 * Displays source-specific metadata in a 2-column grid.
 *
 * Returns null if:
 * - No field configuration exists for this source
 * - No raw_data is provided
 * - No fields have displayable values
 */
export default function SiteMetadata({ sourceId, rawData }: SiteMetadataProps) {
  // Get displayable fields (memoized for performance)
  const fields = useMemo(() => {
    if (!rawData || !hasMetadataFields(sourceId)) {
      return []
    }
    return getDisplayableFields(sourceId, rawData)
  }, [sourceId, rawData])

  // Return null if no displayable fields - component will be completely hidden
  if (fields.length === 0) {
    return null
  }

  return (
    <div className="site-metadata">
      <div className="site-metadata-grid">
        {fields.map(({ config, value }) => (
          <div key={config.key} className="site-metadata-field">
            <span className="site-metadata-label">{config.label}</span>
            <span className="site-metadata-value">{value}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

/**
 * Inline styles for SiteMetadata component.
 *
 * These can also be added to SitePopup.css for consistency.
 */
export const siteMetadataStyles = `
.site-metadata {
  margin: 12px 0;
  padding: 12px;
  background: rgba(0, 0, 0, 0.2);
  border-radius: 8px;
  border: 1px solid rgba(255, 255, 255, 0.1);
}

.site-metadata-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 8px 16px;
}

.site-metadata-field {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.site-metadata-label {
  font-size: 10px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  color: rgba(255, 255, 255, 0.5);
}

.site-metadata-value {
  font-size: 13px;
  color: rgba(255, 255, 255, 0.9);
  font-weight: 500;
}

/* Single column on narrow containers */
@media (max-width: 400px) {
  .site-metadata-grid {
    grid-template-columns: 1fr;
  }
}
`
