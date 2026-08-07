/**
 * ResearchPaperPage — Dedicated public page for a single research paper.
 * URL: /research.html?slug=paper-slug-here
 * SEO-friendly, shareable, renders full paper with attribution.
 */

import { useState, useEffect, useMemo, useCallback, useRef } from 'react'
import { createPortal } from 'react-dom'
import AiNoticeBanner from '../components/layout/AiNoticeBanner'
import PageHeader from '../components/layout/PageHeader'
import QualityBadge, { type QualityScore } from '../components/theo/QualityBadge'
import { splitIntoImageSegments } from '../components/theo/galleryParser'
import TheoPaperBody from '../components/theo/TheoPaperBody'
import ImageLightbox, { type LightboxImage } from '../components/ImageLightbox'
import { useIsFounder } from '../hooks/useIsFounder'
import { inferSourceType } from '../utils/sourceType'
import { anRoute } from '../types/anRoute'
import '../styles/theo.css'

interface HeroImage {
  src: string
  title: string
  caption: string
  sourceUrl: string
  web_path?: string
  source_name?: string
  rationale?: string
}

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
    hero_image?: HeroImage | null
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
  // Academic metadata — populated only when the backend emits the rich format
  // (`[N] Authors (YYYY). Title. Venue. DOI: 10.xxx/yyy`). Legacy entries
  // (YouTube, Wikipedia, blog) leave these undefined and fall back to the
  // existing one-line rendering.
  authors?: string
  year?: number
  venue?: string
  doi?: string
}

const GROUP_ORDER: RefGroup[] = ['Academic', 'Reputable', 'PDF', 'Video', 'Other']

const GROUP_LABEL: Record<RefGroup, string> = {
  Academic: 'Academic sources',
  Reputable: 'Reputable sources',
  PDF: 'PDFs & archives',
  Video: 'Video sources',
  Other: 'Other sources',
}

/** Split paper markdown at the LAST `## References` / `## Sources` heading.
 *
 * The pipeline always appends the canonical references list at the very end,
 * so the last matching heading is the right split point. Using the last (not
 * first) match defends against a writer LLM that emits its own References
 * section in the body — without this, the frontend would surface the LLM's
 * URL-less fake refs and hide the real bibliography. The backend now strips
 * such duplicate sections too, but this stays as a belt-and-braces safeguard
 * for already-published reports that still carry the bug.
 */
function splitBodyAndRefs(report: string): { body: string; refsText: string } {
  const re = /\n#{2,3}\s+(?:References|Sources)\s*\n/g
  let lastMatch: RegExpExecArray | null = null
  for (let m = re.exec(report); m !== null; m = re.exec(report)) {
    lastMatch = m
  }
  if (!lastMatch) {
    return { body: report, refsText: '' }
  }
  const body = report.slice(0, lastMatch.index)
  const refsText = report.slice(lastMatch.index + lastMatch[0].length)
  return { body, refsText }
}

// Rich (academic) ref pattern. Mirrors theo_citations.py `_RICH_REF_LINE_RE`.
// Shape: `[N] Authors (YYYY). Title. Venue. DOI: 10.xxx/yyy (accessed YYYY-MM-DD) [Academic]`
const RICH_REF_RE =
  /^\[(\d+)\]\s+(.+?)\s+\((\d{4})\)\.\s+(.+?)\.\s+(.+?)\.\s+DOI:\s+(\S+?)(?:\s+\(accessed\s+(\d{4}-\d{2}-\d{2})\))?(?:\s+\[(Academic|Reputable)\])?\s*$/

/**
 * Parse the references section into structured records and group them.
 *
 * Two formats are accepted in the same list:
 * - Rich (academic): `[N] Authors (YYYY). Title. Venue. DOI: 10.xxx/yyy (accessed YYYY-MM-DD) [Academic]`
 * - Legacy: `[N] Title — URL (accessed YYYY-MM-DD) [Tier]`
 *
 * The rich shape's `(YYYY).` anchor is specific enough that we can try it
 * first without confusing the legacy parser.
 */
