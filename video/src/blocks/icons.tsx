/** Line icons of the ClaimBoard (24x24 viewBox, stroked in the claim's status colour). */
import React from 'react'

export const ICONS = ['weight', 'ruler', 'clock', 'globe', 'tool', 'eye', 'scroll', 'star', 'question', 'people'] as const

export type IconName = (typeof ICONS)[number]

const PATHS: Record<IconName, string> = {
  weight: 'M6 8h12l2 12H4L6 8z M9 8a3 3 0 0 1 6 0',
  ruler: 'M3 17L17 3l4 4L7 21l-4-4z M7 13l2 2 M10 10l2 2 M13 7l2 2',
  clock: 'M12 3a9 9 0 1 0 0.01 0z M12 7v5l3 3',
  globe: 'M12 3a9 9 0 1 0 0.01 0z M3 12h18 M12 3c3 3 3 15 0 18 M12 3c-3 3-3 15 0 18',
  tool: 'M14 6a4 4 0 0 0 5 5l-9 9-3-3 9-9a4 4 0 0 0-2-2z',
  eye: 'M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12z M12 9a3 3 0 1 0 0.01 0z',
  scroll: 'M7 3h11v15a3 3 0 0 1-3 3H6a3 3 0 0 1-3-3v-2h11v2 M7 3a2 2 0 0 0-2 2v11',
  star: 'M12 3l2.7 5.6 6.1.9-4.4 4.3 1 6.1L12 17l-5.4 2.9 1-6.1L3.2 9.5l6.1-.9L12 3z',
  question: 'M9 9a3 3 0 1 1 4 2.8c-.6.3-1 .9-1 1.6V15 M12 19v.5',
  people: 'M9 11a3 3 0 1 0 0.01 0z M3 20a6 6 0 0 1 12 0 M17 11a2.5 2.5 0 1 0 0.01 0z M16 15a5 5 0 0 1 5 5',
}

export const Icon: React.FC<{ name: IconName; color: string; size: number }> = ({ name, color, size }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round">
    <path d={PATHS[name]} />
  </svg>
)
