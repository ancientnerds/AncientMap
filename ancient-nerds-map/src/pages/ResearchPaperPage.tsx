/**
 * ResearchPaperPage — Dedicated public page for a single research paper.
 * URL: /research.html?slug=paper-slug-here
 * SEO-friendly, shareable, renders full paper with attribution.
 */

import { useState, useEffect, useMemo, useCallback, useRef } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import AiNoticeBanner from '../components/layout/AiNoticeBanner'
import PageHeader from '../components/layout/PageHeader'
import QualityBadge, { type QualityScore } from '../components/theo/QualityBadge'
import '../styles/theo.css'

interface PaperData {
  id: string
  question: string
  slug: string
  published_by: string
  published_at: string
  result: {
    report: string
    title?: string
    quality_score?: QualityScore | null
  } | null
  sites_found: number
  tools_used: number
  duration_ms: number | null
}

interface TtsStatus {
  has_audio: boolean
  audio_url: string | null
  chars_generated: number | null
  status: string | null
}

type RefGroup = 'Academic' | 'Reputable' | 'PDF' | 'Video' | 'Other'

interface Reference {
  num: number
  title: string
  url: string
  accessed?: string
  group: RefGroup
}

const GROUP_ORDER: RefGroup[] = ['Academic', 'Reputable', 'PDF', 'Video', 'Other']

const GROUP_LABEL: Record<RefGroup, string> = {
  Academic: 'Academic sources',
  Reputable: 'Reputable sources',
  PDF: 'PDFs & archives',
  Video: 'Video sources',
  Other: 'Other sources',
}

