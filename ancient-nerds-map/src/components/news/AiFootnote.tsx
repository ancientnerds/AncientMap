/**
 * AiFootnote — the EU-AI-Act-Art.-50 disclosure as a quiet footnote under an
 * article, instead of a banner above it.
 *
 * Lived inside StoryArticle until 2026-09-10, when the homepage journal and
 * paper windows needed the same marking: those windows run the pages, but the
 * pages carry their disclosure as a page-level <AiNoticeBanner> the extracted
 * components never see — so the excerpts arrived unmarked. One definition, so
 * the three windows cannot say it differently (or stop saying it).
 */

import '../../styles/story-page.css'

export default function AiFootnote() {
  return (
    <p className="story-ai-notice" data-ai-generated="true">
      AI-generated text · images from the original sources · always verify with the sources.
    </p>
  )
}
