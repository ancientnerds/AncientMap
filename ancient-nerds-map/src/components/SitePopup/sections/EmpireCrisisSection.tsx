/**
 * Empire Crisis Section
 *
 * Displays crisis events and power transitions from Seshat data.
 */

import { SeshatCrisisData, SeshatCrisisEvent } from '../../../types/seshat'
import { formatYear } from '../../../services/seshatService'

interface EmpireCrisisSectionProps {
  crisis: SeshatCrisisData | undefined
}

// Get icon for crisis type
function getCrisisIcon(type: SeshatCrisisEvent['type']) {
  switch (type) {
    case 'civil war':
      return (
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M14.5 17.5L3 6V3h3l11.5 11.5" />
          <path d="M13 19l6-6" />
          <path d="M16 16l4 4" />
          <path d="M19 21l2-2" />
        </svg>
      )
    case 'invasion':
      return (
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M4 15s1-1 4-1 5 2 8 2 4-1 4-1V3s-1 1-4 1-5-2-8-2-4 1-4 1z" />
          <line x1="4" y1="22" x2="4" y2="15" />
        </svg>
      )
    case 'plague':
      return (
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M8 2v4" />
          <path d="M12 2v4" />
          <path d="M16 2v4" />
          <path d="M3 10h18" />
          <path d="M5 6h14a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2z" />
        </svg>
      )
    case 'famine':
      return (
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M12 2v10" />
          <path d="M18.6 14.5a6 6 0 0 1-12 0c0-3.3 6-10.5 6-10.5s6 7.2 6 10.5z" />
        </svg>
      )
    case 'political crisis':
      return (
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <circle cx="12" cy="12" r="10" />
          <path d="M12 8v4" />
          <path d="M12 16h.01" />
        </svg>
      )
    case 'economic crisis':
      return (
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M12 2v20" />
          <path d="M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6" />
        </svg>
      )
    case 'social crisis':
      return (
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2" />
          <circle cx="9" cy="7" r="4" />
          <line x1="17" y1="11" x2="23" y2="11" />
        </svg>
      )
    default:
      return (
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <circle cx="12" cy="12" r="10" />
          <path d="M12 8v4" />
          <path d="M12 16h.01" />
        </svg>
      )
  }
}

// Get severity color class
function getSeverityClass(severity?: SeshatCrisisEvent['severity']) {
  switch (severity) {
    case 'catastrophic':
      return 'empire-crisis-catastrophic'
    case 'severe':
      return 'empire-crisis-severe'
    case 'moderate':
      return 'empire-crisis-moderate'
    case 'minor':
      return 'empire-crisis-minor'
    default:
      return ''
  }
}

export default function EmpireCrisisSection({ crisis }: EmpireCrisisSectionProps) {
  if (!crisis) return null

  const hasEvents = crisis.crisisEvents && crisis.crisisEvents.length > 0
  const hasTransitions = crisis.powerTransitions && crisis.powerTransitions.length > 0

  if (!hasEvents && !hasTransitions) return null

  return (
    <div className="empire-section empire-crisis-section">
      <h3 className="empire-section-title">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
          <line x1="12" y1="9" x2="12" y2="13" />
          <line x1="12" y1="17" x2="12.01" y2="17" />
        </svg>
        Crisis Events
      </h3>

      {hasEvents && (
        <div className="empire-crisis-list">
          {crisis.crisisEvents!.map((event, i) => (
            <div key={i} className={`empire-crisis-item ${getSeverityClass(event.severity)}`}>
              <div className="empire-crisis-header">
                <span className="empire-crisis-icon">{getCrisisIcon(event.type)}</span>
                <span className="empire-crisis-name">{event.name}</span>
                <span className="empire-crisis-dates">
                  {event.startYear === event.endYear
                    ? formatYear(event.startYear)
                    : `${formatYear(event.startYear)} - ${formatYear(event.endYear)}`
                  }
                </span>
              </div>
              {event.description && (
                <p className="empire-crisis-description">{event.description}</p>
              )}
              <div className="empire-crisis-meta">
                <span className="empire-crisis-type">{event.type}</span>
                {event.severity && (
                  <span className={`empire-crisis-severity ${getSeverityClass(event.severity)}`}>
                    {event.severity}
                  </span>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {hasTransitions && (
        <>
          <h4 className="empire-subsection-title">Power Transitions</h4>
          <div className="empire-transitions-list">
            {crisis.powerTransitions!.map((transition, i) => (
              <div key={i} className="empire-transition-item">
                <span className="empire-transition-year">{formatYear(transition.year)}</span>
                <span className="empire-transition-type">{transition.type}</span>
                {transition.fromPolity && transition.toPolity && (
                  <span className="empire-transition-polities">
                    {transition.fromPolity} → {transition.toPolity}
                  </span>
                )}
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  )
}