/** Split paper markdown at the first `## References` heading. */
function splitBodyAndRefs(report: string): { body: string; refsText: string } {
  const match = report.match(/\n#{2,3}\s+References\s*\n/)
  if (!match || match.index === undefined) {
    return { body: report, refsText: '' }
  }
  const body = report.slice(0, match.index)
  const refsText = report.slice(match.index + match[0].length)
  return { body, refsText }
}

/**
 * Parse the references section into structured records and group them.
 * Line format (from CitationRegistry.format_references_list):
 *   `[N] Title — URL (accessed YYYY-MM-DD) [Tier]`
 * Tier is optional; mdash may be rendered as `—` or ` - `.
 */
function parseReferences(refsText: string): Reference[] {
  if (!refsText.trim()) return []

  const refs: Reference[] = []
  // Each line is one entry; ignore blank lines.
  for (const rawLine of refsText.split('\n')) {
    const line = rawLine.trim()
    if (!line) continue

    // Match `[N] ...`
    const numMatch = line.match(/^\[(\d+)\]\s+(.+)$/)
    if (!numMatch) continue
    const num = parseInt(numMatch[1], 10)
    const rest = numMatch[2]

    // Split title/URL on `—` (em-dash) or ` - ` — we emit em-dash in Python but
    // be lenient for manually edited entries.
    const dashMatch = rest.match(/^(.+?)\s+[—–-]\s+(https?:\/\/\S+)(.*)$/)
    if (!dashMatch) continue
    const title = dashMatch[1].trim()
    const url = dashMatch[2].trim()
    const tail = dashMatch[3] || ''

    // Optional: `(accessed YYYY-MM-DD)`
    const accessedMatch = tail.match(/\(accessed\s+(\d{4}-\d{2}-\d{2})\)/)
    const accessed = accessedMatch ? accessedMatch[1] : undefined

    // Optional: `[Tier]` — Academic / Reputable
    const tierMatch = tail.match(/\[(Academic|Reputable)\]/)
    const tierLabel = tierMatch ? tierMatch[1] : null

    // Classify into visual group
    let group: RefGroup
    if (tierLabel === 'Academic') group = 'Academic'
    else if (tierLabel === 'Reputable') group = 'Reputable'
    else if (/youtu\.?be/.test(url)) group = 'Video'
    else if (/^\[PDF\]/.test(title) || /\.pdf(?:$|\?)/.test(url)) group = 'PDF'
    else group = 'Other'

    // Strip the `[PDF]` prefix Google adds to some titles — cosmetic
    const cleanTitle = title.replace(/^\[PDF\]\s*/, '')

    refs.push({ num, title: cleanTitle, url, accessed, group })
  }

  return refs
}

/**
 * Pre-process body markdown so each inline `[N]` becomes a link to `#ref-N`.
 * We use `[\[N\]](#ref-N)` — the backslash-escapes make the brackets literal
 * text inside the link, so the rendered DOM is `<a href="#ref-N">[N]</a>`.
 *
 * Skipped: `[N]` where N maps to no known reference (left as plain text so
 * any residual hallucinations are visible rather than silently linked).
 */
function wireCitationAnchors(body: string, knownNums: Set<number>): string {
  return body.replace(/\[(\d+)\]/g, (orig, numStr) => {
    const n = parseInt(numStr, 10)
    if (!knownNums.has(n)) return orig
    return `[\\[${numStr}\\]](#ref-${numStr})`
  })
}

export default function ResearchPaperPage() {
  const [paper, setPaper] = useState<PaperData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [ttsStatus, setTtsStatus] = useState<TtsStatus | null>(null)
  const [isPlaying, setIsPlaying] = useState(false)
  const [audioProgress, setAudioProgress] = useState(0)
  const audioRef = useRef<HTMLAudioElement | null>(null)
  const progressRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const slug = useMemo(() => {
    const params = new URLSearchParams(window.location.search)
    return params.get('slug') || ''
  }, [])

  useEffect(() => {
    if (!slug) {
      setError('No paper specified')
      setLoading(false)
      return
    }

    fetch(`/api/theo/public/${slug}`)
      .then(r => {
        if (!r.ok) throw new Error('Paper not found')
        return r.json()
      })
      .then((data: PaperData) => {
        setPaper(data)
        const title = data.result?.title || data.question
        document.title = `${title} — Ancient Nerds Research`
        // Update OG meta tags
        const setMeta = (prop: string, content: string) => {
          let el = document.querySelector(`meta[property="${prop}"]`) as HTMLMetaElement | null
          if (!el) {
            el = document.createElement('meta')
            el.setAttribute('property', prop)
            document.head.appendChild(el)
          }
          el.content = content
        }
        setMeta('og:title', title)
        setMeta('og:description', `Research paper by ${data.published_by} on Ancient Nerds Research`)
        setMeta('og:url', window.location.href)
        if (data.id) {
          setMeta('og:image', `${window.location.origin}/data/research-images/${data.id}/cover.png`)
        }
      })
      .catch(() => setError('Paper not found'))
      .finally(() => setLoading(false))
  }, [slug])

  // Fetch TTS audio status when slug is available
  useEffect(() => {
    if (!slug) return
    fetch(`/api/theo/public/${slug}/tts-status`)
      .then(r => r.ok ? r.json() : null)
      .then((data: TtsStatus | null) => {
        setTtsStatus(data)
      })
      .catch(() => setTtsStatus(null))
  }, [slug])

  // Set up Media Session when audio is ready
  useEffect(() => {
    if (!ttsStatus?.has_audio || !ttsStatus.audio_url || !paper) return

    if (!('mediaSession' in navigator)) return
    const title = paper.result?.title || paper.question
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
  }, [ttsStatus, paper, isPlaying])

  const handleShare = useCallback(() => {
    if (navigator.share) {
      navigator.share({
        title: paper?.result?.title || paper?.question || 'Research Paper',
        url: window.location.href,
      }).catch(() => { /* cancelled */ })
    } else {
      navigator.clipboard.writeText(window.location.href)
    }
  }, [paper])

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

  const mdComponents = useMemo(() => ({
    a: ({ href, children, ...props }: React.AnchorHTMLAttributes<HTMLAnchorElement>) => {
      if (href?.startsWith('site:')) {
        const siteId = href.slice(5)
        return <a {...props} href={`/site.html?id=${siteId}`} target="_blank" rel="noopener noreferrer">{children}</a>
      }
      if (href?.startsWith('#')) {
        return (
          <a
            {...props}
            href={href}
            className="theo-cite-link"
            onClick={(e) => {
              e.preventDefault()
              const id = href.slice(1)
              const target = document.getElementById(id)
              if (target) {
                let node: HTMLElement | null = target
                while (node) {
                  if (node.tagName === 'DETAILS') {
                    (node as HTMLDetailsElement).open = true
                  }
                  node = node.parentElement
                }
                target.scrollIntoView({ behavior: 'smooth', block: 'center' })
                target.classList.add('theo-ref-highlight')
                setTimeout(() => target.classList.remove('theo-ref-highlight'), 1600)
              }
            }}
          >{children}</a>
        )
      }
      return <a {...props} href={href} target="_blank" rel="noopener noreferrer">{children}</a>
    },
    img: ({ src, alt }: React.ImgHTMLAttributes<HTMLImageElement>) => (
      <span data-gallery={alt?.startsWith('gallery:') ? alt.slice(8).split('|')[0] : ''}>
        <img src={src || ''} alt={alt || ''} style={{ maxHeight: 400, borderRadius: 4 }} />
      </span>
    ),
  }), [])

  // Derived values from the loaded paper
  const { bodyWithAnchors, groupedRefs, totalRefs } = useMemo(() => {
    if (!paper?.result) return { bodyWithAnchors: '', groupedRefs: {} as Record<RefGroup, Reference[]>, totalRefs: 0 }
    const { body, refsText } = splitBodyAndRefs(paper.result.report)
    const refs = parseReferences(refsText)
    const knownNums = new Set(refs.map(r => r.num))
    const wired = wireCitationAnchors(body, knownNums)
    const grouped: Record<RefGroup, Reference[]> = {
      Academic: [], Reputable: [], PDF: [], Video: [], Other: [],
    }
    for (const r of refs) grouped[r.group].push(r)
    // Keep numeric order within each group
    for (const g of GROUP_ORDER) grouped[g].sort((a, b) => a.num - b.num)
    return { bodyWithAnchors: wired, groupedRefs: grouped, totalRefs: refs.length }
  }, [paper])

  if (loading) {
    return (
      <div className="theo-page">
        <PageHeader currentPage="theo">
          <span className="page-header-title">Research</span>
        </PageHeader>
        <div style={{ textAlign: 'center', padding: '60px 20px', color: 'var(--text-dimmed)' }}>Loading...</div>
      </div>
    )
  }

  if (error || !paper?.result) {
    return (
      <div className="theo-page">
        <PageHeader currentPage="theo">
          <span className="page-header-title">Research</span>
        </PageHeader>
        <div style={{ textAlign: 'center', padding: '60px 20px' }}>
          <div style={{ color: 'var(--text-dimmed)', fontSize: 16, marginBottom: 12 }}>{error || 'Paper not found'}</div>
          <a href="/theo.html" style={{ color: 'var(--brand-primary)' }}>Browse the Research Library</a>
        </div>
      </div>
    )
  }

  const title = paper.result.title || paper.question
  const readingMinutes = Math.ceil(paper.result.report.split(/\s+/).length / 200)

  return (
    <div className="theo-page">
      <PageHeader currentPage="theo">
        <span className="page-header-title">Research</span>
      </PageHeader>
      <AiNoticeBanner message="Research papers and illustrations are AI-generated. Always verify claims with original sources." />

        {paper.id && (
          <div className="theo-paper-hero">
            <img
              src={`/data/research-images/${paper.id}/cover.png`}
              alt=""
              className="theo-paper-hero-img"
            />
          </div>
        )}

        <div className="theo-paper-page">
        {/* Paper header */}
        <div className="theo-paper-header">
          <h1 className="theo-paper-title">{title}</h1>
          <div className="theo-paper-meta">
            <QualityBadge qualityScore={paper.result.quality_score} />
            <span style={{ color: 'var(--text-dimmed)', fontSize: 12 }}>{readingMinutes} min read</span>
            <span style={{ color: 'var(--text-muted)', fontSize: 12 }}>
              by {paper.published_by}
            </span>
            {paper.published_at && (
              <span style={{ color: 'var(--text-dimmed)', fontSize: 12 }}>
                {new Date(paper.published_at).toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric' })}
              </span>
            )}
            <button className="theo-report-share" onClick={handleShare} title="Share paper" aria-label="Share paper">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/></svg>
            </button>
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

        {/* Paper body */}
        <div className="theo-paper-body theo-md-body">
          <ReactMarkdown remarkPlugins={[remarkGfm]} components={mdComponents}>
            {bodyWithAnchors}
          </ReactMarkdown>
        </div>

        {/* References — clustered, collapsible */}
        {totalRefs > 0 && (
          <div className="theo-refs-section">
            <h2 className="theo-refs-title">References <span className="theo-refs-count">({totalRefs})</span></h2>
            {GROUP_ORDER.map(group => {
              const items = groupedRefs[group]
              if (!items || items.length === 0) return null
              // Academic open by default; the rest collapsed.
              const defaultOpen = group === 'Academic'
              return (
                <details key={group} className="theo-ref-group" {...(defaultOpen ? { open: true } : {})}>
                  <summary className="theo-ref-summary">
                    <span className="theo-ref-group-name">{GROUP_LABEL[group]}</span>
                    <span className="theo-ref-group-count">{items.length}</span>
                  </summary>
                  <ol className="theo-ref-list">
                    {items.map(r => (
                      <li key={r.num} id={`ref-${r.num}`} className="theo-ref-item">
                        <span className="theo-ref-num">[{r.num}]</span>
                        <a href={r.url} target="_blank" rel="noopener noreferrer" className="theo-ref-link">
                          {r.title}
                        </a>
                        {r.accessed && (
                          <span className="theo-ref-accessed"> · accessed {r.accessed}</span>
                        )}
                      </li>
                    ))}
                  </ol>
                </details>
              )
            })}
          </div>
        )}

        {/* Back to library */}
        <div style={{ textAlign: 'center', padding: '32px 0' }}>
          <a href="/theo.html" style={{ color: 'var(--brand-primary)', fontSize: 13, textDecoration: 'none' }}>
            Browse more research in the library
          </a>
        </div>
      </div>
    </div>
  )
}
