import type { LibrarySource } from '../../types/library'

const TIER_LABELS: Record<number, { label: string; className: string }> = {
  1: { label: 'Academic', className: 'library-tier-academic' },
  2: { label: 'Reputable', className: 'library-tier-reputable' },
  3: { label: 'General', className: 'library-tier-general' },
}

interface LibraryCardProps {
  source: LibrarySource
  onClick: () => void
}

export default function LibraryCard({ source, onClick }: LibraryCardProps) {
  const tier = TIER_LABELS[source.reliability_tier]

  return (
    <button className="library-card" onClick={onClick} type="button">
      <div className="library-card-header">
        {source.domain && (
          <img
            className="library-card-favicon"
            src={`https://www.google.com/s2/favicons?domain=${source.domain}&sz=32`}
            alt=""
            width={16}
            height={16}
            loading="lazy"
          />
        )}
        <span className="library-card-domain">{source.domain || 'Unknown'}</span>
        {tier && <span className={`library-card-tier ${tier.className}`}>{tier.label}</span>}
      </div>
      <div className="library-card-title">{source.title}</div>
      <div className="library-card-footer">
        <span className="library-card-citations">Cited {source.citation_count}x</span>
        <div className="library-card-types">
          {source.source_types.slice(0, 2).map(t => (
            <span key={t} className="library-card-type-pill">{t}</span>
          ))}
          {source.source_types.length > 2 && (
            <span className="library-card-type-pill">+{source.source_types.length - 2}</span>
          )}
        </div>
      </div>
    </button>
  )
}
