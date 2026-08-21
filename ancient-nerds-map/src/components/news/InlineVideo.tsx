/**
 * InlineVideo — click the poster, the YouTube player takes its place.
 *
 * The behaviour lived inside NewsCard until the story page wanted the same
 * thing (2026-08-21). Rather than a second copy of the play state, the
 * pause-the-others channel and the VPN hint, both sites render this and
 * bring their own poster through the render prop — the card's thumbnail
 * with its duration badges, the story page's figure. Only the poster
 * markup differs; the player does not.
 */

import { useState, useEffect, type ReactNode } from 'react'

/**
 * One card starting playback stops every other one. The event name predates
 * the story page and stays as it is: renaming it would only break the pause
 * between an already-mounted card and a newly mounted player.
 */
const PLAY_EVENT = 'newscard-play'

interface InlineVideoProps {
  videoId: string
  /** Deep-link offset into the video; 0 or null starts at the beginning. */
  startSeconds?: number | null
  /** Accessible iframe title — the headline, not "YouTube video player". */
  title: string
  /** Where "watch on YouTube" points when the embed refuses to load. */
  watchUrl: string
  /** Wrapper class for the embed, so each site keeps its own framing. */
  embedClassName: string
  /** The poster. Gets the play trigger; renders until playback starts. */
  children: (play: () => void) => ReactNode
}

export default function InlineVideo({
  videoId,
  startSeconds,
  title,
  watchUrl,
  embedClassName,
  children,
}: InlineVideoProps) {
  const [playing, setPlaying] = useState(false)
  const [showHint, setShowHint] = useState(false)

  // The hint only appears once the embed has had a few seconds to fail —
  // showing "not loading?" next to a video that is playing is noise.
  useEffect(() => {
    if (!playing) { setShowHint(false); return }
    const timer = setTimeout(() => setShowHint(true), 3000)
    return () => clearTimeout(timer)
  }, [playing])

  useEffect(() => {
    if (!playing) return
    const handler = (e: Event) => {
      if ((e as CustomEvent).detail !== videoId) setPlaying(false)
    }
    window.addEventListener(PLAY_EVENT, handler)
    return () => window.removeEventListener(PLAY_EVENT, handler)
  }, [playing, videoId])

  const play = () => {
    window.dispatchEvent(new CustomEvent(PLAY_EVENT, { detail: videoId }))
    setPlaying(true)
  }

  if (!playing) return <>{children(play)}</>

  return (
    <div className={embedClassName} onClick={e => e.stopPropagation()}>
      <iframe
        src={`https://www.youtube.com/embed/${videoId}?start=${startSeconds || 0}&autoplay=1`}
        allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share"
        referrerPolicy="strict-origin-when-cross-origin"
        allowFullScreen
        title={title}
      />
      {showHint && (
        <div className="news-card-embed-hint">
          Not loading? Disable VPN or{' '}
          <a href={watchUrl} target="_blank" rel="noopener noreferrer">watch on YouTube</a>
        </div>
      )}
    </div>
  )
}
