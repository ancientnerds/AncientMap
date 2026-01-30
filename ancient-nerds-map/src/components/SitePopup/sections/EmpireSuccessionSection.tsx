/**
 * Empire Succession Section
 *
 * Displays preceding and succeeding polities.
 */

import { SeshatPolityLink } from '../../../types/seshat'

interface EmpireSuccessionSectionProps {
  precedingPolities?: SeshatPolityLink[]
  succeedingPolities?: SeshatPolityLink[]
}

// Get icon for relation type
function getRelationIcon(relation: SeshatPolityLink['relation']) {
  switch (relation) {
    case 'succession':
      return (
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M5 12h14" />
          <path d="m12 5 7 7-7 7" />
        </svg>
      )
    case 'conquest':
      return (
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M14.5 17.5L3 6V3h3l11.5 11.5" />
          <path d="M13 19l6-6" />
        </svg>
      )
    case 'division':
      return (
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M12 2v10" />
          <path d="M6 12 2 22l10-4" />
          <path d="M18 12l4 10-10-4" />
        </svg>
      )
    case 'unification':
      return (
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M12 22v-10" />
          <path d="M6 12l-4-10 10 4" />
          <path d="M18 12l4-10-10 4" />
        </svg>
      )
    case 'continuation':
      return (
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M5 12h14" />
          <path d="m12 5 7 7-7 7" />
        </svg>
      )
    default:
      return null
  }
}

export default function EmpireSuccessionSection({ precedingPolities, succeedingPolities }: EmpireSuccessionSectionProps) {
  const hasPreceding = precedingPolities && precedingPolities.length > 0
  const hasSucceeding = succeedingPolities && succeedingPolities.length > 0

  if (!hasPreceding && !hasSucceeding) return null

  return (
    <div className="empire-section empire-succession-section">
      <h3 className="empire-section-title">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M2 17h20" />
          <path d="M2 12h20" />
          <path d="M2 7h20" />
        </svg>
        Succession
      </h3>

      <div className="empire-succession-content">
        {hasPreceding && (
          <div className="empire-succession-group">
            <div className="empire-succession-label">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M19 12H5" />
                <path d="m12 19-7-7 7-7" />
              </svg>
              Preceding
            </div>
            <div className="empire-succession-list">
              {precedingPolities!.map((polity, i) => (
                <div key={i} className="empire-succession-item">
                  <span className="empire-succession-relation">
                    {getRelationIcon(polity.relation)}
                    {polity.relation}
                  </span>
                  <span className="empire-succession-name">{polity.name}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {hasSucceeding && (
          <div className="empire-succession-group">
            <div className="empire-succession-label">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M5 12h14" />
                <path d="m12 5 7 7-7 7" />
              </svg>
              Succeeding
            </div>
            <div className="empire-succession-list">
              {succeedingPolities!.map((polity, i) => (
                <div key={i} className="empire-succession-item">
                  <span className="empire-succession-relation">
                    {getRelationIcon(polity.relation)}
                    {polity.relation}
                  </span>
                  <span className="empire-succession-name">{polity.name}</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
