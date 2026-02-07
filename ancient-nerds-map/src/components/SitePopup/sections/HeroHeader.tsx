import type { HeroHeaderProps } from '../types'
import { MetadataBadge } from '../../metadata'

export function HeroHeader({
  title,
  heroImageSrc,
  isLoadingImages = false,
  sourceInfo,
  sourceName,
  sourceColor,
  category,
  period,
  catColor,
  periodColor,
  titleCopied,
  onTitleCopy,
  onTitleBarMouseDown,
  onTitleBarDoubleClick,
  isStandalone = false,
  windowState = 'normal',
  isEmpireMode = false
}: HeroHeaderProps) {
  // For empires, we don't show category/period badges
  const showBadges = !isEmpireMode && category && period

  return (
    <div
      className="popup-hero-header"
      onMouseDown={!isStandalone ? onTitleBarMouseDown : undefined}
      onDoubleClick={!isStandalone ? onTitleBarDoubleClick : undefined}
      style={{ cursor: !isStandalone && windowState !== 'maximized' ? 'move' : undefined }}
    >
      {heroImageSrc ? (
        <img
          src={heroImageSrc}
          alt={title}
          className="popup-hero-bg"
          draggable={false}
          onError={(e) => { e.currentTarget.style.display = 'none' }}
        />
      ) : isLoadingImages ? (
        <div className="popup-hero-loading">
          <div className="popup-hero-shimmer" />
        </div>
      ) : null}
      <div className="popup-hero-vignette" />
      <div className="popup-hero-content">
        <div className="popup-title-row">
          <h2
            className="popup-title-overlay"
            style={{
              fontSize: title.length > 50 ? '14px' : title.length > 40 ? '16px' : title.length > 30 ? '18px' : '22px'
            }}
          >{title}</h2>
          <button
            className={`title-action-btn ${titleCopied ? 'copied' : ''}`}
            onMouseDown={(e) => e.stopPropagation()}
            onClick={(e) => {
              e.stopPropagation()
              onTitleCopy()
            }}
            title="Copy name"
          >
            {titleCopied ? (
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <polyline points="20 6 9 17 4 12"></polyline>
              </svg>
            ) : (
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect>
                <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path>
              </svg>
            )}
          </button>
        </div>

        {sourceInfo?.url ? (
          <a
            href={sourceInfo.url}
            target="_blank"
            rel="noopener noreferrer"
            className="popup-source clickable"
            style={{ borderColor: sourceColor, color: sourceColor }}
            title={`Visit ${sourceInfo.name}`}
          >
            <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor">
              <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-1 17.93c-3.95-.49-7-3.85-7-7.93 0-.62.08-1.21.21-1.79L9 15v1c0 1.1.9 2 2 2v1.93zm6.9-2.54c-.26-.81-1-1.39-1.9-1.39h-1v-3c0-.55-.45-1-1-1H8v-2h2c.55 0 1-.45 1-1V7h2c1.1 0 2-.9 2-2v-.41c2.93 1.19 5 4.06 5 7.41 0 2.08-.8 3.97-2.1 5.39z"/>
            </svg>
            {sourceInfo.name}
            <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="external-icon">
              <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"></path>
              <polyline points="15 3 21 3 21 9"></polyline>
              <line x1="10" y1="14" x2="21" y2="3"></line>
            </svg>
          </a>
        ) : sourceName && (
          <div className="popup-source" style={{ borderColor: sourceColor, color: sourceColor }}>
            <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor">
              <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-1 17.93c-3.95-.49-7-3.85-7-7.93 0-.62.08-1.21.21-1.79L9 15v1c0 1.1.9 2 2 2v1.93zm6.9-2.54c-.26-.81-1-1.39-1.9-1.39h-1v-3c0-.55-.45-1-1-1H8v-2h2c.55 0 1-.45 1-1V7h2c1.1 0 2-.9 2-2v-.41c2.93 1.19 5 4.06 5 7.41 0 2.08-.8 3.97-2.1 5.39z"/>
            </svg>
            {sourceName}
          </div>
        )}

        {showBadges && (
          <div className="meta-badges">
            <MetadataBadge label={category!} color={catColor!} size="lg" />
            <MetadataBadge label={period!} color={periodColor!} size="lg" />
          </div>
        )}
      </div>
    </div>
  )
}
