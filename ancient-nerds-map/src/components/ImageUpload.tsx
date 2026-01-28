import { useState, useRef } from 'react'
import { config } from '../config'

interface ImageUploadProps {
  siteId: string
  siteName: string
  onUploadComplete?: () => void
}

const ALLOWED_TYPES = ['image/jpeg', 'image/png', 'image/gif', 'image/webp']
const MAX_SIZE = 10 * 1024 * 1024 // 10MB

export default function ImageUpload({ siteId, siteName, onUploadComplete }: ImageUploadProps) {
  const [isUploading, setIsUploading] = useState(false)
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const handleClick = () => {
    fileInputRef.current?.click()
  }

  const handleFileSelect = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return

    // Reset input so same file can be selected again
    e.target.value = ''

    // Validate file type
    if (!ALLOWED_TYPES.includes(file.type)) {
      setMessage({ type: 'error', text: 'Invalid format. Use JPG, PNG, GIF, or WebP.' })
      setTimeout(() => setMessage(null), 3000)
      return
    }

    // Validate file size
    if (file.size > MAX_SIZE) {
      setMessage({ type: 'error', text: 'File too large. Max 10MB.' })
      setTimeout(() => setMessage(null), 3000)
      return
    }

    // Upload
    setIsUploading(true)
    setMessage(null)

    try {
      const formData = new FormData()
      formData.append('file', file)
      formData.append('site_id', siteId)
      formData.append('site_name', siteName)
      formData.append('uploader', 'web_user')

      const response = await fetch(config.api.uploadUrl, {
        method: 'POST',
        body: formData,
      })

      if (response.ok) {
        setMessage({ type: 'success', text: 'Uploaded! Pending review.' })
        onUploadComplete?.()
      } else {
        const data = await response.json().catch(() => ({}))
        setMessage({ type: 'error', text: data.detail || 'Upload failed' })
      }
    } catch (error) {
      // Server might not be running
      setMessage({ type: 'error', text: 'Upload server not available' })
    } finally {
      setIsUploading(false)
      setTimeout(() => setMessage(null), 4000)
    }
  }

  return (
    <div className="image-upload">
      <input
        ref={fileInputRef}
        type="file"
        accept="image/jpeg,image/png,image/gif,image/webp"
        onChange={handleFileSelect}
        style={{ display: 'none' }}
      />

      <button
        className="upload-btn"
        onClick={handleClick}
        disabled={isUploading}
        title="Upload your own photo of this site"
      >
        {isUploading ? (
          <span className="upload-spinner" />
        ) : (
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
            <polyline points="17 8 12 3 7 8" />
            <line x1="12" y1="3" x2="12" y2="15" />
          </svg>
        )}
        {isUploading ? 'Uploading...' : 'Upload Photo'}
      </button>

      {message && (
        <div className={`upload-message ${message.type}`}>
          {message.text}
        </div>
      )}
    </div>
  )
}
