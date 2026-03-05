import { useState, type ReactNode } from 'react'
import SiteMetadata from '../../SiteMetadata'
import { hasDisplayableRawData } from '../../../config/sourceFields'
import { isWikipediaUrl } from '../../../services/imageService'
import type { DescriptionSectionProps } from '../types'

/** Truncate domain label for display (e.g. "hiddenincatours.com" → "hiddenincatours") */
function shortDomain(domain: string): string {
  return domain.replace(/^www\./, '').replace(/\.(com|org|net|edu|gov|io|co\.uk)$/, '')
}

/** Build a citation lookup map from descriptionCitations array */
function buildCitationMap(citations?: { n: number; url: string; title: string; domain: string }[]) {
  const map = new Map<number, { url: string; title: string; domain: string }>()
  if (citations) {
    for (const c of citations) map.set(c.n, c)
  }
  return map
}

/** Render description text with superscript citation links */
function renderWithCitations(
  text: string,
  citationMap: Map<number, { url: string; title: string; domain: string }>,
): ReactNode[] {
  const parts: ReactNode[] = []
  const regex = /\[(\d+)\]/g
  let lastIndex = 0
  let match: RegExpExecArray | null

  while ((match = regex.exec(text)) !== null) {
    // Text before the marker
    if (match.index > lastIndex) {
      parts.push(text.slice(lastIndex, match.index))
    }
    const num = parseInt(match[1], 10)
    const cite = citationMap.get(num)
    if (cite) {
      parts.push(
        <a
          key={`cite-${match.index}`}
          href={cite.url}
          target="_blank"
          rel="noopener noreferrer"
          className="popup-citation-sup"
          title={cite.title}
        >
          [{num}]
        </a>
      )
    } else {
      parts.push(
        <sup key={`cite-${match.index}`} className="popup-citation-sup">[{num}]</sup>
      )
    }
    lastIndex = regex.lastIndex
  }

  // Trailing text
  if (lastIndex < text.length) {
    parts.push(text.slice(lastIndex))
  }

  return parts
}

/** Strip [N] citation markers from text */
function stripCitations(text: string): string {
  return text.replace(/\s*\[\d+\]/g, '')
}

