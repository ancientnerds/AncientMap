/**
 * ResearchPaperPage — /research/{slug}, one public research paper.
 *
 * Since react-ssr Task 12 the route payload carries the whole paper: the
 * raw paper_summary_kwargs fields (snake_case) plus body_html, the
 * published report rendered by the pipeline's Python-markdown renderer.
 * The FIRST render — the one renderToString and every crawler sees — is
 * therefore the complete paper text with no fetch and no loading flash.
 *
 * Only the TTS audio player stays effect-based (fetching
 * /api/theo/public/{slug}/tts-status and wiring MediaSession): audio is a
 * client-side enhancement and may arrive after mount without changing the
 * server markup — the player button simply appears once status is known.
 */

import { useState, useEffect, useCallback, useRef } from 'react'
import AiNoticeBanner from '../components/layout/AiNoticeBanner'
import CommunityCta from '../components/layout/CommunityCta'
import PageHeader from '../components/layout/PageHeader'
import { useIsFounder } from '../hooks/useIsFounder'
import { isoDate } from '../seo/display'
import { useRoute } from '../seo/RouteContext'
import SanitizedMarkdownHtml from '../seo/SanitizedMarkdownHtml'
import { shareOrCopy } from '../utils/share'
import '../styles/theo.css'
import '../styles/story-page.css'

interface TtsStatus {
  has_audio: boolean
  audio_url: string | null
  chars_generated: number | null
  status: string | null
}

/** ~200 words/min over the visible text of the rendered body HTML. */
function readingMinutes(bodyHtml: string): number {
  const words = bodyHtml
    .replace(/<[^>]+>/g, ' ')
    .split(/\s+/)
    .filter(Boolean).length
  return Math.max(1, Math.ceil(words / 200))
}

