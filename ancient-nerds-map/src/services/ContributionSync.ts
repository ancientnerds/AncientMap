/**
 * ContributionSync - Handles syncing queued offline contributions
 * Gets fresh Turnstile tokens and submits to API when back online
 */

import { OfflineStorage } from './OfflineStorage'
import { config } from '../config'

export interface SyncResult {
  total: number
  success: number
  failed: number
  results: Array<{
    id: string
    status: 'success' | 'error' | 'retry'
    error?: string
  }>
}

class ContributionSyncClass {
  private syncInProgress = false
  private listeners: Set<(result: SyncResult) => void> = new Set()

  /**
   * Add listener for sync completion
   */
  onSyncComplete(callback: (result: SyncResult) => void): () => void {
    this.listeners.add(callback)
    return () => this.listeners.delete(callback)
  }

  /**
   * Check if sync is currently in progress
   */
  isSyncing(): boolean {
    return this.syncInProgress
  }

  /**
   * Sync all pending contributions
   */
  async syncPendingContributions(): Promise<SyncResult> {
    if (this.syncInProgress) {
      return { total: 0, success: 0, failed: 0, results: [] }
    }

    if (!navigator.onLine) {
      return { total: 0, success: 0, failed: 0, results: [] }
    }

    this.syncInProgress = true

    try {
      const pending = await OfflineStorage.getPendingContributions()
      if (pending.length === 0) {
        return { total: 0, success: 0, failed: 0, results: [] }
      }

      const results: SyncResult['results'] = []
      let success = 0
      let failed = 0

      for (const contribution of pending) {
        // Skip if too many retries
        if (contribution.retryCount >= 3) {
          results.push({
            id: contribution.id,
            status: 'error',
            error: 'Max retries exceeded'
          })
          failed++
          continue
        }

        try {
          // Update status to syncing
          await OfflineStorage.updateContributionStatus(contribution.id, 'syncing')

          // Get fresh Turnstile token
          const token = await this.getFreshTurnstileToken()

          // Submit to API
          const response = await fetch(`${config.api.baseUrl}/contributions/`, {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json'
            },
            body: JSON.stringify({
              name: contribution.formData.name,
              country: contribution.formData.country || null,
              lat: contribution.formData.lat,
              lon: contribution.formData.lon,
              site_type: contribution.formData.siteType || null,
              description: contribution.formData.description || null,
              source_url: contribution.formData.sourceUrl || null,
              turnstile_token: token
            })
          })

          if (response.ok) {
            await OfflineStorage.removeContribution(contribution.id)
            results.push({ id: contribution.id, status: 'success' })
            success++
          } else {
            const errorText = await response.text()
            await OfflineStorage.updateContributionStatus(contribution.id, 'error', errorText)
            await OfflineStorage.incrementRetryCount(contribution.id)
            results.push({
              id: contribution.id,
              status: 'retry',
              error: errorText
            })
            failed++
          }
        } catch (error) {
          const errorMsg = error instanceof Error ? error.message : 'Unknown error'
          await OfflineStorage.updateContributionStatus(contribution.id, 'error', errorMsg)
          await OfflineStorage.incrementRetryCount(contribution.id)
          results.push({
            id: contribution.id,
            status: 'retry',
            error: errorMsg
          })
          failed++
        }
      }

      const result: SyncResult = {
        total: pending.length,
        success,
        failed,
        results
      }

      // Notify listeners
      this.listeners.forEach(cb => cb(result))

      return result
    } finally {
      this.syncInProgress = false
    }
  }

  /**
   * Get a fresh Turnstile token for submission
   */
  private async getFreshTurnstileToken(): Promise<string> {
    return new Promise((resolve, reject) => {
      // Check if Turnstile is available
      if (!window.turnstile) {
        reject(new Error('Turnstile not loaded'))
        return
      }

      // Create invisible container
      const container = document.createElement('div')
      container.style.position = 'fixed'
      container.style.top = '-9999px'
      container.style.left = '-9999px'
      document.body.appendChild(container)

      let widgetId: string | null = null
      let timeoutId: ReturnType<typeof setTimeout> | null = null

      const cleanup = () => {
        if (timeoutId) clearTimeout(timeoutId)
        if (widgetId && window.turnstile) {
          try {
            window.turnstile.remove(widgetId)
          } catch {
            // Ignore removal errors
          }
        }
        if (container.parentNode) {
          container.parentNode.removeChild(container)
        }
      }

      // Set timeout for token generation
      timeoutId = setTimeout(() => {
        cleanup()
        reject(new Error('Turnstile token timeout'))
      }, 30000)

      try {
        widgetId = window.turnstile.render(container, {
          sitekey: config.turnstile?.siteKey || '0x4AAAAAAA-placeholder',
          callback: (token: string) => {
            cleanup()
            resolve(token)
          },
          'error-callback': () => {
            cleanup()
            reject(new Error('Turnstile verification failed'))
          }
        })
      } catch (error) {
        cleanup()
        reject(error)
      }
    })
  }

  /**
   * Manually trigger sync (called when coming back online)
   */
  async triggerSync(): Promise<void> {
    if (!navigator.onLine) return

    const pendingCount = await OfflineStorage.getPendingContributionsCount()
    if (pendingCount > 0) {
      await this.syncPendingContributions()
    }
  }
}

export const ContributionSync = new ContributionSyncClass()
