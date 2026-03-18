import { type ReactNode, useState, lazy, Suspense } from 'react'
import { BRAND_NAME, BRAND_ASSETS } from '../../constants/brand'
import { usePipelineStatus } from '../nerv/usePipelineStatus'
import HamburgerNav from './HamburgerNav'
import './page-header.css'

const PipelineModal = lazy(() => import('../nerv/PipelineModal'))

interface PageHeaderProps {
  children: ReactNode
  rightSection?: ReactNode
  speechBubble?: string
  onAvatarClick?: () => void
  currentPage?: string
  hideLyra?: boolean
}

function LiveIndicator({ onClick }: { onClick?: () => void }) {
  const { data } = usePipelineStatus('news')
  const online = data?.status === 'online'

  return (
    <div
      className={`page-header-live${online ? '' : ' offline'}`}
      title="Click to view pipeline status"
      onClick={onClick}
      role="button"
      tabIndex={0}
      onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') onClick?.() }}
    >
      <span className="page-header-live-dot" />
      <span className="page-header-live-text">{online ? 'LIVE' : 'OFFLINE'}</span>
    </div>
  )
}

export default function PageHeader({ children, rightSection, speechBubble, onAvatarClick, currentPage, hideLyra }: PageHeaderProps) {
  const [showPipeline, setShowPipeline] = useState(false)

  return (
    <>
      <header className="page-header">
        <a href="/globe.html" className="page-header-brand">
          <img src={BRAND_ASSETS.logo} alt="" className="page-header-logo" />
          <span className="page-header-brand-text">{BRAND_NAME}</span>
        </a>
        <HamburgerNav currentPage={currentPage} />
        <div className="page-header-divider" />
        {children}
        {!hideLyra && (
          <img
            src="/lyra.png"
            alt="Lyra Whiskerbyte"
            className="page-header-avatar lyra-avatar-clickable"
            onClick={onAvatarClick}
          />
        )}
        {speechBubble && <div className="page-header-bubble">{speechBubble}</div>}
        <div className="page-header-live-wrap">
          <LiveIndicator onClick={() => setShowPipeline(true)} />
        </div>
        {rightSection && <div className="page-header-right">{rightSection}</div>}
      </header>
      {showPipeline && (
        <Suspense fallback={null}>
          <PipelineModal isOpen={showPipeline} onClose={() => setShowPipeline(false)} defaultTab={currentPage} />
        </Suspense>
      )}
    </>
  )
}
