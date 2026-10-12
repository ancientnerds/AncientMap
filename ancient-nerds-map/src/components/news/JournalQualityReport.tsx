/**
 * JournalQualityReport — das Qualitäts-Audit-Panel unter einem Journal.
 *
 * Bis 2026-10-12 stand dieses Panel nur im Standalone-Leser von
 * /articles.html; die indexierte Seite /articles/{slug} zeigte es nicht.
 * Mit der Leser-Zusammenführung rendert nur noch dieses Panel die
 * Bewertung — vorher gab es zwei Orte, an denen sie stehen konnte.
 *
 * Die Felder kommen unverändert aus news_articles.quality_report; die
 * Anzeige ist die des alten Panels (Klassen aus styles/index.css).
 * "partial" bedeutet dabei nicht "schlecht": der Cluster-Judge beanstandet
 * fast immer irgendeinen Claim (siehe Memory: journal-quality-report-semantics).
 */

import type { JournalQualityReport } from '../../types/anRoute'

/** D-Nummer auf den Namen der Prüfregel, wie im Panel seit 2026-08. */
const DIMENSION_NAMES: Record<string, string> = {
  D1: 'Proper noun',
  D2: 'Citation',
  D3: 'Academic style',
  D4: 'Screenshot',
  D5: 'Source quality',
  D6: 'Spelling',
  D7: 'Citation format',
  D8: 'Week date',
  D9: 'Summary',
  D10: 'Balance',
}

export default function JournalQualityReportPanel({
  report,
}: {
  report: JournalQualityReport
}) {
  const clusters = Object.entries(report.research_clusters ?? {})
  const fixes = report.fixes_applied ?? []

  return (
    <details className="articles-quality-report">
      <summary className="articles-quality-summary">
        Quality Audit — {report.assessment_score}/10
        {report.assessment_score === 10 && ' ✓'}
      </summary>
      <div className="articles-quality-body">
        <p className="articles-quality-meta">
          Converged in {report.assessment_iterations} iteration
          {report.assessment_iterations !== 1 ? 's' : ''} · {report.total_sources} sources
          {report.total_elapsed_seconds > 0
            ? ` · ${Math.round(report.total_elapsed_seconds / 60)} min generation time`
            : ' · retroactive assessment'}
        </p>

        <div className="articles-quality-dimensions">
          <h4>Quality Dimensions</h4>
          {Object.entries(report.assessment_dimensions ?? {}).map(([dim, passed]) => (
            <span key={dim} className={`articles-quality-dim ${passed ? 'pass' : 'fail'}`}>
              {passed ? '✓' : '✗'} {dim.replace(/_/g, ' ').replace(/^D\d+\s*/, '')}
            </span>
          ))}
        </div>

        {clusters.length > 0 && (
          <div className="articles-quality-clusters">
            <h4>Research Clusters</h4>
            {clusters.map(([name, data]) => (
              <div key={name} className="articles-quality-cluster">
                <span className={`articles-quality-score ${data.score >= 72 ? 'pass' : 'fail'}`}>
                  {data.score}
                </span>
                <span className="articles-quality-cluster-name">{name}</span>
                <span className="articles-quality-cluster-meta">
                  {data.sources} sources · {Math.round(data.elapsed)}s
                </span>
              </div>
            ))}
          </div>
        )}

        {fixes.length > 0 && (
          <div className="articles-quality-fixes">
            <h4>Fixes Applied</h4>
            {fixes.map((fix, i) => {
              const dim = String(fix.dimension)
              const label = DIMENSION_NAMES[dim] || dim
              return (
                <span key={i} className="articles-quality-fix">
                  {label}:{' '}
                  {fix.find
                    ? `${String(fix.find).slice(0, 40)} → ${String(fix.replace).slice(0, 40)}`
                    : 'corrected'}
                </span>
              )
            })}
          </div>
        )}
      </div>
    </details>
  )
}