/**
 * LyraProfileModal - Draggable agent dossier window for Lyra Wiskerbyte.
 */

import { useState, useEffect, useCallback, useRef, useMemo } from 'react'
import { config } from '../config'

const WATCHED_CHANNELS = [
  { name: 'Ancient Architects', id: 'UCscI4NOggNSN-Si5QgErNCw' },
  { name: 'Bright Insight', id: 'UCsIlJ9eYylZQcyfMOPNUz9w' },
  { name: 'UnchartedX', id: 'UC2Stn8atEra7SMdPWyQoSLA' },
  { name: 'Matthew LaCroix', id: 'UC65XXzhHyH3BKZ72Q1eKF8Q' },
  { name: 'History for GRANITE', id: 'UCDWboBDVnIsGdYSK3KUO0hQ' },
  { name: 'Luke Caverns', id: 'UCFestibN7lYXvEj_BMEh29w' },
  { name: 'MegalithomaniaUK', id: 'UCqMVaZM-USi0G54pu5318dQ' },
  { name: 'Universe Inside You', id: 'UCOnnmKlDZltHAqJLz-XIpGA' },
  { name: 'Funny Olde World', id: 'UCN2Z_nuG5XtVnE998unA3PA' },
  { name: 'History with Kayleigh', id: 'UCMwDeEoupy8QQpKKc8pzU_Q' },
  { name: 'Curious Being', id: 'UCxq9PsBVarBK9BpG9SYQF7w' },
  { name: 'DeDunking', id: 'UCodgvia5IT5wiV0II9swBLw' },
  { name: 'Wandering Wolf', id: 'UCmhg8Hd2vOHwH3Pi3_9fYag' },
  { name: 'Dark5 Ancient Mysteries', id: 'UC8QWOIcinxsrvMGlWox7bXg' },
  { name: 'History, Myths & Legends', id: 'UCgMfHNvlc4Zvr8FJHopDnvA' },
  { name: 'Nikkiana Jones', id: 'UC9qJWqnmPhDLnZNllSQ8uQA' },
  { name: 'Inst. for Natural Philosophy', id: 'UC452QHC05BAbQZZlYDUaoAA' },
  { name: 'One-eyed giant', id: 'UCLclaVGVpaNIbdQaRs1wC5Q' },
]

const NFT_URL = 'https://opensea.io/item/ethereum/0xe2bddad5584a0c1929a793161829714ce21dac0d/1'

const MIN_W = 660
const MIN_H = 440
const DEFAULT_W = 740
const DEFAULT_H = 520

interface Props {
  onClose: () => void
}