function parseReferences(refsText: string): Reference[] {
  if (!refsText.trim()) return []

  const refs: Reference[] = []
  for (const rawLine of refsText.split('\n')) {
    const line = rawLine.trim()
    if (!line) continue

    // Try rich format first
    const richMatch = line.match(RICH_REF_RE)
    if (richMatch) {
      const [, numStr, authors, yearStr, rawTitle, venue, doi, accessed, tier] = richMatch
      const num = parseInt(numStr, 10)
      const cleanTitle = rawTitle.replace(/^\[PDF\]\s*/, '')
      let group: RefGroup
      if (tier === 'Academic') group = 'Academic'
      else if (tier === 'Reputable') group = 'Reputable'
      else group = 'Academic'  // DOI-bearing ref defaults to Academic group
      refs.push({
        num,
        title: cleanTitle,
        url: `https://doi.org/${doi}`,
        accessed: accessed || undefined,
        group,
        authors,
        year: parseInt(yearStr, 10),
        venue,
        doi,
      })
      continue
    }

    // Legacy `[N] Title — URL (accessed YYYY-MM-DD) [Tier]`
    const numMatch = line.match(/^\[(\d+)\]\s+(.+)$/)
    if (!numMatch) continue
    const num = parseInt(numMatch[1], 10)
    const rest = numMatch[2]

    const dashMatch = rest.match(/^(.+?)\s+[—–-]\s+(https?:\/\/\S+)(.*)$/)
    if (!dashMatch) continue
    const title = dashMatch[1].trim()
    const url = dashMatch[2].trim()
    const tail = dashMatch[3] || ''

    const accessedMatch = tail.match(/\(accessed\s+(\d{4}-\d{2}-\d{2})\)/)
    const accessed = accessedMatch ? accessedMatch[1] : undefined

    const tierMatch = tail.match(/\[(Academic|Reputable)\]/)
    const tierLabel = tierMatch ? tierMatch[1] : null

    let group: RefGroup
    if (tierLabel === 'Academic') group = 'Academic'
    else if (tierLabel === 'Reputable') group = 'Reputable'
    else if (/youtu\.?be/.test(url)) group = 'Video'
    else if (/^\[PDF\]/.test(title) || /\.pdf(?:$|\?)/.test(url)) group = 'PDF'
    else group = 'Other'

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
  const isFounder = useIsFounder()
  const [paper, setPaper] = useState<PaperData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [ttsStatus, setTtsStatus] = useState<TtsStatus | null>(null)
  const [isPlaying, setIsPlaying] = useState(false)
  const [audioProgress, setAudioProgress] = useState(0)
  const [lightboxIndex, setLightboxIndex] = useState<number | null>(null)
  const audioRef = useRef<HTMLAudioElement | null>(null)
  const progressRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const slug = useMemo(() => {
    // /research/{slug} is canonical; ?slug= is the legacy entry form.
    const route = anRoute()
    if (route?.type === 'research') return route.slug
    return new URLSearchParams(window.location.search).get('slug') || ''
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
        setMeta('og:description', `AI-generated research paper by ${data.published_by} on Ancient Nerds Research`)
        setMeta('og:url', window.location.href)
        const heroSrc = data.result?.hero_image?.src
        if (heroSrc) {
          const absolute = heroSrc.startsWith('http') ? heroSrc : `${window.location.origin}${heroSrc}`
          setMeta('og:image', absolute)
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
    img: ({ src, alt }: React.ImgHTMLAttributes<HTMLImageElement>) => {
      // Strip gallery:ID|verified:..| prefix from alt if a stray image slipped
      // past the gallery segmenter (legacy papers, malformed blocks).
      let cleanAlt = alt || ''
      const stripped = cleanAlt.match(/^gallery:[^|]+\|(?:verified:(?:yes|no)\|)?(.*)$/)
      if (stripped) cleanAlt = stripped[1]
      return (
        <img src={src || ''} alt={cleanAlt} style={{ maxHeight: 400, borderRadius: 4 }} />
      )
    },
  }), [])

  // Derived values from the loaded paper. The lightbox flat array contains
  // [hero?, ...body figures in document order]; figureStartIndex maps each
  // segment key to its first image's offset in that array so figures and
  // mosaic tiles can wire a direct onClick → setLightboxIndex.
  const { bodySegments, groupedRefs, totalRefs, lightboxImages, figureStartIndex, heroLightboxIndex } = useMemo(() => {
    const emptyRefs: Record<RefGroup, Reference[]> = {
      Academic: [], Reputable: [], PDF: [], Video: [], Other: [],
    }
    if (!paper?.result) {
      return {
        bodySegments: [],
        groupedRefs: emptyRefs,
        totalRefs: 0,
        lightboxImages: [] as LightboxImage[],
        figureStartIndex: new Map<string, number>(),
        heroLightboxIndex: null as number | null,
      }
    }
    // The page renders its own <h1> title; stored reports start with the
    // same title as a markdown heading (7 of 10 papers use '## Title',
    // 3 use '# Title') — strip it or the title appears twice. A genuine
    // section heading like '## Introduction' is never touched.
    const headingMatch = paper.result.report.match(/^\s*(#{1,3})\s+([^\n]+)\n+/)
    const normalize = (s: string) => s.toLowerCase().replace(/[^a-z0-9]+/g, '')
    const paperTitle = paper.result.title || paper.question || ''
    const reportSansTitle = headingMatch
      && (headingMatch[1] === '#' || normalize(headingMatch[2]) === normalize(paperTitle))
      ? paper.result.report.slice(headingMatch[0].length)
      : paper.result.report
    const { body, refsText } = splitBodyAndRefs(reportSansTitle)
    const refs = parseReferences(refsText)
    const knownNums = new Set(refs.map(r => r.num))
    const wired = wireCitationAnchors(body, knownNums)
    const segments = splitIntoImageSegments(wired)

    const images: LightboxImage[] = []
    const startIndex = new Map<string, number>()

    const hero = paper.result.hero_image
    let heroIdx: number | null = null
    if (hero?.src) {
      heroIdx = images.length
      images.push({
        src: hero.src,
        title: hero.title || '',
        sourceUrl: hero.sourceUrl || undefined,
        sourceType: inferSourceType(hero.sourceUrl),
      })
    }

    segments.forEach((seg, segIdx) => {
      if (seg.kind === 'figure') {
        startIndex.set(`f-${segIdx}`, images.length)
        images.push({
          src: seg.figure.src,
          title: seg.figure.title,
          sourceUrl: seg.figure.sourceUrl || undefined,
          sourceType: inferSourceType(seg.figure.sourceUrl),
        })
      } else if (seg.kind === 'mosaic') {
        startIndex.set(`m-${segIdx}`, images.length)
        for (const fig of seg.figures) {
          images.push({
            src: fig.src,
            title: fig.title,
            sourceUrl: fig.sourceUrl || undefined,
            sourceType: inferSourceType(fig.sourceUrl),
          })
        }
      }
    })

    const grouped: Record<RefGroup, Reference[]> = {
      Academic: [], Reputable: [], PDF: [], Video: [], Other: [],
    }
    for (const r of refs) grouped[r.group].push(r)
    for (const g of GROUP_ORDER) grouped[g].sort((a, b) => a.num - b.num)
    return {
      bodySegments: segments,
      groupedRefs: grouped,
      totalRefs: refs.length,
      lightboxImages: images,
      figureStartIndex: startIndex,
      heroLightboxIndex: heroIdx,
    }
  }, [paper])

  if (loading) {
    return (
      <div className="theo-page">
        <PageHeader currentPage="theo">
          <a href="/theo.html#research-library" className="page-header-title">Research</a>
        </PageHeader>
        <div style={{ textAlign: 'center', padding: '60px 20px', color: 'var(--text-dimmed)' }}>Loading...</div>
      </div>
    )
  }

  if (error || !paper?.result) {
    return (
      <div className="theo-page">
        <PageHeader currentPage="theo">
          <a href="/theo.html#research-library" className="page-header-title">Research</a>
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
        <a href="/theo.html#research-library" className="page-header-title">Research</a>
      </PageHeader>
      <AiNoticeBanner message="Research paper text is AI-generated; images are from cited sources. Always verify claims with original sources." />

        {paper.result.hero_image?.src && (
          <figure className="theo-paper-hero">
            <img
              src={paper.result.hero_image.src}
              alt={paper.result.hero_image.title || ''}
              className="theo-paper-hero-img"
              onClick={heroLightboxIndex !== null ? () => setLightboxIndex(heroLightboxIndex) : undefined}
              style={heroLightboxIndex !== null ? { cursor: 'zoom-in' } : undefined}
            />
            {paper.result.hero_image.caption && (
              <figcaption className="theo-paper-hero-caption">
                {paper.result.hero_image.sourceUrl ? (
                  <a href={paper.result.hero_image.sourceUrl} target="_blank" rel="noopener noreferrer">
                    <em>{paper.result.hero_image.caption}</em>
                  </a>
                ) : (
                  <em>{paper.result.hero_image.caption}</em>
                )}
              </figcaption>
            )}
          </figure>
        )}

        <div className="theo-paper-page">
        {/* Paper header */}
        <div className="theo-paper-header">
          <h1 className="theo-paper-title">{title}</h1>
          <div className="theo-paper-meta">
            <QualityBadge qualityScore={paper.result.quality_score} />
            <span style={{ color: 'var(--text-dimmed)', fontSize: 12 }}>{readingMinutes} min read</span>
            <span style={{ color: 'var(--text-muted)', fontSize: 12 }}>
              by {paper.published_by}{paper.published_by === 'Theo' ? ' · AI research agent' : ''}
            </span>
            {paper.published_at && (
              <span style={{ color: 'var(--text-dimmed)', fontSize: 12 }}>
                {new Date(paper.published_at).toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric' })}
              </span>
            )}
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

        {/* Paper body */}
        <TheoPaperBody
          segments={bodySegments}
          mdComponents={mdComponents}
          figureStartIndex={figureStartIndex}
          onImageClick={setLightboxIndex}
          className="theo-paper-body theo-md-body"
        />

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
                        {r.doi ? (
                          // Rich (academic) layout: Authors (Year). Title. Venue. DOI
                          <span className="theo-ref-academic">
                            {r.authors && <span className="theo-ref-authors">{r.authors}</span>}
                            {r.year != null && <span className="theo-ref-year"> ({r.year})</span>}
                            {'. '}
                            <a href={r.url} target="_blank" rel="noopener noreferrer" className="theo-ref-link">
                              <em>{r.title}</em>
                            </a>
                            {r.venue && <span className="theo-ref-venue">. {r.venue}</span>}
                            {'. '}
                            <a
                              href={`https://doi.org/${r.doi}`}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="theo-ref-doi"
                            >
                              DOI: {r.doi}
                            </a>
                            {r.accessed && (
                              <span className="theo-ref-accessed"> · accessed {r.accessed}</span>
                            )}
                          </span>
                        ) : (
                          <>
                            <a href={r.url} target="_blank" rel="noopener noreferrer" className="theo-ref-link">
                              {r.title}
                            </a>
                            {r.accessed && (
                              <span className="theo-ref-accessed"> · accessed {r.accessed}</span>
                            )}
                          </>
                        )}
                      </li>
                    ))}
                  </ol>
                </details>
              )
            })}
          </div>
        )}

        {/* Back to research library */}
        <div style={{ textAlign: 'center', padding: '32px 0' }}>
          <a href="/theo.html#research-library" style={{ color: 'var(--brand-primary)', fontSize: 13, textDecoration: 'none' }}>
            Browse all papers in the Research Library
          </a>
        </div>
      </div>
      {lightboxIndex !== null && lightboxImages.length > 0 && createPortal(
        <ImageLightbox
          images={lightboxImages}
          currentIndex={Math.min(lightboxIndex, lightboxImages.length - 1)}
          onClose={() => setLightboxIndex(null)}
          onNavigate={setLightboxIndex}
        />,
        document.body,
      )}
    </div>
  )
}
