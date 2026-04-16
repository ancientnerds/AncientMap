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

/** NERV panel card style — overrides border, corner brackets, and hover glow with significance color. */
export function getSignificanceNervStyle(level: number): React.CSSProperties | undefined {
  if (level >= 9) return {
    background: 'rgba(192, 32, 35, 0.22)',
    borderColor: 'rgba(192, 32, 35, 0.35)',
    '--nerv-cb-color': 'rgba(192, 32, 35, 0.5)',
    '--sig-hover-border': 'rgba(192, 32, 35, 0.55)',
    '--sig-hover-glow': 'rgba(192, 32, 35, 0.15)',
  } as React.CSSProperties
  if (level >= 7) return {
    background: 'rgba(212, 98, 42, 0.18)',
    borderColor: 'rgba(212, 98, 42, 0.30)',
    '--nerv-cb-color': 'rgba(212, 98, 42, 0.45)',
    '--sig-hover-border': 'rgba(212, 98, 42, 0.50)',
    '--sig-hover-glow': 'rgba(212, 98, 42, 0.12)',
  } as React.CSSProperties
  if (level >= 5) return {
    background: 'rgba(212, 168, 67, 0.12)',
    borderColor: 'rgba(212, 168, 67, 0.22)',
    '--nerv-cb-color': 'rgba(212, 168, 67, 0.38)',
    '--sig-hover-border': 'rgba(212, 168, 67, 0.40)',
    '--sig-hover-glow': 'rgba(212, 168, 67, 0.10)',
  } as React.CSSProperties
  if (level >= 3) return {
    background: 'rgba(91, 138, 114, 0.08)',
    borderColor: 'rgba(91, 138, 114, 0.16)',
    '--nerv-cb-color': 'rgba(91, 138, 114, 0.35)',
    '--sig-hover-border': 'rgba(91, 138, 114, 0.30)',
    '--sig-hover-glow': 'rgba(91, 138, 114, 0.08)',
  } as React.CSSProperties
  return undefined
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
  // Science & dating (blue)
  dating: '#4a9fd4',
  bioarchaeology: '#3db5b0',
  remote_sensing: '#5a8ec4',
  technology: '#6c9fd0',
  // Fieldwork (teal → earth)
  excavation: '#c48840',
  survey: '#a89050',
  underwater: '#3aa0a8',
  // Artifacts & records (amber/gold)
  artifact: '#d4a038',
  art: '#cc8844',
  epigraphy: '#b8983c',
  architecture: '#c4963a',
  // Cultural & heritage (green)
  heritage: '#5daa5d',
  conservation: '#72b860',
  // Theory & general (neutral grey)
  theory: '#8888a8',
  general: '#7a7a90',
  archaeoastronomy: '#6888b8',
  // Speculative (purple → red)
  lost_civilization: '#a070cc',
  ancient_astronauts: '#bb66aa',
  annunaki: '#c46090',
  giants: '#cc5566',
  supernatural: '#9060b8',
  conspiracy: '#886098',
  // Accuracy warning (brand red)
  unverified: '#c02023',
}

/** Canonical order: scientific → fieldwork → artifacts → cultural → general → speculative */
const TOPIC_ORDER: string[] = [
  'dating', 'bioarchaeology', 'remote_sensing', 'technology',
  'excavation', 'survey', 'underwater',
  'artifact', 'art', 'epigraphy', 'architecture',
  'heritage', 'conservation',
  'archaeoastronomy', 'theory', 'general',
  'lost_civilization', 'ancient_astronauts', 'annunaki', 'giants', 'supernatural', 'conspiracy',
]

export function getTopicColor(topic: string): string {
  return TOPIC_COLORS[topic] || '#7a7a90'
}

/** Sort topics from scientific to fringe using canonical order. Unknown topics go to the end. */
export function sortTopics(topics: string[]): string[] {
  return [...topics].sort((a, b) => {
    const ai = TOPIC_ORDER.indexOf(a)
    const bi = TOPIC_ORDER.indexOf(b)
    return (ai === -1 ? 999 : ai) - (bi === -1 ? 999 : bi)
  })
}
