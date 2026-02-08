/** Significance scoring helpers for news cards. */

const SIGNIFICANCE_LABELS: Record<number, string> = {
  10: 'Groundbreaking',
  9: 'Major Discovery',
  8: 'Breakthrough',
  7: 'Significant Find',
  6: 'New Research',
  5: 'Notable Update',
  4: 'Interesting',
  3: 'Routine Update',
  2: 'Background',
  1: 'Filler',
}

export function getSignificanceLabel(level: number): string {
  return SIGNIFICANCE_LABELS[level] || ''
}

export function getSignificanceColor(level: number): string {
  if (level >= 9) return '#c02023'      // hot red
  if (level >= 7) return '#d4622a'      // orange
  if (level >= 5) return '#d4a843'      // warm amber
  if (level >= 3) return '#5b8a72'      // muted green
  return 'rgba(255,255,255,0.3)'        // grey
}

/** Subtle tinted background + border for glassy card effect. */
export function getSignificanceCardStyle(level: number): React.CSSProperties {
  if (level >= 9) return { background: 'rgba(192, 32, 35, 0.12)', borderColor: 'rgba(192, 32, 35, 0.25)' }
  if (level >= 7) return { background: 'rgba(212, 98, 42, 0.10)', borderColor: 'rgba(212, 98, 42, 0.22)' }
  if (level >= 5) return { background: 'rgba(212, 168, 67, 0.08)', borderColor: 'rgba(212, 168, 67, 0.18)' }
  if (level >= 3) return { background: 'rgba(91, 138, 114, 0.06)', borderColor: 'rgba(91, 138, 114, 0.14)' }
  return { background: 'rgba(255, 255, 255, 0.02)', borderColor: 'rgba(255, 255, 255, 0.08)' }
}

const CATEGORY_LABELS: Record<string, string> = {
  excavation: 'Excavation',
  artifact: 'Artifact',
  architecture: 'Architecture',
  bioarchaeology: 'Bioarchaeology',
  dating: 'Dating',
  remote_sensing: 'Remote Sensing',
  underwater: 'Underwater',
  epigraphy: 'Epigraphy',
  conservation: 'Conservation',
  heritage: 'Heritage',
  theory: 'Theory',
  technology: 'Technology',
  survey: 'Survey',
  art: 'Art',
  general: 'General',
}

export function getNewsCategoryLabel(cat: string): string {
  return CATEGORY_LABELS[cat] || cat
}
