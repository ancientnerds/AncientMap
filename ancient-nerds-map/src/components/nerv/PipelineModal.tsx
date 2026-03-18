import { memo, useEffect, useState } from 'react'
import { createPortal } from 'react-dom'
import PipelineHexGraph from './PipelineHexGraph'
import './PipelineModal.css'

type Pipeline = 'news' | 'radar' | 'article'

const TABS: { key: Pipeline; label: string }[] = [
  { key: 'news', label: 'News' },
  { key: 'radar', label: 'Radar' },
  { key: 'article', label: 'Article' },
]

const PAGE_TO_PIPELINE: Record<string, Pipeline> = {
  news: 'news',
  radar: 'radar',
  articles: 'article',
}

interface PipelineModalProps {
  isOpen: boolean
  onClose: () => void
  defaultTab?: string
}

function PipelineModal({ isOpen, onClose, defaultTab }: PipelineModalProps) {
  const [activeTab, setActiveTab] = useState<Pipeline>(
    (defaultTab && PAGE_TO_PIPELINE[defaultTab]) || 'news'
  )

  useEffect(() => {
    if (!isOpen) return
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    document.body.style.overflow = 'hidden'
    return () => {
      window.removeEventListener('keydown', onKey)
      document.body.style.overflow = ''
    }
  }, [isOpen, onClose])

  if (!isOpen) return null

  return createPortal(
    <div className="pipeline-modal-overlay" onClick={onClose}>
      <div className="pipeline-modal" onClick={e => e.stopPropagation()}>
        <button className="pipeline-modal-close" onClick={onClose} title="Close">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <line x1="18" y1="6" x2="6" y2="18" />
            <line x1="6" y1="6" x2="18" y2="18" />
          </svg>
        </button>

        <div className="pipeline-modal-tabs">
          {TABS.map(t => (
            <button
              key={t.key}
              className={`pipeline-modal-tab${activeTab === t.key ? ' active' : ''}`}
              onClick={() => setActiveTab(t.key)}
            >
              {t.label}
            </button>
          ))}
        </div>

        <div className="pipeline-modal-body">
          <PipelineHexGraph pipeline={activeTab} pollInterval={30000} />
        </div>
      </div>
    </div>,
    document.body,
  )
}

export default memo(PipelineModal)