export default function ResearchPaperPage() {
  const isFounder = useIsFounder()
  const [ttsStatus, setTtsStatus] = useState<TtsStatus | null>(null)
  const [isPlaying, setIsPlaying] = useState(false)
  const [audioProgress, setAudioProgress] = useState(0)
  const audioRef = useRef<HTMLAudioElement | null>(null)
  const progressRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const route = useRoute()
  const paper = route?.type === 'research' ? route : null
  const slug = paper?.slug ?? ''
  const title = paper?.title ?? ''

  // Fetch TTS audio status — client-side enhancement, not part of the
  // server markup (the payload carries no audio metadata).
  useEffect(() => {
    if (!slug) return
    fetch(`/api/theo/public/${slug}/tts-status`)
      .then(r => (r.ok ? r.json() : null))
      .then((data: TtsStatus | null) => {
        setTtsStatus(data)
      })
      .catch(() => setTtsStatus(null))
  }, [slug])

  // Set up Media Session when audio is ready
  useEffect(() => {
    if (!ttsStatus?.has_audio || !ttsStatus.audio_url || !title) return

    if (!('mediaSession' in navigator)) return
    navigator.mediaSession!.metadata = new MediaMetadata({
      title,
      artist: 'Ancient Nerds / English Expressive Narrator',
    })
    navigator.mediaSession!.playbackState = isPlaying ? 'playing' : 'none'

    navigator.mediaSession!.setActionHandler('play', () => {
      audioRef.current?.play()
    })
    navigator.mediaSession!.setActionHandler('pause', () => {
      audioRef.current?.pause()
    })
  }, [ttsStatus, title, isPlaying])

  const handleShare = useCallback(() => {
    void shareOrCopy(title || 'Research Paper', window.location.href)
  }, [title])

  const handlePlayPause = useCallback(() => {
    if (!ttsStatus?.has_audio || !ttsStatus.audio_url) return

    const audioUrl = ttsStatus.audio_url.startsWith('http')
      ? ttsStatus.audio_url
      : `${window.location.origin}${ttsStatus.audio_url}`

    if (!audioRef.current) {
      // Create audio element on first play (required for browser autoplay policy)
      audioRef.current = new Audio(audioUrl)
      audioRef.current.addEventListener('ended', () => {
        setIsPlaying(false)
        setAudioProgress(0)
        if (progressRef.current) clearInterval(progressRef.current)
        if ('mediaSession' in navigator) navigator.mediaSession!.playbackState = 'none'
      })
      audioRef.current.addEventListener('timeupdate', () => {
        if (audioRef.current) {
          setAudioProgress((audioRef.current.currentTime / audioRef.current.duration) * 100)
        }
      })
    }

    if (isPlaying) {
      audioRef.current.pause()
      setIsPlaying(false)
      if (progressRef.current) clearInterval(progressRef.current)
    } else {
      audioRef.current.play()
      setIsPlaying(true)
      // Poll progress every 500ms
      progressRef.current = setInterval(() => {
        if (audioRef.current) {
          setAudioProgress((audioRef.current.currentTime / audioRef.current.duration) * 100)
        }
      }, 500)
    }
  }, [ttsStatus, isPlaying])

  if (!paper) return null

  const author = paper.author || 'Theo'
  const pubDate = isoDate(paper.published_at)
  const summary = (paper.summary || '').trim()

  return (
    <div className="theo-page">
      <PageHeader currentPage="theo">
        <a href="/theo.html#research-library" className="page-header-title">Research</a>
      </PageHeader>
      <AiNoticeBanner message="Research paper text is AI-generated; images are from cited sources. Always verify claims with original sources." />

      {paper.hero_image_url && (
        <figure className="theo-paper-hero">
          <img src={paper.hero_image_url} alt={title} className="theo-paper-hero-img" />
        </figure>
      )}

      <div className="theo-paper-page">
        {/* Paper header */}
        <div className="theo-paper-header">
          <h1 className="theo-paper-title">{title}</h1>
          <div className="theo-paper-meta">
            <span style={{ color: 'var(--text-dimmed)', fontSize: 12 }}>
              {`${readingMinutes(paper.body_html)} min read`}
            </span>
            <span style={{ color: 'var(--text-muted)', fontSize: 12 }}>
              {`by ${author}${author === 'Theo' ? ' · AI research agent' : ''}`}
            </span>
            {pubDate && (
              <span style={{ color: 'var(--text-dimmed)', fontSize: 12 }}>{pubDate}</span>
            )}
            <span style={{ color: 'var(--text-dimmed)', fontSize: 12 }}>CC BY 4.0</span>
            <button className="theo-report-share" onClick={handleShare} title="Share paper" aria-label="Share paper">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/></svg>
            </button>
            {isFounder && (
              <button
                className="theo-report-share"
                onClick={() => window.open(`/research/${slug}/medium`, '_blank')}
                title="Copy for Medium (founders only)"
                aria-label="Copy for Medium"
              >
                <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><path d="M13.54 12a6.8 6.8 0 01-6.77 6.82A6.8 6.8 0 010 12a6.8 6.8 0 016.77-6.82A6.8 6.8 0 0113.54 12zM20.96 12c0 3.54-1.51 6.42-3.38 6.42-1.87 0-3.39-2.88-3.39-6.42s1.52-6.42 3.39-6.42 3.38 2.88 3.38 6.42M24 12c0 3.17-.53 5.75-1.19 5.75-.66 0-1.19-2.58-1.19-5.75s.53-5.75 1.19-5.75C23.47 6.25 24 8.83 24 12z"/></svg>
              </button>
            )}
            {ttsStatus?.has_audio && (
              <div className="tts-audio-player">
                <button
                  className="theo-report-share"
                  onClick={handlePlayPause}
                  title={isPlaying ? 'Pause narration' : 'Play narration'}
                  aria-label={isPlaying ? 'Pause narration' : 'Play narration'}
                  style={{ color: isPlaying ? 'var(--brand-primary)' : undefined }}
                >
                  {isPlaying ? (
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><rect x="6" y="4" width="4" height="16"/><rect x="14" y="4" width="4" height="16"/></svg>
                  ) : (
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><polygon points="5,3 19,12 5,21"/></svg>
                  )}
                </button>
                {isPlaying && audioProgress > 0 && (
                  <div className="tts-progress-bar">
                    <div className="tts-progress-fill" style={{ width: `${audioProgress}%` }} />
                  </div>
                )}
              </div>
            )}
          </div>
        </div>

        {/* Lead-in summary, exactly like the Python fragment rendered it. */}
        {summary && (
          <p>
            <strong>{summary}</strong>
          </p>
        )}

        {/* Paper body — the pipeline's markdown rendering, verbatim. */}
        <SanitizedMarkdownHtml
          html={paper.body_html}
          className="theo-paper-body theo-md-body"
        />

        {/* Back to the research library */}
        <div style={{ textAlign: 'center', padding: '32px 0' }}>
          <a href="/research/" style={{ color: 'var(--brand-primary)', fontSize: 13, textDecoration: 'none' }}>
            ← All research papers
          </a>
        </div>
        <CommunityCta />
      </div>
    </div>
  )
}
