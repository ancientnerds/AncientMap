/**
 * DownloadManager - Modal UI for managing offline data downloads
 * Uses service layer for all download operations (no inline logic)
 */

import { useState, useEffect, useCallback, useMemo, useRef } from 'react'
import { OfflineStorage, DownloadState, CompactSite } from '../services/OfflineStorage'
import { BasemapCache, BasemapType } from '../services/BasemapCache'
import { VectorLayerCache } from '../services/VectorLayerCache'
import { EmpireCache } from '../services/EmpireCache'
import { ImageCache } from '../services/ImageCache'
import { config } from '../config'
import './DownloadManager.css'

interface DownloadManagerProps {
  isOpen: boolean
  onClose: () => void
  sources: Array<{
    id: string
    name: string
    count: number
    color: string
  }>
  isOffline: boolean
  onToggleOffline: () => void
}

interface DownloadProgress {
  type: 'source' | 'basemap' | 'layer' | 'empire'
  id: string
  loaded: number
  total: number
  label: string
}

/**
 * Format bytes to human readable string
 * Supports B, KB, MB, GB, TB
 */
function formatBytes(bytes: number): string {
  if (bytes === 0) return '0 B'
  if (bytes < 0) return '0 B'

  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB', 'TB']
  const i = Math.min(Math.floor(Math.log(bytes) / Math.log(k)), sizes.length - 1)
  const value = bytes / Math.pow(k, i)

  // Show more precision for larger units
  if (i >= 3) { // GB or TB
    return value.toFixed(2) + ' ' + sizes[i]
  } else if (i >= 2) { // MB
    return value.toFixed(1) + ' ' + sizes[i]
  } else {
    return Math.round(value) + ' ' + sizes[i]
  }
}

