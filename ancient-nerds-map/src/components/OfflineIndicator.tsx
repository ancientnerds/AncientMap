/**
 * OfflineIndicator - Status badge showing online/offline state
 * Displays pending contributions count and opens DownloadManager
 */

import { useState, useEffect, memo } from 'react'
import { OfflineStorage } from '../services/OfflineStorage'
import { ContributionSync } from '../services/ContributionSync'
import './OfflineIndicator.css'

interface OfflineIndicatorProps {
  onManageClick: () => void
}

function OfflineIndicator({ onManageClick }: OfflineIndicatorProps) {
  const [isOnline, setIsOnline] = useState(navigator.onLine)
  const [pendingCount, setPendingCount] = useState(0)
  const [isSyncing, setIsSyncing] = useState(false)
  const [hasOfflineData, setHasOfflineData] = useState(false)

  // Listen for online/offline events
  useEffect(() => {
    const handleOnline = () => {
      setIsOnline(true)
      // Trigger sync when back online
      ContributionSync.triggerSync()
    }

    const handleOffline = () => {
      setIsOnline(false)
    }

    window.addEventListener('online', handleOnline)
    window.addEventListener('offline', handleOffline)

    return () => {
      window.removeEventListener('online', handleOnline)
      window.removeEventListener('offline', handleOffline)
    }
  }, [])

  // Load pending count and offline state
  useEffect(() => {
    const loadState = async () => {
      const count = await OfflineStorage.getPendingContributionsCount()
      setPendingCount(count)

      const hasData = await OfflineStorage.isOfflineEnabled()
      setHasOfflineData(hasData)
    }

    loadState()

    // Re-check periodically
    const interval = setInterval(loadState, 5000)
    return () => clearInterval(interval)
  }, [])

  // Listen for sync events
  useEffect(() => {
    const unsubscribe = ContributionSync.onSyncComplete(async () => {
      setIsSyncing(false)
      // Refresh pending count after sync
      const count = await OfflineStorage.getPendingContributionsCount()
      setPendingCount(count)
    })

    return unsubscribe
  }, [])

  // Update syncing state
  useEffect(() => {
    const checkSyncing = () => {
      setIsSyncing(ContributionSync.isSyncing())
    }

    checkSyncing()
    const interval = setInterval(checkSyncing, 1000)
    return () => clearInterval(interval)
  }, [])

  return (
    <div className="offline-indicator">
      {/* Status dot */}
      <div
        className={`status-dot ${isOnline ? 'online' : 'offline'} ${isSyncing ? 'syncing' : ''}`}
        title={isOnline ? 'Online' : 'Offline'}
      />

      {/* Pending count badge */}
      {pendingCount > 0 && (
        <span className="pending-badge" title={`${pendingCount} contribution${pendingCount !== 1 ? 's' : ''} pending sync`}>
          {pendingCount}
        </span>
      )}

      {/* Offline data indicator */}
      {hasOfflineData && (
        <span className="offline-data-badge" title="Offline data available">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor">
            <path d="M19 9h-4V3H9v6H5l7 7 7-7zM5 18v2h14v-2H5z"/>
          </svg>
        </span>
      )}

      {/* Manage button */}
      <button
        className="manage-offline-btn"
        onClick={onManageClick}
        title="Manage offline data"
      >
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <circle cx="12" cy="12" r="10"/>
          <path d="M2 12h20M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/>
        </svg>
      </button>
    </div>
  )
}

// Memoize to prevent unnecessary re-renders
export default memo(OfflineIndicator)
