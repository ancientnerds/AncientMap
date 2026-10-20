/**
 * PaperSites — the curated sites a paper treats, as links to their pages (owner
 * decision 2026-10-20). The SEO evaluation of 2026-10-19 (A2) found papers to be
 * link dead ends: 0 links to a site on 6 of 6 sampled papers. The links are reviewed
 * rows (migration 0031), not a name match; the site pages link back under "Research
 * on this site". Same look as the corrections log (paper-extras.css).
 */

import '../../styles/paper-extras.css'

export default function PaperSites({ sites }: { sites: { name: string; path: string }[] }) {
  return (
    <section className="theo-paper-sites" aria-labelledby="paper-sites-title">
      <h2 id="paper-sites-title">Sites in this paper</h2>
      <ul>
        {sites.map(s => (
          <li key={s.path}>
            <a href={s.path}>{s.name}</a>
          </li>
        ))}
      </ul>
    </section>
  )
}
