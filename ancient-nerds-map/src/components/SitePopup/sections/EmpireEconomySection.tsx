/**
 * Empire Economy Section
 *
 * Displays economic data including writing systems, monetary systems,
 * and trade information.
 */

import { SeshatPolityData } from '../../../types/seshat'
import { getEconomySummary } from '../../../services/seshatService'

interface EmpireEconomySectionProps {
  data: SeshatPolityData
}

export default function EmpireEconomySection({ data }: EmpireEconomySectionProps) {
  const economy = getEconomySummary(data)

  // Check if we have any data to display
  const hasData = economy.informationSystems.length > 0 ||
    economy.monetary.length > 0 ||
    economy.trade.length > 0

  if (!hasData) return null

  return (
    <div className="empire-section empire-economy-section">
      <h3 className="empire-section-title">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <circle cx="12" cy="12" r="8" />
          <line x1="12" y1="8" x2="12" y2="12" />
          <line x1="12" y1="16" x2="12.01" y2="16" />
        </svg>
        Economy
      </h3>

      <div className="empire-economy-content">
        {economy.informationSystems.length > 0 && (
          <div className="empire-economy-category">
            <div className="empire-economy-category-header">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20" />
                <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z" />
              </svg>
              <span>Information Systems</span>
            </div>
            <div className="empire-tags">
              {economy.informationSystems.map((item, i) => (
                <span key={i} className="empire-tag empire-tag-info">
                  {item}
                </span>
              ))}
            </div>
          </div>
        )}

        {economy.monetary.length > 0 && (
          <div className="empire-economy-category">
            <div className="empire-economy-category-header">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <circle cx="12" cy="12" r="8" />
                <path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3" />
                <line x1="12" y1="17" x2="12.01" y2="17" />
              </svg>
              <span>Monetary</span>
            </div>
            <div className="empire-tags">
              {economy.monetary.map((item, i) => (
                <span key={i} className="empire-tag empire-tag-monetary">
                  {item}
                </span>
              ))}
            </div>
          </div>
        )}

        {economy.trade.length > 0 && (
          <div className="empire-economy-category">
            <div className="empire-economy-category-header">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M8 3H5a2 2 0 0 0-2 2v3" />
                <path d="M21 8V5a2 2 0 0 0-2-2h-3" />
                <path d="M3 16v3a2 2 0 0 0 2 2h3" />
                <path d="M16 21h3a2 2 0 0 0 2-2v-3" />
                <line x1="7" y1="12" x2="17" y2="12" />
              </svg>
              <span>Trade</span>
            </div>
            <div className="empire-tags">
              {economy.trade.map((item, i) => (
                <span key={i} className="empire-tag empire-tag-trade">
                  {item}
                </span>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
