/**
 * Empire Social Section
 *
 * Displays languages, religions, and centralization data.
 */

import { SeshatPolityData } from '../../../types/seshat'

interface EmpireSocialSectionProps {
  data: SeshatPolityData
}

export default function EmpireSocialSection({ data }: EmpireSocialSectionProps) {
  const hasLanguages = data.languages && data.languages.length > 0
  const hasReligions = data.religions && data.religions.length > 0
  const hasCentralization = data.centralization

  if (!hasLanguages && !hasReligions && !hasCentralization) {
    return null
  }

  // Format centralization for display
  const centralizationDisplay = data.centralization
    ? data.centralization.charAt(0).toUpperCase() + data.centralization.slice(1)
    : null

  return (
    <div className="empire-section empire-social-section">
      <h3 className="empire-section-title">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M3 21h18" />
          <path d="M9 8h1" />
          <path d="M9 12h1" />
          <path d="M9 16h1" />
          <path d="M14 8h1" />
          <path d="M14 12h1" />
          <path d="M14 16h1" />
          <path d="M5 21V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2v16" />
        </svg>
        Society & Government
      </h3>

      <div className="empire-social-content">
        {hasLanguages && (
          <div className="empire-social-row">
            <div className="empire-social-label">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="m5 8 6 6" />
                <path d="m4 14 6-6 2-3" />
                <path d="M2 5h12" />
                <path d="M7 2h1" />
                <path d="m22 22-5-10-5 10" />
                <path d="M14 18h6" />
              </svg>
              Languages
            </div>
            <div className="empire-tags">
              {data.languages!.map((lang, i) => (
                <span key={i} className="empire-tag empire-tag-language">
                  {lang}
                </span>
              ))}
            </div>
          </div>
        )}

        {hasReligions && (
          <div className="empire-social-row">
            <div className="empire-social-label">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <circle cx="12" cy="12" r="10" />
                <path d="M12 2v20" />
                <path d="M2 12h20" />
              </svg>
              Religions
            </div>
            <div className="empire-tags">
              {data.religions!.map((religion, i) => (
                <span key={i} className="empire-tag empire-tag-religion">
                  {religion}
                </span>
              ))}
            </div>
          </div>
        )}

        {hasCentralization && (
          <div className="empire-social-row">
            <div className="empire-social-label">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <circle cx="12" cy="12" r="3" />
                <path d="M12 2v4" />
                <path d="M12 18v4" />
                <path d="m4.93 4.93 2.83 2.83" />
                <path d="m16.24 16.24 2.83 2.83" />
                <path d="M2 12h4" />
                <path d="M18 12h4" />
                <path d="m4.93 19.07 2.83-2.83" />
                <path d="m16.24 7.76 2.83-2.83" />
              </svg>
              Centralization
            </div>
            <div className="empire-centralization-badge">
              <span className={`empire-centralization empire-centralization-${data.centralization?.replace(/\s+/g, '-')}`}>
                {centralizationDisplay}
              </span>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
