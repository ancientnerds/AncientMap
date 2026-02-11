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

/** Tinted background + border for glassy card effect — intensity scales with significance. */
export function getSignificanceCardStyle(level: number): React.CSSProperties {
  if (level >= 9) return { background: 'rgba(192, 32, 35, 0.22)', borderColor: 'rgba(192, 32, 35, 0.35)' }
  if (level >= 7) return { background: 'rgba(212, 98, 42, 0.18)', borderColor: 'rgba(212, 98, 42, 0.30)' }
  if (level >= 5) return { background: 'rgba(212, 168, 67, 0.12)', borderColor: 'rgba(212, 168, 67, 0.22)' }
  if (level >= 3) return { background: 'rgba(91, 138, 114, 0.08)', borderColor: 'rgba(91, 138, 114, 0.16)' }
  return { background: 'rgba(255, 255, 255, 0.03)', borderColor: 'rgba(255, 255, 255, 0.08)' }
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
  ancient_astronauts: 'Ancient Astronauts',
  annunaki: 'Annunaki',
  lost_civilization: 'Lost Civilization',
  giants: 'Giants',
  supernatural: 'Supernatural',
  conspiracy: 'Conspiracy',
}

export function getNewsCategoryLabel(cat: string): string {
  return CATEGORY_LABELS[cat] || cat
}

const TOPIC_COLORS: Record<string, string> = {
  // Fieldwork (warm earth)
  excavation: '#c17f3e',
  survey: '#b89254',
  underwater: '#5e8fa8',
  // Artifacts (amber/gold)
  artifact: '#c9a84c',
  art: '#d4a05a',
  epigraphy: '#a89060',
  // Science (blue/cyan)
  dating: '#4a90b8',
  remote_sensing: '#5c7eb0',
  technology: '#6a88b0',
  bioarchaeology: '#5d9a8a',
  // Cultural (green)
  heritage: '#6b9e6b',
  conservation: '#7aab6f',
  architecture: '#8a9e6b',
  // Theory (neutral)
  theory: '#8888a0',
  general: '#7a7a8a',
  // Alternative (purple range)
  ancient_astronauts: '#9b70c0',
  annunaki: '#8a6ab0',
  lost_civilization: '#a078b8',
  giants: '#b07aaa',
  supernatural: '#8860a8',
  conspiracy: '#7a6498',
}

export function getTopicColor(topic: string): string {
  return TOPIC_COLORS[topic] || '#7a7a8a'
}