export function DescriptionSection({
  description,
  sourceId,
  rawData,
  rawDataLoading,
  sourceUrl,
  onAdminClick,
  isEmpireMode = false,
  isFounder = false,
  bestWikiUrl,
  sourceLanguage,
  referenceLinks,
  descriptionCitations,
}: DescriptionSectionProps) {
  const [showCitations, setShowCitations] = useState(false)
  const [showMoreInfo, setShowMoreInfo] = useState(false)

  const hasMoreInfo = !rawDataLoading && hasDisplayableRawData(sourceId, rawData)

  // Extract domain for source attribution (e.g. "de.wikipedia.org")
  const wikiSourceDomain = bestWikiUrl && sourceLanguage && sourceLanguage !== 'en'
    ? (() => { try { return new URL(bestWikiUrl).hostname } catch { return null } })()
    : null

  const hasCitations = /\[\d+\]/.test(description || '')
  const citationMap = buildCitationMap(descriptionCitations)

  // Build unique citation source domains for favicon display
  const citationSources: { domain: string; url: string; title: string; nums: number[] }[] = []
  const seenDomains = new Map<string, number>() // domain → index in citationSources
  // Wikipedia domain from sourceUrl is already shown via its own icon — skip it
  const skipDomains = new Set<string>()
  if (sourceUrl) {
    try { skipDomains.add(new URL(sourceUrl).hostname.replace(/^www\./, '')) } catch { /* skip */ }
  }
  if (descriptionCitations) {
    for (const c of descriptionCitations) {
      const d = c.domain.replace(/^www\./, '')
      if (skipDomains.has(d)) continue
      const existing = seenDomains.get(d)
      if (existing !== undefined) {
        citationSources[existing].nums.push(c.n)
      } else {
        seenDomains.set(d, citationSources.length)
        citationSources.push({ domain: c.domain, url: c.url, title: c.title, nums: [c.n] })
      }
    }
  }

  // Render description content
  let descriptionContent: ReactNode = null
  if (rawDataLoading && isEmpireMode) {
    descriptionContent = <p className="popup-description loading">Loading description from Wikipedia...</p>
  } else if (description) {
    if (hasCitations && showCitations) {
      descriptionContent = <p className="popup-description">{renderWithCitations(description, citationMap)}</p>
    } else if (hasCitations) {
      descriptionContent = <p className="popup-description">{stripCitations(description)}</p>
    } else {
      descriptionContent = <p className="popup-description">{description}</p>
    }
  } else if (isEmpireMode) {
    descriptionContent = <p className="popup-description empty">No description available</p>
  }

  return (
    <>
      {showMoreInfo ? (
        <SiteMetadata sourceId={sourceId} rawData={rawData} />
      ) : (
        <>
          {descriptionContent}

          {/* Source attribution for non-English wiki sources */}
          {wikiSourceDomain && bestWikiUrl && (
            <a
              href={bestWikiUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="popup-wiki-source-link"
              title={`Description sourced from ${wikiSourceDomain}`}
            >
              Source: {wikiSourceDomain} →
            </a>
          )}
        </>
      )}

      <div className="popup-links-section">
        {sourceUrl && isWikipediaUrl(sourceUrl) && (
          <a
            href={sourceUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="popup-link-item wikipedia"
            title="View on Wikipedia"
          >
            <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor">
              <path d="M12.09 13.119c-.936 1.932-2.217 4.548-2.853 5.728-.616 1.074-1.127.931-1.532.029-1.406-3.321-4.293-9.144-5.651-12.409-.251-.601-.441-.987-.619-1.139-.181-.15-.554-.24-1.122-.271C.103 5.033 0 4.982 0 4.898v-.455l.052-.045c.924-.005 5.401 0 5.401 0l.051.045v.434c0 .119-.075.176-.225.176l-.564.031c-.485.029-.727.164-.727.436 0 .135.053.33.166.601 1.082 2.646 4.818 10.521 4.818 10.521l.136.046 2.411-4.81-.482-1.067-1.658-3.264s-.318-.654-.428-.872c-.728-1.443-.712-1.518-1.447-1.617-.207-.023-.313-.05-.313-.149v-.468l.06-.045h4.292l.113.037v.451c0 .105-.076.15-.227.15l-.308.047c-.792.061-.661.381-.136 1.422l1.582 3.252 1.758-3.504c.293-.64.233-.801.111-.947-.07-.084-.305-.22-.812-.24l-.201-.021c-.052 0-.098-.015-.145-.051-.045-.031-.067-.076-.067-.129v-.427l.061-.045c1.247-.008 4.043 0 4.043 0l.059.045v.436c0 .121-.059.178-.193.178-.646.03-.782.095-1.023.439-.12.186-.375.589-.646 1.039l-2.301 4.273-.065.135 2.792 5.712.17.048 4.396-10.438c.154-.422.129-.722-.064-.895-.197-.172-.346-.273-.857-.295l-.42-.016c-.061 0-.105-.014-.152-.045-.043-.029-.072-.075-.072-.119v-.436l.059-.045h4.961l.041.045v.437c0 .119-.074.18-.209.18-.648.03-1.127.18-1.443.421-.314.255-.557.616-.736 1.067 0 0-4.043 9.258-5.426 12.339-.525 1.007-1.053.917-1.503-.031-.571-1.171-1.773-3.786-2.646-5.71l.053-.036z"/>
            </svg>
          </a>
        )}

        {/* Citation source favicons */}
        {citationSources.map((src, i) => {
          const label = `[${src.nums.join(',')}] ${src.title}`
          return (
            <a
              key={`cite-src-${i}`}
              href={src.url}
              target="_blank"
              rel="noopener noreferrer"
              className="popup-link-item cite-source"
              title={label}
            >
              <img
                src={`https://www.google.com/s2/favicons?domain=${src.domain}&sz=32`}
                alt={label}
                width="20"
                height="20"
                loading="lazy"
                onError={e => { (e.target as HTMLImageElement).style.display = 'none' }}
              />
            </a>
          )
        })}

        {/* Reference links — favicon + domain buttons */}
        {referenceLinks?.map((ref, i) => (
          <a
            key={i}
            href={ref.url}
            target="_blank"
            rel="noopener noreferrer"
            className="popup-link-item ref-link"
            title={ref.title}
          >
            <img
              src={`https://www.google.com/s2/favicons?domain=${ref.domain}&sz=16`}
              alt=""
              width="16"
              height="16"
              className="ref-link-favicon"
              loading="lazy"
              onError={e => { (e.target as HTMLImageElement).style.display = 'none' }}
            />
            <span className="ref-link-label">{shortDomain(ref.domain)}</span>
          </a>
        ))}

        <div className="popup-links-spacer" />

        {/* More Info toggle button */}
        {hasMoreInfo && (
          <button
            className={`popup-link-item more-info-toggle${showMoreInfo ? ' active' : ''}`}
            onClick={() => setShowMoreInfo(!showMoreInfo)}
            title={showMoreInfo ? 'Show description' : 'Show source data'}
          >
            ℹ
          </button>
        )}

        {/* Citation toggle button */}
        {hasCitations && (
          <button
            className={`popup-link-item cite-toggle${showCitations ? ' active' : ''}`}
            onClick={() => setShowCitations(!showCitations)}
            title={showCitations ? 'Hide citations' : 'Show citations'}
          >
            [1]
          </button>
        )}

        {/* Admin button - subtle, on the right - only for founder on sites */}
        {isFounder && !isEmpireMode && (
          <button
            className="popup-link-item admin"
            onClick={onAdminClick}
            title="Admin Edit"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <circle cx="12" cy="12" r="3"/>
              <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"/>
            </svg>
          </button>
        )}
      </div>
    </>
  )
}
