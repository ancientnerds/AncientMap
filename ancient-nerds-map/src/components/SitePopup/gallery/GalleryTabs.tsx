import { useState, useEffect, useRef, useCallback } from 'react'
import type { GalleryTabsProps, GalleryTab } from '../types'

interface TabConfig {
  id: GalleryTab
  label: string
  icon: JSX.Element
  count: number
  isLoading?: boolean
}

export function GalleryTabs({
  activeTab,
  onTabChange,
  photoCount,
  videoCount,
  mapCount,
  modelCount,
  artifactCount,
  artworkCount,
  bookCount,
  paperCount,
  mythCount,
  webcamCount,
  isLoadingWebcams = false,
  isLoadingImages = false,
  isLoadingVideos = false,
  isLoadingMaps = false,
  isLoadingModels = false,
  isLoadingArtifacts = false,
  isLoadingBooks = false,
  isLoadingPapers = false,
}: GalleryTabsProps) {
  const scrollRef = useRef<HTMLDivElement>(null)
  const [canScrollLeft, setCanScrollLeft] = useState(false)
  const [canScrollRight, setCanScrollRight] = useState(false)

  const updateArrows = useCallback(() => {
    const el = scrollRef.current
    if (!el) return
    setCanScrollLeft(el.scrollLeft > 1)
    setCanScrollRight(el.scrollLeft + el.clientWidth < el.scrollWidth - 1)
  }, [])

  useEffect(() => {
    const el = scrollRef.current
    if (!el) return
    updateArrows()
    el.addEventListener('scroll', updateArrows)
    const ro = new ResizeObserver(updateArrows)
    ro.observe(el)
    return () => {
      el.removeEventListener('scroll', updateArrows)
      ro.disconnect()
    }
  }, [updateArrows])

  const scroll = (direction: 'left' | 'right') => {
    const el = scrollRef.current
    if (!el) return
    // Scroll by ~70% of visible width
    const amount = el.clientWidth * 0.7
    el.scrollBy({ left: direction === 'left' ? -amount : amount, behavior: 'smooth' })
  }

  const chevronLeft = (
    <svg width="10" height="10" viewBox="0 0 10 10" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="7 1.5 3 5 7 8.5" />
    </svg>
  )
  const chevronRight = (
    <svg width="10" height="10" viewBox="0 0 10 10" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="3 1.5 7 5 3 8.5" />
    </svg>
  )

  const tabs: TabConfig[] = [
    {
      id: 'photos',
      label: 'Photos',
      icon: (
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <rect x="3" y="3" width="18" height="18" rx="2" ry="2"></rect>
          <circle cx="8.5" cy="8.5" r="1.5"></circle>
          <polyline points="21 15 16 10 5 21"></polyline>
        </svg>
      ),
      count: photoCount,
      isLoading: isLoadingImages
    },
    {
      id: 'videos',
      label: 'Videos',
      icon: (
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <circle cx="12" cy="12" r="10"></circle>
          <polygon points="10 8 16 12 10 16 10 8"></polygon>
        </svg>
      ),
      count: videoCount,
      isLoading: isLoadingVideos
    },
    {
      id: '3dmodels',
      label: '3D',
      icon: (
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/>
          <polyline points="3.27 6.96 12 12.01 20.73 6.96"/>
          <line x1="12" y1="22.08" x2="12" y2="12"/>
        </svg>
      ),
      count: modelCount,
      isLoading: isLoadingModels
    },
    {
      id: 'maps',
      label: 'Maps',
      icon: (
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <rect x="3" y="3" width="18" height="18" rx="2" ry="2"></rect>
          <line x1="3" y1="9" x2="21" y2="9"></line>
          <line x1="9" y1="21" x2="9" y2="9"></line>
        </svg>
      ),
      count: mapCount,
      isLoading: isLoadingMaps
    },
    {
      id: 'artifacts',
      label: 'Artifacts',
      icon: (
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M12 2L2 7l10 5 10-5-10-5z"></path>
          <path d="M2 17l10 5 10-5"></path>
          <path d="M2 12l10 5 10-5"></path>
        </svg>
      ),
      count: artifactCount,
      isLoading: isLoadingArtifacts
    },
    {
      id: 'artworks',
      label: 'Artworks',
      icon: (
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <rect x="3" y="3" width="18" height="18" rx="2"></rect>
          <path d="M3 9h18"></path>
          <path d="M9 21V9"></path>
        </svg>
      ),
      count: artworkCount
    },
    {
      id: 'books',
      label: 'Books',
      icon: (
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"></path>
          <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"></path>
        </svg>
      ),
      count: bookCount,
      isLoading: isLoadingBooks
    },
    {
      id: 'papers',
      label: 'Papers',
      icon: (
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
          <polyline points="14 2 14 8 20 8"></polyline>
          <line x1="16" y1="13" x2="8" y2="13"></line>
          <line x1="16" y1="17" x2="8" y2="17"></line>
        </svg>
      ),
      count: paperCount,
      isLoading: isLoadingPapers
    },
    {
      id: 'myths',
      label: 'Myths',
      icon: (
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M12 3c.132 0 .263 0 .393 0a7.5 7.5 0 0 0 7.92 12.446a9 9 0 1 1 -8.313 -12.454z"></path>
          <path d="M17 4a2 2 0 0 0 2 2a2 2 0 0 0 -2 2a2 2 0 0 0 -2 -2a2 2 0 0 0 2 -2"></path>
        </svg>
      ),
      count: mythCount
    },
    {
      id: 'webcams',
      label: 'Live',
      icon: (
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z"></path>
          <circle cx="12" cy="13" r="4"></circle>
        </svg>
      ),
      count: webcamCount,
      isLoading: isLoadingWebcams
    }
  ]

  return (
    <div className="gallery-tabs">
      {canScrollLeft && (
        <button className="gallery-tabs-arrow left" onClick={() => scroll('left')} aria-label="Scroll tabs left">
          {chevronLeft}
        </button>
      )}
      <div className="gallery-tabs-scroll" ref={scrollRef}>
        {tabs.map(tab => (
          <button
            key={tab.id}
            className={`gallery-tab ${activeTab === tab.id ? 'active' : ''}`}
            onClick={() => onTabChange(tab.id)}
          >
            {tab.icon}
            {tab.label}
            <span className={`gallery-tab-count ${tab.isLoading ? 'loading' : ''}`}>
              {tab.isLoading ? '...' : tab.count > 0 ? tab.count : ''}
            </span>
          </button>
        ))}
      </div>
      {canScrollRight && (
        <button className="gallery-tabs-arrow right" onClick={() => scroll('right')} aria-label="Scroll tabs right">
          {chevronRight}
        </button>
      )}
    </div>
  )
}
