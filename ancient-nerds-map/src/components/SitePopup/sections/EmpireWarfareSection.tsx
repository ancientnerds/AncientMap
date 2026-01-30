/**
 * Empire Warfare Section
 *
 * Displays military technology data including fortifications,
 * weapons, armor, animals, and naval capabilities.
 */

import { SeshatWarfareData } from '../../../types/seshat'
import { formatWarfareDisplay } from '../../../services/seshatService'

interface EmpireWarfareSectionProps {
  warfare: SeshatWarfareData | undefined
}

export default function EmpireWarfareSection({ warfare }: EmpireWarfareSectionProps) {
  if (!warfare) return null

  const display = formatWarfareDisplay(warfare)

  // Check if we have any data to display
  const hasData = display.fortifications.length > 0 ||
    display.weapons.length > 0 ||
    display.armor.length > 0 ||
    display.animals.length > 0 ||
    display.naval !== 'None'

  if (!hasData) return null

  return (
    <div className="empire-section empire-warfare-section">
      <h3 className="empire-section-title">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M14.5 17.5L3 6V3h3l11.5 11.5" />
          <path d="M13 19l6-6" />
          <path d="M16 16l4 4" />
          <path d="M19 21l2-2" />
        </svg>
        Military Technology
      </h3>

      <div className="empire-warfare-content">
        {display.fortifications.length > 0 && (
          <div className="empire-warfare-category">
            <div className="empire-warfare-category-header">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M3 21h18" />
                <path d="M4 21V10a1 1 0 0 1 1-1h2a1 1 0 0 1 1 1v11" />
                <path d="M8 21V6a1 1 0 0 1 1-1h2a1 1 0 0 1 1 1v15" />
                <path d="M12 21V3a1 1 0 0 1 1-1h2a1 1 0 0 1 1 1v18" />
                <path d="M16 21V6a1 1 0 0 1 1-1h2a1 1 0 0 1 1 1v15" />
              </svg>
              <span>Fortifications</span>
            </div>
            <div className="empire-tags">
              {display.fortifications.map((item, i) => (
                <span key={i} className="empire-tag empire-tag-fortification">
                  {item}
                </span>
              ))}
            </div>
          </div>
        )}

        {display.weapons.length > 0 && (
          <div className="empire-warfare-category">
            <div className="empire-warfare-category-header">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M14.5 17.5L3 6V3h3l11.5 11.5" />
                <path d="M13 19l6-6" />
                <path d="M16 16l4 4" />
              </svg>
              <span>Weapons</span>
            </div>
            <div className="empire-tags">
              {display.weapons.map((item, i) => (
                <span key={i} className="empire-tag empire-tag-weapon">
                  {item}
                </span>
              ))}
            </div>
          </div>
        )}

        {display.armor.length > 0 && (
          <div className="empire-warfare-category">
            <div className="empire-warfare-category-header">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
              </svg>
              <span>Armor</span>
            </div>
            <div className="empire-tags">
              {display.armor.map((item, i) => (
                <span key={i} className="empire-tag empire-tag-armor">
                  {item}
                </span>
              ))}
            </div>
          </div>
        )}

        {display.animals.length > 0 && (
          <div className="empire-warfare-category">
            <div className="empire-warfare-category-header">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <circle cx="12" cy="8" r="4" />
                <path d="M4 20v-2a4 4 0 0 1 4-4h8a4 4 0 0 1 4 4v2" />
                <path d="M8 4l-2-2" />
                <path d="M16 4l2-2" />
              </svg>
              <span>War Animals</span>
            </div>
            <div className="empire-tags">
              {display.animals.map((item, i) => (
                <span key={i} className="empire-tag empire-tag-animal">
                  {item}
                </span>
              ))}
            </div>
          </div>
        )}

        {display.naval !== 'None' && (
          <div className="empire-warfare-category">
            <div className="empire-warfare-category-header">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M2 20a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2" />
                <path d="M4 18l-1.7-4.3A1 1 0 0 1 3.2 12H4l2-2h12l2 2h.8a1 1 0 0 1 .9 1.7L20 18" />
                <path d="M12 6V2" />
                <path d="M12 12V6" />
              </svg>
              <span>Naval</span>
            </div>
            <div className="empire-tags">
              <span className="empire-tag empire-tag-naval">{display.naval}</span>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
