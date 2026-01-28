/**
 * useScreenshot - Hook for handling globe screenshot functionality
 *
 * Consolidates:
 * - Screenshot capture with html2canvas
 * - Screenshot mode CSS class toggling
 * - Download link creation
 */

import { useCallback } from 'react'
import html2canvas from 'html2canvas'

interface UseScreenshotReturn {
  handleScreenshot: () => Promise<void>
}

export function useScreenshot(): UseScreenshotReturn {
  // Screenshot function - captures entire viewport with current UI state (respects Hide HUD mode)
  const handleScreenshot = useCallback(async () => {
    // Add screenshot mode (makes tooltips solid/opaque)
    document.body.classList.add('screenshot-mode')

    // Wait for CSS changes to apply
    await new Promise(resolve => setTimeout(resolve, 100))

    try {
      // Capture the entire document body (includes globe, FilterPanel, all UI elements)
      const canvas = await html2canvas(document.body, {
        backgroundColor: '#000000',
        scale: window.devicePixelRatio || 1,
        useCORS: true,
        logging: false,
        width: window.innerWidth,
        height: window.innerHeight,
      })

      // Create download link
      const link = document.createElement('a')
      link.download = `ancient-nerds-${Date.now()}.png`
      link.href = canvas.toDataURL('image/png')
      link.click()
    } finally {
      // Restore classes
      document.body.classList.remove('screenshot-mode')
    }
  }, [])

  return { handleScreenshot }
}
