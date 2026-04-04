/**
 * ResearchPaperPage — Dedicated public page for a single research paper.
 * URL: /research.html?slug=paper-slug-here
 * SEO-friendly, shareable, renders full paper with attribution.
 */

import { useState, useEffect, useMemo, useCallback } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import AiNoticeBanner from '../components/layout/AiNoticeBanner'
import PageHeader from '../components/layout/PageHeader'
import QualityBadge, { type QualityScore } from '../components/theo/QualityBadge'
import '../styles/theo.css'

const EFFORT_LABELS: Record<string, string> = {
  brief: 'Research Brief', note: 'Research Note', article: 'Journal Article',
  review: 'Literature Review', thesis: 'Thesis Chapter',
}

interface PaperData {
  id: string
  question: string
  effort: string
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

export default function ResearchPaperPage() {
  const [paper, setPaper] = useState<PaperData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

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
        setMeta('og:description', `${EFFORT_LABELS[data.effort] || data.effort} by ${data.published_by} on Ancient Nerds Research`)
        setMeta('og:url', window.location.href)
        if (data.id) {
          setMeta('og:image', `${window.location.origin}/data/research-images/${data.id}/cover.png`)
        }
      })
      .catch(() => setError('Paper not found'))
      .finally(() => setLoading(false))
  }, [slug])

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

  const mdComponents = useMemo(() => ({
    a: ({ href, children, ...props }: React.AnchorHTMLAttributes<HTMLAnchorElement>) => {
      if (href?.startsWith('site:')) {
        const siteId = href.slice(5)
        return <a {...props} href={`/site.html?id=${siteId}`} target="_blank" rel="noopener noreferrer">{children}</a>
      }
      return <a {...props} href={href} target="_blank" rel="noopener noreferrer">{children}</a>
    },
  }), [])

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

      <div className="theo-paper-page">
        {/* Paper header */}
        <div className="theo-paper-header">
          <h1 className="theo-paper-title">{title}</h1>
          <div className="theo-paper-meta">
            <span className="theo-badge theo-badge-effort">{EFFORT_LABELS[paper.effort] || paper.effort}</span>
            <QualityBadge qualityScore={paper.result.quality_score} effort={paper.effort} />
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
          </div>
        </div>

        {/* Paper body */}
        <div className="theo-paper-body theo-md-body">
          <ReactMarkdown remarkPlugins={[remarkGfm]} components={mdComponents}>
            {paper.result.report}
          </ReactMarkdown>
        </div>

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
