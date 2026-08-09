import './page-header.css'

interface AiNoticeBannerProps {
  message?: string
}

export default function AiNoticeBanner({
  message = 'Content is AI-generated from YouTube video content. Always verify with original sources.',
}: AiNoticeBannerProps) {
  // data-ai-generated mirrors AI_NOTICE_HTML in pipeline/article_html_renderer.py.
  // The server fragment carried the machine-readable marker, React did not — so
  // it disappeared the moment the page hydrated (Art. 50 EU AI Act, Phase B).
  return (
    <div className="ai-notice-banner" data-ai-generated="true">
      {message}
    </div>
  )
}
