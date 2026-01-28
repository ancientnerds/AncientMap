/**
 * Data types for Video Factory
 *
 * Standalone types that match the Ancient Nerds API response format.
 * No imports from main codebase - completely independent.
 */

// =============================================================================
// Site Data
// =============================================================================

/** Site data from API */
export interface Site {
  id: string;
  name: string;
  lat: number;
  lon: number;
  sourceId: string;
  type?: string;
  description?: string;
  location?: string;
  period?: string;
  sourceUrl?: string;
  imageUrl?: string;
  periodStart?: number | null;
  periodEnd?: number | null;
}

/** Site detail with full information */
export interface SiteDetail {
  id: string;
  source: string;
  sourceRecordId?: string;
  name: string;
  lat: number;
  lon: number;
  type?: string;
  period?: {
    start?: number | null;
    end?: number | null;
    name?: string;
  };
  country?: string;
  description?: string;
  thumbnail?: string;
  url?: string;
}

// =============================================================================
// Source Metadata
// =============================================================================

/** Source metadata */
export interface SourceMeta {
  id: string;
  name: string;
  description: string;
  color: string;
  icon?: string;
  category: string;
  recordCount: number;
  license?: string;
  attribution?: string;
  enabled: boolean;
  url?: string;
  isPrimary?: boolean;
}

// =============================================================================
// Category Data
// =============================================================================

/** Category information */
export interface Category {
  id: string;
  name: string;
  count: number;
  color?: string;
}

// =============================================================================
// Video Generation Types
// =============================================================================

/** Video format configuration */
export interface VideoFormat {
  width: number;
  height: number;
  fps: number;
  aspectRatio: '16:9' | '9:16';
}

/** Video format presets */
export const VIDEO_FORMATS = {
  teaser: {
    width: 1920,
    height: 1080,
    fps: 30,
    aspectRatio: '16:9' as const,
  },
  short: {
    width: 1080,
    height: 1920,
    fps: 30,
    aspectRatio: '9:16' as const,
  },
} as const;

/** Directive for video generation */
export interface Directive {
  type: 'teaser' | 'short' | 'capture';
  site?: string;
  siteId?: string;
  category?: string;
  country?: string;
  format?: '16:9' | '9:16';
  duration?: number;
  actions?: CaptureAction[];
  output?: string;
}

/** Available capture actions */
export type CaptureAction =
  | 'fly-to'
  | 'rotate'
  | 'popup'
  | 'search'
  | 'filter'
  | 'zoom-in'
  | 'zoom-out';

// =============================================================================
// API Response Types
// =============================================================================

/** Sites search response */
export interface SitesSearchResponse {
  sites: Site[];
  total: number;
  page: number;
  pageSize: number;
}

/** Site detail response */
export interface SiteDetailResponse {
  site: SiteDetail;
  relatedContent?: {
    images?: ContentItem[];
    videos?: ContentItem[];
    articles?: ContentItem[];
  };
}

/** Content item */
export interface ContentItem {
  source: string;
  id: string;
  title: string;
  thumbnail?: string;
  url?: string;
  metadata?: Record<string, unknown>;
}

// =============================================================================
// Render Configuration
// =============================================================================

/** Configuration for rendering a video */
export interface RenderConfig {
  compositionId: string;
  outputPath: string;
  format: VideoFormat;
  inputProps: Record<string, unknown>;
  durationInFrames?: number;
}

/** Site props for video compositions */
export interface SiteVideoProps {
  site: SiteDetail;
  captureFrames?: string[];
  duration?: number;
}

/** Teaser props for product teaser video */
export interface TeaserVideoProps {
  title: string;
  tagline: string;
  featuredSites: SiteDetail[];
  stats: {
    totalSites: number;
    categories: number;
    countries: number;
  };
  duration?: number;
}
