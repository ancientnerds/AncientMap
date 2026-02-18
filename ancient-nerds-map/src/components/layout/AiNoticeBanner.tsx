import './page-header.css'

interface AiNoticeBannerProps {
  message?: string
}

export default function AiNoticeBanner({
  message = 'Content is AI-generated from YouTube video content. Always verify with original sources.',
}: AiNoticeBannerProps) {
  return <div className="ai-notice-banner">{message}</div>
}
