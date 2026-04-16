import { useEffect } from 'react'
import type { LibrarySource, ParentRef } from '../../types/library'

const TIER_LABELS: Record<number, { label: string; className: string }> = {
  1: { label: 'Academic', className: 'library-tier-academic' },
  2: { label: 'Reputable', className: 'library-tier-reputable' },
  3: { label: 'General', className: 'library-tier-general' },
}

const PARENT_LINKS: Record<string, { label: string; href: (id: string) => string }> = {
  story: { label: 'Story', href: () => '/news.html' },
  journal: { label: 'Journal', href: () => '/articles.html' },
  research: { label: 'Research', href: (id) => `/research.html?id=${id}` },
  site: { label: 'Site', href: (id) => `/site.html?id=${id}` },
}

interface LibraryDetailCardProps {
  source: LibrarySource
  onClose: () => void
}

export default function LibraryDetailCard({ source, onClose }: LibraryDetailCardProps) {
  const tier = TIER_LABELS[source.reliability_tier]

  useEffect(() => {
    const handler = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [onClose])

  return (
    <div className="library-detail-backdrop" onClick={onClose}>
      <div className="library-detail-card" onClick={e => e.stopPropagation()}>
        <button className="library-detail-close" onClick={onClose}>&times;</button>

        <div className="library-detail-header">
          {source.domain && (
            <img
              className="library-detail-favicon"
              src={`https://www.google.com/s2/favicons?domain=${source.domain}&sz=64`}
              alt=""
              width={24}
              height={24}
            />
          )}
          <div>
            <h3 className="library-detail-title">{source.title}</h3>
            <span className="library-detail-domain">{source.domain}</span>
            {tier && <span className={`library-card-tier ${tier.className}`}>{tier.label}</span>}
          </div>
        </div>

        {source.snippet && (
          <p className="library-detail-snippet">{source.snippet}</p>
        )}

        <a
          className="library-detail-visit"
          href={source.url}
          target="_blank"
          rel="noopener noreferrer"
        >
          Visit source &rarr;
        </a>

        {source.parent_refs.length > 0 && (
          <div className="library-detail-cited-in">
            <h4>Cited in</h4>
            <ul className="library-detail-refs">
              {source.parent_refs.map((ref: ParentRef, i: number) => {
                const link = PARENT_LINKS[ref.type]
                return (
                  <li key={`${ref.type}-${ref.id}-${i}`}>
                    <span className="library-card-type-pill">{link?.label || ref.type}</span>
                    {link ? (
                      <a href={link.href(ref.id)} target="_blank" rel="noopener noreferrer">{ref.title}</a>
                    ) : (
                      <span>{ref.title}</span>
                    )}
                  </li>
                )
              })}
            </ul>
          </div>
        )}
      </div>
    </div>
  )
}
