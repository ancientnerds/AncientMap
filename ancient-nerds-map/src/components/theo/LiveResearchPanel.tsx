import { useCurrentResearch } from '../../hooks/useCurrentResearch'
import './LiveResearchPanel.css'

function formatElapsed(seconds: number | null): string {
  if (seconds === null) return ''
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  return h > 0 ? `${h}h ${m}m` : `${m}m`
}

/**
 * Public live view of the permanent researcher — visible without login.
 * Renders nothing until the public /research/current endpoint responds.
 */
export default function LiveResearchPanel() {
  const current = useCurrentResearch()
  if (!current) return null
  if (!current.running && current.queued_batch === 0) return null

  return (
    <div className="live-research-panel">
      {current.running ? (
        <>
          <div className="lrp-status">
            <span className="lrp-dot" />
            <span className="lrp-label">Theo is researching</span>
            <span className="lrp-elapsed">{formatElapsed(current.running.elapsed_s)}</span>
          </div>
          <div className="lrp-question">{current.running.question}</div>
          <div className="lrp-meta">
            {current.running.sites_found.toLocaleString()} sources ·{' '}
            {current.running.llm_calls.toLocaleString()} analysis steps ·{' '}
            {current.queued_batch} topics queued
          </div>
        </>
      ) : (
        <div className="lrp-status">
          <span className="lrp-dot lrp-dot--idle" />
          <span className="lrp-label">
            Permanent researcher idle — {current.queued_batch} topics queued
          </span>
          {current.last_published && (
            <a className="lrp-last" href={`/research.html?slug=${current.last_published.slug}`}>
              Latest: {current.last_published.title}
            </a>
          )}
        </div>
      )}
      <a className="lrp-graph-link" href="/knowledge.html">
        Explore the Knowledge Graph →
      </a>
    </div>
  )
}
