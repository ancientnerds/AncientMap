import { type ReactNode, useState, useEffect } from 'react'
import { config } from '../../config'
import './page-header.css'

interface PageHeaderProps {
  children: ReactNode
  rightSection?: ReactNode
  speechBubble?: string
  onAvatarClick?: () => void
}

function LiveIndicator() {
  const [online, setOnline] = useState(false)

  useEffect(() => {
    const check = () => {
      fetch(`${config.api.baseUrl}/news/lyra-status`)
        .then(r => r.ok ? r.json() : null)
        .then(d => setOnline(d ? d.status === 'online' : false))
        .catch(() => setOnline(false))
    }
    check()
    const id = setInterval(check, 60_000)
    return () => clearInterval(id)
  }, [])

  return (
    <div
      className={`page-header-live${online ? '' : ' offline'}`}
      title={online
        ? 'Lyra is online — monitoring YouTube archaeology channels and extracting discoveries'
        : 'Lyra is offline — pipeline not currently running'}
    >
      <span className="page-header-live-dot" />
      <span className="page-header-live-text">{online ? 'LIVE' : 'OFFLINE'}</span>
    </div>
  )
}

export default function PageHeader({ children, rightSection, speechBubble, onAvatarClick }: PageHeaderProps) {
  return (
    <header className="page-header">
      <a href="/globe.html" className="page-header-brand">
        <img src="/an-logo.svg" alt="" className="page-header-logo" />
        <span className="page-header-brand-text">ANCIENT NERDS</span>
      </a>
      <div className="page-header-divider" />
      {children}
      <img
        src="/lyra.png"
        alt="Lyra Wiskerbyte"
        className="page-header-avatar lyra-avatar-clickable"
        onClick={onAvatarClick}
      />
      {speechBubble && <div className="page-header-bubble">{speechBubble}</div>}
      <div className="page-header-live-wrap">
        <LiveIndicator />
      </div>
      {rightSection && <div className="page-header-right">{rightSection}</div>}
    </header>
  )
}