export default function DownloadManager({ isOpen, onClose, sources, isOffline, onToggleOffline }: DownloadManagerProps) {
  // State
  const [downloadState, setDownloadState] = useState<DownloadState | null>(null)
  const [selectedSources, setSelectedSources] = useState<Set<string>>(new Set())
  const [selectedBasemaps, setSelectedBasemaps] = useState<Set<BasemapType>>(new Set())
  const [selectedLayers, setSelectedLayers] = useState<Set<string>>(new Set())
  const [selectedEmpires, setSelectedEmpires] = useState<Set<string>>(new Set())
  const [progress, setProgress] = useState<DownloadProgress | null>(null)
  const [downloadSpeed, setDownloadSpeed] = useState(0) // bytes per second
  const speedTrackingRef = useRef<{ lastTime: number; lastBytes: number }>({ lastTime: 0, lastBytes: 0 })
  const [isDownloading, setIsDownloading] = useState(false)
  const [storageUsed, setStorageUsed] = useState(0)
  const [activeTab, setActiveTab] = useState<'sources' | 'layers' | 'basemap' | 'empires'>('layers')
  const [showClearConfirm, setShowClearConfirm] = useState(false)

  // Image pre-download state
  const [downloadingImagesSourceId, setDownloadingImagesSourceId] = useState<string | null>(null)
  const [imageDownloadProgress, setImageDownloadProgress] = useState<{ loaded: number; total: number } | null>(null)

  // Get data from services
  const vectorLayers = useMemo(() => VectorLayerCache.getAvailableLayers(), [])
  const basemapItems = useMemo(() => BasemapCache.getBasemapItems(), [])
  const empiresByRegion = useMemo(() => EmpireCache.getEmpiresByRegion(), [])
  const allEmpires = useMemo(() => EmpireCache.getAvailableEmpires(), [])

  // Load current download state
  useEffect(() => {
    if (!isOpen) return

    const loadState = async () => {
      const state = await OfflineStorage.getDownloadState()
      setDownloadState(state)

      // Pre-select already cached items
      setSelectedSources(new Set(Object.keys(state.sources)))
      setSelectedBasemaps(new Set((state.basemapItems || []) as BasemapType[]))
      setSelectedLayers(new Set(state.layers || []))
      setSelectedEmpires(new Set(state.empires))

      // Get storage estimate
      const estimate = await OfflineStorage.getStorageEstimate()
      setStorageUsed(estimate.used)
    }

    loadState()
  }, [isOpen])

  // Toggle handlers - don't allow unchecking cached items
  const toggleSource = useCallback((id: string) => {
    // Don't allow unchecking cached items
    if (downloadState?.sources[id]?.cached) return
    setSelectedSources(prev => {
      const next = new Set(prev)
      next.has(id) ? next.delete(id) : next.add(id)
      return next
    })
  }, [downloadState])

  const toggleBasemap = useCallback((id: BasemapType) => {
    // Don't allow unchecking cached items
    if (downloadState?.basemapItems?.includes(id)) return
    setSelectedBasemaps(prev => {
      const next = new Set(prev)
      next.has(id) ? next.delete(id) : next.add(id)
      return next
    })
  }, [downloadState])

  const toggleLayer = useCallback((id: string) => {
    // Don't allow unchecking cached items
    if (downloadState?.layers?.includes(id)) return
    setSelectedLayers(prev => {
      const next = new Set(prev)
      next.has(id) ? next.delete(id) : next.add(id)
      return next
    })
  }, [downloadState])

  const toggleEmpire = useCallback((id: string) => {
    // Don't allow unchecking cached items
    if (downloadState?.empires.includes(id)) return
    setSelectedEmpires(prev => {
      const next = new Set(prev)
      next.has(id) ? next.delete(id) : next.add(id)
      return next
    })
  }, [downloadState])

  // Select all handlers
  const selectAllSources = useCallback(() => {
    const allIds = sources.map(s => s.id)
    setSelectedSources(prev =>
      allIds.every(id => prev.has(id)) ? new Set() : new Set(allIds)
    )
  }, [sources])

  const selectAllBasemaps = useCallback(() => {
    const allIds: BasemapType[] = ['satellite', 'labels']
    setSelectedBasemaps(prev =>
      allIds.every(id => prev.has(id)) ? new Set() : new Set(allIds)
    )
  }, [])

  const selectAllLayers = useCallback(() => {
    const allIds = vectorLayers.map(l => l.id)
    setSelectedLayers(prev =>
      allIds.every(id => prev.has(id)) ? new Set() : new Set(allIds)
    )
  }, [vectorLayers])

  const selectAllEmpires = useCallback(() => {
    const allIds = allEmpires.map(e => e.id)
    setSelectedEmpires(prev =>
      allIds.every(id => prev.has(id)) ? new Set() : new Set(allIds)
    )
  }, [allEmpires])

  // Calculate estimated download size
  const estimatedSize = useMemo(() => {
    let size = 0

    // Sources (rough estimate: 50 bytes per site)
    for (const sourceId of selectedSources) {
      if (downloadState?.sources[sourceId]?.cached) continue
      const source = sources.find(s => s.id === sourceId)
      if (source) size += source.count * 50
    }

    // Basemaps
    const newBasemaps = [...selectedBasemaps].filter(
      id => !downloadState?.basemapItems?.includes(id)
    )
    size += BasemapCache.estimateSize(newBasemaps)

    // Vector layers
    const newLayers = [...selectedLayers].filter(
      id => !downloadState?.layers?.includes(id)
    )
    size += VectorLayerCache.estimateSize(newLayers)

    // Empires
    for (const empireId of selectedEmpires) {
      if (downloadState?.empires.includes(empireId)) continue
      size += EmpireCache.estimateEmpireSize(empireId)
    }

    return size
  }, [selectedSources, selectedBasemaps, selectedLayers, selectedEmpires, downloadState, sources])

  // Update progress with speed calculation
  const updateProgressWithSpeed = useCallback((loaded: number, total: number) => {
    const now = Date.now()
    const { lastTime, lastBytes } = speedTrackingRef.current

    if (lastTime > 0 && now - lastTime > 100) { // Update speed every 100ms minimum
      const timeDelta = (now - lastTime) / 1000 // seconds
      const bytesDelta = loaded - lastBytes
      if (timeDelta > 0 && bytesDelta > 0) {
        setDownloadSpeed(bytesDelta / timeDelta)
      }
    }

    speedTrackingRef.current = { lastTime: now, lastBytes: loaded }
    setProgress(prev => prev ? { ...prev, loaded, total } : null)
  }, [])

  // Reset speed tracking when starting a new download item
  const resetSpeedTracking = useCallback(() => {
    speedTrackingRef.current = { lastTime: Date.now(), lastBytes: 0 }
    setDownloadSpeed(0)
  }, [])

  // Download handlers using services
  const downloadSources = async () => {
    const toDownload = [...selectedSources].filter(
      id => !downloadState?.sources[id]?.cached
    )

    for (const sourceId of toDownload) {
      const source = sources.find(s => s.id === sourceId)
      if (!source) continue

      setProgress({
        type: 'source',
        id: sourceId,
        loaded: 0,
        total: source.count,
        label: source.name
      })

      try {
        const response = await fetch(
          `${config.api.baseUrl}/sites/all?source=${sourceId}&limit=1000000`
        )
        if (!response.ok) throw new Error('Failed to fetch')

        const data = await response.json()
        const sites: CompactSite[] = data.sites || []

        await OfflineStorage.saveSites(sourceId, sites)
        setProgress(prev => prev ? { ...prev, loaded: sites.length } : null)
      } catch (error) {
        console.error(`Failed to download source ${sourceId}:`, error)
      }
    }
  }

  const downloadBasemaps = async () => {
    const toDownload = [...selectedBasemaps].filter(
      id => !downloadState?.basemapItems?.includes(id)
    )

    for (const itemId of toDownload) {
      const info = BasemapCache.getBasemapItemInfo(itemId)
      setProgress({
        type: 'basemap',
        id: itemId,
        loaded: 0,
        total: info.totalSize,
        label: info.name
      })
      resetSpeedTracking()

      try {
        await BasemapCache.downloadBasemapItem(itemId, (loaded, total) => {
          updateProgressWithSpeed(loaded, total)
        })
      } catch (error) {
        console.error(`Failed to download basemap ${itemId}:`, error)
      }
    }
  }

  const downloadLayers = async () => {
    const toDownload = [...selectedLayers].filter(
      id => !downloadState?.layers?.includes(id)
    )

    for (const layerId of toDownload) {
      const layer = VectorLayerCache.getLayerInfo(layerId)
      if (!layer) continue

      setProgress({
        type: 'layer',
        id: layerId,
        loaded: 0,
        total: layer.estimatedSize,
        label: layer.name
      })
      resetSpeedTracking()

      try {
        await VectorLayerCache.downloadLayer(layerId, (loaded, total) => {
          updateProgressWithSpeed(loaded, total)
        })
      } catch (error) {
        console.error(`Failed to download layer ${layerId}:`, error)
      }
    }
  }

  const downloadEmpires = async () => {
    const toDownload = [...selectedEmpires].filter(
      id => !downloadState?.empires.includes(id)
    )

    for (const empireId of toDownload) {
      const empire = EmpireCache.getEmpireInfo(empireId)
      if (!empire) continue

      setProgress({
        type: 'empire',
        id: empireId,
        loaded: 0,
        total: empire.estimatedSize,
        label: empire.name
      })
      resetSpeedTracking()

      try {
        await EmpireCache.downloadEmpire(empireId, (loaded, total) => {
          updateProgressWithSpeed(loaded, total)
        })
      } catch (error) {
        console.error(`Failed to download empire ${empireId}:`, error)
      }
    }
  }

  const handleDownload = async () => {
    setIsDownloading(true)

    try {
      await downloadSources()
      await downloadLayers()
      await downloadBasemaps()
      await downloadEmpires()

      // Refresh state
      const state = await OfflineStorage.getDownloadState()
      setDownloadState(state)

      const estimate = await OfflineStorage.getStorageEstimate()
      setStorageUsed(estimate.used)
    } catch (error) {
      console.error('Download error:', error)
    } finally {
      setIsDownloading(false)
      setProgress(null)
    }
  }

  const handleClearAll = async () => {
    setShowClearConfirm(false)

    await OfflineStorage.clearAllSites()
    await BasemapCache.clearAll()
    await VectorLayerCache.clearAllLayers()
    await EmpireCache.clearAllEmpires()

    setSelectedSources(new Set())
    setSelectedBasemaps(new Set())
    setSelectedLayers(new Set())
    setSelectedEmpires(new Set())

    const state = await OfflineStorage.getDownloadState()
    setDownloadState(state)

    const estimate = await OfflineStorage.getStorageEstimate()
    setStorageUsed(estimate.used)
  }

  // Download images for a cached source
  const downloadImagesForSource = async (sourceId: string) => {
    if (downloadingImagesSourceId) return // Already downloading

    setDownloadingImagesSourceId(sourceId)
    setImageDownloadProgress({ loaded: 0, total: 0 })

    try {
      // Get all image URLs for this source
      const imageUrls = await OfflineStorage.getImageUrlsForSource(sourceId)
      if (imageUrls.length === 0) {
        console.log(`[DownloadManager] No images found for source ${sourceId}`)
        return
      }

      setImageDownloadProgress({ loaded: 0, total: imageUrls.length })

      // Bulk cache images with progress
      const cached = await ImageCache.bulkCache(imageUrls, (loaded, total) => {
        setImageDownloadProgress({ loaded, total })
      })

      console.log(`[DownloadManager] Cached ${cached}/${imageUrls.length} images for ${sourceId}`)
    } catch (error) {
      console.error(`[DownloadManager] Failed to download images for ${sourceId}:`, error)
    } finally {
      setDownloadingImagesSourceId(null)
      setImageDownloadProgress(null)
    }
  }

  if (!isOpen) return null

  // Render helpers
  const renderCheckbox = (isSelected: boolean) => (
    <span className={`dm-checkbox ${isSelected ? 'checked' : ''}`}>
      {isSelected && (
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3">
          <polyline points="20 6 9 17 4 12"/>
        </svg>
      )}
    </span>
  )

  return (
    <div className="download-manager-overlay" onClick={onClose}>
      <div className="download-manager-modal" onClick={e => e.stopPropagation()}>
        {/* Header */}
        <div className="dm-header">
          <div className="dm-header-content">
            <h2>Offline Data Manager</h2>
            <p className="dm-explainer">Download site data, basemaps, and historical empires for offline field use.</p>
          </div>
          <button className="dm-close-btn" onClick={onClose}>
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M18 6L6 18M6 6l12 12"/>
            </svg>
          </button>
        </div>

        {/* Offline Mode Toggle */}
        <div className="dm-mode-toggle">
          <div className="dm-mode-status">
            <span className={`dm-mode-led ${isOffline ? 'offline' : 'online'}`} />
            <span className="dm-mode-label">
              {isOffline ? 'Offline Mode Active' : 'Online Mode Active'}
            </span>
          </div>
          <button
            className={`dm-mode-btn ${isOffline ? 'go-online' : 'go-offline'}`}
            onClick={onToggleOffline}
          >
            {isOffline ? 'Go Online' : 'Go Offline'}
          </button>
        </div>

        {/* Storage info */}
        <div className="dm-storage-info">
          {(() => {
            // Calculate total as: used + selected (what will be stored after download)
            const totalAfterDownload = storageUsed + estimatedSize
            const barMax = Math.max(totalAfterDownload, storageUsed, 1) // Avoid division by zero
            const usedPercent = (storageUsed / barMax) * 100
            const selectedPercent = (estimatedSize / barMax) * 100

            return (
              <>
                <div className="storage-bar">
                  <div
                    className="storage-used"
                    style={{ width: `${usedPercent}%` }}
                  />
                  {estimatedSize > 0 && (
                    <div
                      className="storage-preview"
                      style={{
                        left: `${usedPercent}%`,
                        width: `${selectedPercent}%`
                      }}
                    />
                  )}
                </div>
                <div className="storage-text">
                  <span>{formatBytes(storageUsed)} used</span>
                  {estimatedSize > 0 && (
                    <span className="storage-preview-text"> + {formatBytes(estimatedSize)} selected</span>
                  )}
                  <span className="storage-total"> = {formatBytes(totalAfterDownload)} total</span>
                </div>
              </>
            )
          })()}
        </div>

        {/* Tabs */}
        <div className="dm-tabs">
          {(['layers', 'basemap', 'empires', 'sources'] as const).map(tab => (
            <button
              key={tab}
              className={`dm-tab ${activeTab === tab ? 'active' : ''}`}
              onClick={() => setActiveTab(tab)}
            >
              {tab === 'sources' ? `Sources (${sources.length})` :
               tab === 'layers' ? `Layers (${vectorLayers.length})` :
               tab === 'empires' ? `Empires (${allEmpires.length})` :
               'Basemap'}
            </button>
          ))}
        </div>

        {/* Content */}
        <div className="dm-content">
          {/* Sources Tab */}
          {activeTab === 'sources' && (
            <div className="dm-section">
              <div className="dm-section-header">
                <span className="dm-section-title">Archaeological Site Sources</span>
                <button className="dm-select-all-btn" onClick={selectAllSources} disabled={isDownloading}>
                  {sources.every(s => selectedSources.has(s.id)) ? 'Deselect All' : 'Select All'}
                </button>
              </div>
              <div className="dm-list">
                {sources.map(source => (
                  <div
                    key={source.id}
                    className={`dm-item ${selectedSources.has(source.id) ? 'selected' : ''} ${isDownloading ? 'disabled' : ''}`}
                    onClick={() => !isDownloading && toggleSource(source.id)}
                  >
                    {renderCheckbox(selectedSources.has(source.id))}
                    <span className="item-color" style={{ backgroundColor: source.color }} />
                    <span className="item-name">{source.name}</span>
                    {downloadState?.sources[source.id]?.cached && <span className="cached-badge">Cached</span>}
                    {/* Download Images button for cached sources */}
                    {downloadState?.sources[source.id]?.cached && (
                      <button
                        className="dm-download-images-btn"
                        onClick={(e) => {
                          e.stopPropagation()
                          downloadImagesForSource(source.id)
                        }}
                        disabled={!!downloadingImagesSourceId}
                      >
                        {downloadingImagesSourceId === source.id && imageDownloadProgress
                          ? `${imageDownloadProgress.loaded}/${imageDownloadProgress.total}`
                          : 'Images'
                        }
                      </button>
                    )}
                    <span className="item-meta">
                      {source.count.toLocaleString()} sites (~{formatBytes(source.count * 50)})
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Layers Tab */}
          {activeTab === 'layers' && (
            <div className="dm-section">
              <div className="dm-section-header">
                <span className="dm-section-title">Vector Layers</span>
                <button className="dm-select-all-btn" onClick={selectAllLayers} disabled={isDownloading}>
                  {vectorLayers.every(l => selectedLayers.has(l.id)) ? 'Deselect All' : 'Select All'}
                </button>
              </div>
              <p className="dm-section-note">Includes coastlines, borders, rivers, lakes, and paleoshorelines at multiple LODs.</p>
              <div className="dm-list">
                {vectorLayers.map(layer => (
                  <div
                    key={layer.id}
                    className={`dm-item ${selectedLayers.has(layer.id) ? 'selected' : ''} ${isDownloading ? 'disabled' : ''}`}
                    onClick={() => !isDownloading && toggleLayer(layer.id)}
                  >
                    {renderCheckbox(selectedLayers.has(layer.id))}
                    <span className="item-color" style={{ backgroundColor: layer.color }} />
                    <span className="item-name">{layer.name}</span>
                    {downloadState?.layers?.includes(layer.id) && <span className="cached-badge">Cached</span>}
                    <span className="item-meta">
                      {layer.fileCount} files ({formatBytes(layer.estimatedSize)})
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Basemap Tab */}
          {activeTab === 'basemap' && (
            <div className="dm-section">
              <div className="dm-section-header">
                <span className="dm-section-title">Basemap Data</span>
                <button className="dm-select-all-btn" onClick={selectAllBasemaps} disabled={isDownloading}>
                  {(['satellite', 'labels'] as BasemapType[]).every(id => selectedBasemaps.has(id)) ? 'Deselect All' : 'Select All'}
                </button>
              </div>
              <p className="dm-section-note">Download satellite imagery and geographic labels for offline use.</p>
              <div className="dm-list">
                {basemapItems.map(item => (
                  <div
                    key={item.id}
                    className={`dm-item ${selectedBasemaps.has(item.id) ? 'selected' : ''} ${isDownloading ? 'disabled' : ''}`}
                    onClick={() => !isDownloading && toggleBasemap(item.id)}
                  >
                    {renderCheckbox(selectedBasemaps.has(item.id))}
                    <span className="item-name">{item.name}</span>
                    {downloadState?.basemapItems?.includes(item.id) && <span className="cached-badge">Cached</span>}
                    <span className="item-meta">
                      {item.files.length} file{item.files.length > 1 ? 's' : ''} ({formatBytes(item.totalSize)})
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Empires Tab */}
          {activeTab === 'empires' && (
            <div className="dm-section">
              <div className="dm-section-header">
                <span className="dm-section-title">Historical Empire Boundaries</span>
                <button className="dm-select-all-btn" onClick={selectAllEmpires} disabled={isDownloading}>
                  {allEmpires.every(e => selectedEmpires.has(e.id)) ? 'Deselect All' : 'Select All'}
                </button>
              </div>
              <p className="dm-section-note">Total: {formatBytes(EmpireCache.getTotalSize())} for all {allEmpires.length} empires</p>
              <div className="dm-list">
                {Object.entries(empiresByRegion).map(([region, empires]) => (
                  <div key={region} className="dm-empire-region">
                    <div className="dm-region-title">{region}</div>
                    {empires.map(empire => (
                      <div
                        key={empire.id}
                        className={`dm-item ${selectedEmpires.has(empire.id) ? 'selected' : ''} ${isDownloading ? 'disabled' : ''}`}
                        onClick={() => !isDownloading && toggleEmpire(empire.id)}
                      >
                        {renderCheckbox(selectedEmpires.has(empire.id))}
                        <span className="item-color" style={{ backgroundColor: empire.color }} />
                        <span className="item-name">{empire.name}</span>
                        {downloadState?.empires.includes(empire.id) && <span className="cached-badge">Cached</span>}
                        <span className="item-meta">
                          {empire.fileCount} files ({formatBytes(empire.estimatedSize)})
                        </span>
                      </div>
                    ))}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Progress bar */}
        {progress && (
          <div className="dm-progress">
            <div className="progress-label">Downloading: {progress.label}</div>
            <div className="progress-bar">
              <div
                className="progress-fill"
                style={{ width: `${(progress.loaded / progress.total) * 100}%` }}
              />
            </div>
            <div className="progress-text">
              {progress.type === 'source'
                ? `${progress.loaded.toLocaleString()} / ${progress.total.toLocaleString()} sites`
                : `${formatBytes(progress.loaded)} / ${formatBytes(progress.total)}${downloadSpeed > 0 ? ` - ${formatBytes(downloadSpeed)}/s` : ''}`}
            </div>
          </div>
        )}

        {/* Footer */}
        <div className="dm-footer">
          <div className="dm-status">
            {isDownloading && progress ? (
              <span className="download-status">
                {progress.type === 'source'
                  ? `${progress.loaded.toLocaleString()} / ${progress.total.toLocaleString()} sites`
                  : `${formatBytes(progress.loaded)} / ${formatBytes(progress.total)}${downloadSpeed > 0 ? ` - ${formatBytes(downloadSpeed)}/s` : ''}`}
              </span>
            ) : estimatedSize > 0 ? (
              <span className="ready-status">{formatBytes(estimatedSize)} ready to download</span>
            ) : (
              <span className="empty-status">Select items to download</span>
            )}
          </div>
          <div className="dm-actions">
            <button className="dm-clear-btn" onClick={() => setShowClearConfirm(true)} disabled={isDownloading}>
              Clear All
            </button>
            <button
              className="dm-download-btn"
              onClick={handleDownload}
              disabled={isDownloading || estimatedSize === 0}
            >
              {isDownloading ? 'Downloading...' : 'Download Offline Data'}
            </button>
          </div>
        </div>

        {/* Clear Confirmation Dialog */}
        {showClearConfirm && (
          <div className="dm-confirm-overlay" onClick={() => setShowClearConfirm(false)}>
            <div className="dm-confirm-dialog" onClick={e => e.stopPropagation()}>
              <div className="dm-confirm-icon">
                <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                  <path d="M12 9v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/>
                </svg>
              </div>
              <h3>Clear All Offline Data?</h3>
              <p>This will remove all cached sites, basemaps, layers, and empire data. You will need to re-download for offline use.</p>
              <div className="dm-confirm-actions">
                <button className="dm-confirm-cancel" onClick={() => setShowClearConfirm(false)}>
                  Cancel
                </button>
                <button className="dm-confirm-delete" onClick={handleClearAll}>
                  Clear All Data
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
