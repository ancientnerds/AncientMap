export interface LibrarySource {
  id: string
  url: string
  title: string
  domain: string | null
  snippet: string | null
  reliability_tier: number
  citation_count: number
  source_types: string[]
  parent_refs: ParentRef[]
}

export interface ParentRef {
  type: 'story' | 'journal' | 'research' | 'site'
  id: string
  title: string
}

export interface LibraryPeriod {
  period: string
  slug: string
  count: number
}

export interface LibraryPeriodData {
  period: string
  slug: string
  total: number
  sources: LibrarySource[]
}

export interface LibraryStats {
  total_sources: number
  by_type: Record<string, number>
  by_tier: Record<number, number>
  top_domains: { domain: string; count: number }[]
  period_count: number
}

export interface LibrarySearchResponse {
  items: LibrarySource[]
  total: number
  page: number
  page_size: number
}
