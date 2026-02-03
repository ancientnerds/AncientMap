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
  mapCount,
  modelCount,
  artifactCount,
  artworkCount,
  bookCount,
  paperCount,
  mythCount,
  isLoadingImages = false,
  isLoadingMaps = false,
  isLoadingModels = false,
  isLoadingArtifacts = false,
  isLoadingBooks = false,
  isLoadingPapers = false,
  isGalleryExpanded,
  onExpandToggle
}: GalleryTabsProps) {
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
    }
  ]

  return (
    <div className="gallery-tabs">
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

      {/* Expand button only shown when not expanded */}
      {!isGalleryExpanded && (
        <>
          <div className="gallery-tabs-spacer" />
          <button
            className="gallery-expand-btn"
            onClick={onExpandToggle}
            title="Expand"
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <polyline points="15 3 21 3 21 9"></polyline>
              <polyline points="9 21 3 21 3 15"></polyline>
              <line x1="21" y1="3" x2="14" y2="10"></line>
              <line x1="3" y1="21" x2="10" y2="14"></line>
            </svg>
          </button>
        </>
      )}
    </div>
  )
}
