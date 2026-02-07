import './metadata.css'

export type BadgeSize = 'sm' | 'md' | 'lg'

interface MetadataBadgeProps {
  label: string
  color: string
  size?: BadgeSize
}

export function MetadataBadge({ label, color, size = 'sm' }: MetadataBadgeProps) {
  return (
    <span
      className={`meta-badge meta-badge-${size}`}
      style={{ borderColor: color, color }}
    >
      {label}
    </span>
  )
}
