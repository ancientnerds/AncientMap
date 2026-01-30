/**
 * Empire Stats Section
 *
 * Displays population, territory, hierarchy, and capital information
 * from Seshat data.
 */

import { SeshatPolityData } from '../../../types/seshat'
import { getSocialComplexitySummary } from '../../../services/seshatService'

interface EmpireStatsSectionProps {
  data: SeshatPolityData
}

export default function EmpireStatsSection({ data }: EmpireStatsSectionProps) {
  const summary = getSocialComplexitySummary(data)

  // Check if we have any data to display
  const hasScale = summary.scale.territory || summary.scale.population || summary.scale.capital
  const hasHierarchy = summary.hierarchy.administrative || summary.hierarchy.military ||
    summary.hierarchy.religious || summary.hierarchy.settlement

  if (!hasScale && !hasHierarchy) {
    return null
  }

  return (
    <div className="empire-section empire-stats-section">
      <h3 className="empire-section-title">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M3 3v18h18" />
          <path d="M18 17V9" />
          <path d="M13 17V5" />
          <path d="M8 17v-3" />
        </svg>
        Empire Scale
      </h3>

      <div className="empire-stats-grid">
        {summary.scale.territory && (
          <div className="empire-stat-card">
            <div className="empire-stat-icon">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <circle cx="12" cy="12" r="10" />
                <path d="M2 12h20" />
                <path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z" />
              </svg>
            </div>
            <div className="empire-stat-value">{summary.scale.territory}</div>
            <div className="empire-stat-label">Territory</div>
          </div>
        )}

        {summary.scale.population && (
          <div className="empire-stat-card">
            <div className="empire-stat-icon">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2" />
                <circle cx="9" cy="7" r="4" />
                <path d="M23 21v-2a4 4 0 0 0-3-3.87" />
                <path d="M16 3.13a4 4 0 0 1 0 7.75" />
              </svg>
            </div>
            <div className="empire-stat-value">{summary.scale.population}</div>
            <div className="empire-stat-label">Population</div>
          </div>
        )}

        {summary.scale.capital && (
          <div className="empire-stat-card">
            <div className="empire-stat-icon">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M3 21h18" />
                <path d="M5 21V7l8-4v18" />
                <path d="M19 21V11l-6-4" />
                <path d="M9 9v.01" />
                <path d="M9 12v.01" />
                <path d="M9 15v.01" />
                <path d="M9 18v.01" />
              </svg>
            </div>
            <div className="empire-stat-value">{summary.scale.capital}</div>
            <div className="empire-stat-label">Capital</div>
          </div>
        )}

        {data.capitalPopulation && (
          <div className="empire-stat-card">
            <div className="empire-stat-icon">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M12 22s-8-4.5-8-11.8A8 8 0 0 1 12 2a8 8 0 0 1 8 8.2c0 7.3-8 11.8-8 11.8z" />
                <circle cx="12" cy="10" r="3" />
              </svg>
            </div>
            <div className="empire-stat-value">
              {data.capitalPopulation >= 1000000
                ? `${(data.capitalPopulation / 1000000).toFixed(1)}M`
                : data.capitalPopulation >= 1000
                  ? `${(data.capitalPopulation / 1000).toFixed(0)}K`
                  : data.capitalPopulation}
            </div>
            <div className="empire-stat-label">Capital Pop.</div>
          </div>
        )}
      </div>

      {hasHierarchy && (
        <>
          <h4 className="empire-subsection-title">Hierarchy Levels</h4>
          <div className="empire-hierarchy-grid">
            {summary.hierarchy.administrative && (
              <div className="empire-hierarchy-item">
                <span className="empire-hierarchy-label">Administrative</span>
                <span className="empire-hierarchy-value">{summary.hierarchy.administrative}</span>
              </div>
            )}
            {summary.hierarchy.military && (
              <div className="empire-hierarchy-item">
                <span className="empire-hierarchy-label">Military</span>
                <span className="empire-hierarchy-value">{summary.hierarchy.military}</span>
              </div>
            )}
            {summary.hierarchy.religious && (
              <div className="empire-hierarchy-item">
                <span className="empire-hierarchy-label">Religious</span>
                <span className="empire-hierarchy-value">{summary.hierarchy.religious}</span>
              </div>
            )}
            {summary.hierarchy.settlement && (
              <div className="empire-hierarchy-item">
                <span className="empire-hierarchy-label">Settlement</span>
                <span className="empire-hierarchy-value">{summary.hierarchy.settlement}</span>
              </div>
            )}
          </div>
        </>
      )}

      {summary.infrastructure.length > 0 && (
        <>
          <h4 className="empire-subsection-title">Infrastructure</h4>
          <div className="empire-tags">
            {summary.infrastructure.map((item, i) => (
              <span key={i} className="empire-tag empire-tag-infrastructure">
                {item}
              </span>
            ))}
          </div>
        </>
      )}
    </div>
  )
}
