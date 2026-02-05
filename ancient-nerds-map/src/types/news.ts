export interface NewsVideoInfo {
  id: string
  title: string
  channel_name: string
  channel_id: string
  published_at: string
  thumbnail_url: string | null
  duration_minutes: number | null
}

export interface NewsItemData {
  id: number
  headline: string
  summary: string
  post_text: string | null
  facts: string[] | null
  timestamp_range: string | null
  timestamp_seconds: number | null
  screenshot_url: string | null
  youtube_url: string | null
  youtube_deep_url: string | null
  video: NewsVideoInfo
  created_at: string
  site_id: string | null
  site_name: string | null
  site_lat: number | null
  site_lon: number | null
  site_type: string | null
  site_period_name: string | null
  site_period_start: number | null
  site_country: string | null
  site_name_extracted: string | null
}

export interface NewsFeedResponse {
  items: NewsItemData[]
  total_count: number
  page: number
  has_more: boolean
}

export interface NewsStats {
  total_items: number
  total_videos: number
  total_channels: number
  total_articles: number
  total_duration_hours: number
  latest_item_date: string | null
}

export interface NewsChannel {
  id: string
  name: string
}

export interface NewsFilterSiteOption {
  id: string
  name: string
}

export interface NewsFilters {
  channels: NewsChannel[]
  sites: NewsFilterSiteOption[]
  categories: string[]
  periods: string[]
  countries: string[]
}

export interface ActiveFilters {
  channel: string | null
  site: string | null
  category: string | null
  period: string | null
  country: string | null
}
