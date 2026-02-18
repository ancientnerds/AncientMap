import './page-header.css'

export interface StatItem {
  value: string | number
  label: string
  title?: string
  sep?: '→' | '·'
}

interface PageStatsBarProps {
  items: StatItem[]
}

export default function PageStatsBar({ items }: PageStatsBarProps) {
  if (items.length === 0) return null

  return (
    <div className="page-stats-bar">
      {items.map((item, i) => (
        <span key={i}>
          {i > 0 && item.sep && <span className="psb-sep">{item.sep}</span>}
          <span className="psb-item" title={item.title}>
            <strong>{typeof item.value === 'number' ? item.value.toLocaleString() : item.value}</strong> {item.label}
          </span>
        </span>
      ))}
    </div>
  )
}
