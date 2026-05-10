import React, { useState, useEffect } from 'react'
import { FileText, AlertCircle } from 'lucide-react'
import { storageAPI } from '@/api/services'
import { Spinner } from './index'

interface DocumentViewerProps {
  storageKey: string
  alt?: string
  className?: string
  onError?: (error: Error) => void
}

export function DocumentViewer({ storageKey, alt = 'Document', className = '', onError }: DocumentViewerProps) {
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [imageUrl, setImageUrl] = useState<string | null>(null)

  useEffect(() => {
    if (!storageKey) {
      setError('No storage key provided')
      setLoading(false)
      return
    }

    let isMounted = true

    async function fetchUrl() {
      try {
        setLoading(true)
        const response = await storageAPI.getPresignedGetUrl(storageKey)
        if (response.data?.data?.url && isMounted) {
          setImageUrl(response.data.data.url)
          setError(null)
        } else {
          setError('Failed to get document URL')
          onError?.(new Error('Failed to get document URL'))
        }
      } catch (err) {
        if (isMounted) {
          setError('Document unavailable')
          onError?.(err instanceof Error ? err : new Error(String(err)))
        }
      } finally {
        if (isMounted) {
          setLoading(false)
        }
      }
    }

    fetchUrl()

    return () => {
      isMounted = false
    }
  }, [storageKey, onError])

  if (loading) {
    return (
      <div className={`flex items-center justify-center bg-surface-50 rounded-lg min-h-[120px] ${className}`}>
        <Spinner size="md" />
      </div>
    )
  }

  if (error || !imageUrl) {
    return (
      <div className={`flex flex-col items-center justify-center bg-surface-50 rounded-lg min-h-[120px] text-surface-400 ${className}`}>
        <FileText className="h-8 w-8 mb-2 opacity-50" />
        <span className="text-xs">Document unavailable</span>
      </div>
    )
  }

  return (
    <div className={`relative overflow-hidden rounded-lg bg-surface-50 ${className}`}>
      <img
        src={imageUrl}
        alt={alt}
        className="w-full h-auto max-h-[200px] object-contain"
      />
    </div>
  )
}