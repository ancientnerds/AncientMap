/**
 * Pure helpers for the optional parts of a Claude-written paper (studio spec
 * 2026-09-26 §2.7, §3.7), shared by the page components and researchMeta so
 * the visible markup and the JSON-LD cannot drift apart.
 */

import type { ResearchCorrection } from '../../types/anRoute'

/** The id of a YouTube watch URL (`?v=`), '' when the URL has none. Shared by the story
 *  page's player and the story's JSON-LD. */
export function youtubeIdOf(url: string): string {
  try {
    return new URL(url).searchParams.get('v') || ''
  } catch {
    return ''
  }
}

/** The YouTube watch page of a video. */
export function youtubeWatchUrl(youtubeId: string): string {
  return `https://www.youtube.com/watch?v=${youtubeId}`
}

/**
 * A thumbnail every YouTube video has (hqdefault; maxresdefault exists only
 * for HD uploads). Used in JSON-LD only (a crawler reads it, the visitor's
 * browser does not): the page itself shows our own poster
 * (ResearchVideo.poster) or none, and never loads an image from YouTube
 * before the visitor clicks play.
 */
export function youtubeThumbnailUrl(youtubeId: string): string {
  return `https://i.ytimg.com/vi/${youtubeId}/hqdefault.jpg`
}

/** The newest correction day. The dates are YYYY-MM-DD, which order as strings. */
export function latestCorrectionDate(corrections: ResearchCorrection[]): string {
  return corrections.reduce((latest, c) => (c.date > latest ? c.date : latest), '')
}