export default function LyraProfileModal({ onClose }: Props) {
  const panelRef = useRef<HTMLDivElement>(null)
  const [stats, setStats] = useState<{ total_items: number; total_videos: number; total_channels: number; latest_item_date: string | null } | null>(null)
  const [discoveryStats, setDiscoveryStats] = useState<{ total_discoveries: number; total_sites_known: number; total_name_variants: number } | null>(null)
  const [lyraStatus, setLyraStatus] = useState<'online' | 'offline' | 'error'>('offline')
  const [pos, setPos] = useState({ x: 0, y: 0 })
  const [size, setSize] = useState({ w: DEFAULT_W, h: DEFAULT_H })
  const [ready, setReady] = useState(false)
  const [isDragging, setIsDragging] = useState(false)
  const [isResizing, setIsResizing] = useState(false)
  const [resizeDir, setResizeDir] = useState('')
  const dragStart = useRef({ mx: 0, my: 0, px: 0, py: 0 })
  const resizeStart = useRef({ mx: 0, my: 0, w: 0, h: 0, px: 0, py: 0 })

  useEffect(() => {
    const w = Math.min(DEFAULT_W, window.innerWidth - 40)
    const h = Math.min(DEFAULT_H, window.innerHeight - 40)
    setSize({ w, h })
    setPos({
      x: Math.round(Math.max(20, (window.innerWidth - w) / 2)),
      y: Math.round(Math.max(20, (window.innerHeight - h) / 2)),
    })
    setReady(true)
  }, [])

  useEffect(() => {
    fetch(`${config.api.baseUrl}/news/stats`)
      .then(r => r.ok ? r.json() : null)
      .then(d => { if (d) setStats(d) })
      .catch(() => {})
    fetch(`${config.api.baseUrl}/news/lyra-status`)
      .then(r => r.ok ? r.json() : null)
      .then(d => { if (d) setLyraStatus(d.status) })
      .catch(() => setLyraStatus('offline'))
    fetch(`${config.api.baseUrl}/contributions/lyra/stats`)
      .then(r => r.ok ? r.json() : null)
      .then(d => { if (d) setDiscoveryStats(d) })
      .catch(() => {})
  }, [])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  const onTitleMouseDown = useCallback((e: React.MouseEvent) => {
    e.preventDefault()
    setIsDragging(true)
    dragStart.current = { mx: e.clientX, my: e.clientY, px: pos.x, py: pos.y }
  }, [pos])

  const onResizeMouseDown = useCallback((e: React.MouseEvent, dir: string) => {
    e.preventDefault()
    e.stopPropagation()
    setIsResizing(true)
    setResizeDir(dir)
    resizeStart.current = { mx: e.clientX, my: e.clientY, w: size.w, h: size.h, px: pos.x, py: pos.y }
  }, [size, pos])

  useEffect(() => {
    if (!isDragging && !isResizing) return
    const onMove = (e: MouseEvent) => {
      if (isDragging) {
        const dx = e.clientX - dragStart.current.mx
        const dy = e.clientY - dragStart.current.my
        setPos({
          x: Math.max(0, Math.min(window.innerWidth - size.w, dragStart.current.px + dx)),
          y: Math.max(0, Math.min(window.innerHeight - size.h, dragStart.current.py + dy)),
        })
      }
      if (isResizing) {
        const dx = e.clientX - resizeStart.current.mx
        const dy = e.clientY - resizeStart.current.my
        let nw = resizeStart.current.w, nh = resizeStart.current.h
        let nx = resizeStart.current.px, ny = resizeStart.current.py
        if (resizeDir.includes('e')) nw = Math.max(MIN_W, resizeStart.current.w + dx)
        if (resizeDir.includes('w')) { const c = Math.min(dx, resizeStart.current.w - MIN_W); nw = resizeStart.current.w - c; nx = resizeStart.current.px + c }
        if (resizeDir.includes('s')) nh = Math.max(MIN_H, resizeStart.current.h + dy)
        if (resizeDir.includes('n')) { const c = Math.min(dy, resizeStart.current.h - MIN_H); nh = resizeStart.current.h - c; ny = resizeStart.current.py + c }
        nw = Math.min(nw, window.innerWidth - nx)
        nh = Math.min(nh, window.innerHeight - ny)
        setSize({ w: nw, h: nh })
        setPos({ x: Math.max(0, nx), y: Math.max(0, ny) })
      }
    }
    const onUp = () => { setIsDragging(false); setIsResizing(false); setResizeDir('') }
    window.addEventListener('mousemove', onMove)
    window.addEventListener('mouseup', onUp)
    return () => { window.removeEventListener('mousemove', onMove); window.removeEventListener('mouseup', onUp) }
  }, [isDragging, isResizing, resizeDir, size.w, size.h])

  const style = useMemo((): React.CSSProperties => ({
    position: 'fixed', left: pos.x, top: pos.y, width: size.w, height: size.h,
    zIndex: 1000, opacity: ready ? 1 : 0,
  }), [pos, size, ready])

  return (
    <div className={`lyra-modal${(isDragging || isResizing) ? ' lyra-modal-dragging' : ''}`} style={style} ref={panelRef}>
      {/* Resize handles */}
      <div className="resize-handle resize-n" onMouseDown={e => onResizeMouseDown(e, 'n')} />
      <div className="resize-handle resize-s" onMouseDown={e => onResizeMouseDown(e, 's')} />
      <div className="resize-handle resize-e" onMouseDown={e => onResizeMouseDown(e, 'e')} />
      <div className="resize-handle resize-w" onMouseDown={e => onResizeMouseDown(e, 'w')} />
      <div className="resize-handle resize-ne" onMouseDown={e => onResizeMouseDown(e, 'ne')} />
      <div className="resize-handle resize-nw" onMouseDown={e => onResizeMouseDown(e, 'nw')} />
      <div className="resize-handle resize-se" onMouseDown={e => onResizeMouseDown(e, 'se')} />
      <div className="resize-handle resize-sw" onMouseDown={e => onResizeMouseDown(e, 'sw')} />

      {/* Drag bar */}
      <div className="lyra-poster-dragbar" onMouseDown={onTitleMouseDown}>
        <div className="popup-window-controls" style={{ position: 'static' }}>
          <button className="popup-window-btn close-btn" onClick={onClose} title="Close">
            <svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.5">
              <line x1="2" y1="2" x2="10" y2="10" />
              <line x1="10" y1="2" x2="2" y2="10" />
            </svg>
          </button>
        </div>
      </div>

      {/* Three-column body */}
      <div className="lyra-poster-body">
        {/* LEFT: portrait + NFT link */}
        <div className="lyra-poster-left">
          <div className="lyra-poster-banner">AGENT DOSSIER</div>
          <div className="lyra-poster-portrait">
            <img src="/lyra.gif" alt="Lyra Wiskerbyte" />
          </div>
          <div className="lyra-poster-name">
            <span className="lyra-poster-name-first">LYRA</span>
            <span className="lyra-poster-name-last">WISKERBYTE</span>
          </div>
          <span className="lyra-poster-tag">Archaeological Agent</span>
          <a className="lyra-poster-nft" href={NFT_URL} target="_blank" rel="noopener noreferrer">
            View NFT #001
          </a>
          <div className="lyra-poster-status">
            <div className={`lyra-poster-status-online${lyraStatus !== 'online' ? ' lyra-poster-status-offline' : ''}`}>
              <span className="lyra-poster-status-dot" />
              {lyraStatus === 'online' ? 'ONLINE' : 'OFFLINE'}
            </div>
            <div className="lyra-poster-status-stats">
              <div className="lyra-poster-status-row">
                <span className="lyra-poster-status-val">{stats?.total_videos ?? 0}</span>
                <span className="lyra-poster-status-label">videos processed</span>
              </div>
              <div className="lyra-poster-status-row">
                <span className="lyra-poster-status-val">{stats?.total_items ?? 0}</span>
                <span className="lyra-poster-status-label">headlines extracted</span>
              </div>
              <div className="lyra-poster-status-row">
                <span className="lyra-poster-status-val">{stats?.total_channels ?? WATCHED_CHANNELS.length}</span>
                <span className="lyra-poster-status-label">channels watched</span>
              </div>
              <div className="lyra-poster-status-row">
                <span className="lyra-poster-status-val">{(discoveryStats?.total_sites_known ?? 0).toLocaleString()}</span>
                <span className="lyra-poster-status-label">sites known</span>
              </div>
              <div className="lyra-poster-status-row">
                <span className="lyra-poster-status-val">{(discoveryStats?.total_name_variants ?? 0).toLocaleString()}</span>
                <span className="lyra-poster-status-label">name variants</span>
              </div>
              <div className="lyra-poster-status-row lyra-poster-status-highlight">
                <span className="lyra-poster-status-val">{discoveryStats?.total_discoveries ?? 0}</span>
                <span className="lyra-poster-status-label">sites discovered</span>
              </div>
            </div>
            <a className="lyra-poster-discoveries-btn" href="/discoveries.html" target="_blank" rel="noopener noreferrer">
              Analyze Discoveries
            </a>
          </div>
        </div>

        {/* CENTER: lore + abilities + discord */}
        <div className="lyra-poster-center">
          <div className="lyra-poster-section">
            <div className="lyra-poster-section-title">Background</div>
            <p>
              One of 100 biopunk Ancient Nerds using pre-Flood tech to uncover lost
              knowledge. Lyra monitors archaeology channels, extracts transcripts,
              and distills them into headlines so no discovery goes unnoticed.
            </p>
          </div>
          <div className="lyra-poster-section">
            <div className="lyra-poster-section-title">Abilities</div>
            <div className="lyra-poster-abilities">
              <div className="lyra-poster-ability">
                <span className="lyra-poster-ability-name">Transcript Extraction</span>
                <span className="lyra-poster-ability-desc">Pulls and cleans full video transcripts in seconds</span>
              </div>
              <div className="lyra-poster-ability">
                <span className="lyra-poster-ability-name">AI Summarization</span>
                <span className="lyra-poster-ability-desc">Distills hour-long lectures into key headlines and facts</span>
              </div>
              <div className="lyra-poster-ability">
                <span className="lyra-poster-ability-name">Timestamp Linking</span>
                <span className="lyra-poster-ability-desc">Deep-links to the exact moment a discovery is discussed</span>
              </div>
              <div className="lyra-poster-ability">
                <span className="lyra-poster-ability-name">24/7 Surveillance</span>
                <span className="lyra-poster-ability-desc">Monitors {WATCHED_CHANNELS.length} channels around the clock via RSS</span>
              </div>
            </div>
          </div>
          <div className="lyra-poster-section">
            <div className="lyra-poster-section-title">Report Sightings</div>
            <p>Want a channel on the watch list? Have intel?</p>
            <a className="lyra-poster-discord" href="https://discord.gg/8bAjKKCue4" target="_blank" rel="noopener noreferrer">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
                <path d="M20.317 4.37a19.791 19.791 0 0 0-4.885-1.515.074.074 0 0 0-.079.037c-.21.375-.444.864-.608 1.25a18.27 18.27 0 0 0-5.487 0 12.64 12.64 0 0 0-.617-1.25.077.077 0 0 0-.079-.037A19.736 19.736 0 0 0 3.677 4.37a.07.07 0 0 0-.032.027C.533 9.046-.32 13.58.099 18.057a.082.082 0 0 0 .031.057 19.9 19.9 0 0 0 5.993 3.03.078.078 0 0 0 .084-.028c.36-.698.772-1.362 1.226-1.994a.076.076 0 0 0-.041-.106 13.107 13.107 0 0 1-1.872-.892.077.077 0 0 1-.008-.128c.12-.094.246-.194.372-.292a.074.074 0 0 1 .077-.01c3.928 1.793 8.18 1.793 12.062 0a.074.074 0 0 1 .078.01c.12.098.246.198.373.292a.077.077 0 0 1-.006.127 12.299 12.299 0 0 1-1.873.892.077.077 0 0 0-.041.107c.36.698.772 1.362 1.225 1.993a.076.076 0 0 0 .084.028 19.839 19.839 0 0 0 6.002-3.03.077.077 0 0 0 .032-.054c.5-5.177-.838-9.674-3.549-13.66a.061.061 0 0 0-.031-.03zM8.02 15.33c-1.183 0-2.157-1.085-2.157-2.419 0-1.333.956-2.419 2.157-2.419 1.21 0 2.176 1.096 2.157 2.42 0 1.333-.956 2.418-2.157 2.418zm7.975 0c-1.183 0-2.157-1.085-2.157-2.419 0-1.333.955-2.419 2.157-2.419 1.21 0 2.176 1.096 2.157 2.42 0 1.333-.946 2.418-2.157 2.418z"/>
              </svg>
              Join Discord
            </a>
          </div>
        </div>

        {/* RIGHT: channel list */}
        <div className="lyra-poster-right">
          <div className="lyra-poster-section-title">Surveilled Channels</div>
          <div className="lyra-poster-channel-list">
            {WATCHED_CHANNELS.map(ch => (
              <a key={ch.name} className="lyra-poster-channel" href={`https://www.youtube.com/channel/${ch.id}`} target="_blank" rel="noopener noreferrer">
                <svg width="10" height="10" viewBox="0 0 24 24" fill="currentColor" className="lyra-poster-yt-icon">
                  <path d="M23.498 6.186a3.016 3.016 0 0 0-2.122-2.136C19.505 3.545 12 3.545 12 3.545s-7.505 0-9.377.505A3.017 3.017 0 0 0 .502 6.186C0 8.07 0 12 0 12s0 3.93.502 5.814a3.016 3.016 0 0 0 2.122 2.136c1.871.505 9.376.505 9.376.505s7.505 0 9.377-.505a3.015 3.015 0 0 0 2.122-2.136C24 15.93 24 12 24 12s0-3.93-.502-5.814zM9.545 15.568V8.432L15.818 12l-6.273 3.568z"/>
                </svg>
                {ch.name}
              </a>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}
