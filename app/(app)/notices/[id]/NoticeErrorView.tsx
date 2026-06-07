'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'

interface Props {
  noticeId: string
  title: string
  description: string
  errorMessage: string | null
  retryLabel: string
  retryingLabel: string
  retryFailedLabel: string
}

export default function NoticeErrorView({
  noticeId,
  title,
  description,
  errorMessage,
  retryLabel,
  retryingLabel,
  retryFailedLabel,
}: Props) {
  const router = useRouter()
  const [isRetrying, setIsRetrying] = useState(false)
  const [retryError, setRetryError] = useState<string | null>(null)

  async function handleRetry() {
    if (isRetrying) return
    setRetryError(null)
    setIsRetrying(true)
    try {
      const res = await fetch(`/api/notices/${noticeId}/process`, {
        method: 'POST',
      })
      if (!res.ok) {
        throw new Error(retryFailedLabel)
      }
      router.refresh()
    } catch (e) {
      setRetryError(e instanceof Error ? e.message : retryFailedLabel)
    } finally {
      setIsRetrying(false)
    }
  }

  return (
    <div className="flex-1 flex flex-col items-center justify-center px-6 py-10 gap-4">
      <span className="text-5xl" aria-hidden="true">⚠️</span>
      <h1 className="text-lg font-bold text-text-primary text-center">{title}</h1>
      <p className="text-sm text-text-secondary text-center">{description}</p>
      {errorMessage && (
        <p className="text-xs text-text-disabled text-center bg-bg rounded-btn px-3 py-2 max-w-xs break-words">
          {errorMessage}
        </p>
      )}
      <button
        type="button"
        onClick={handleRetry}
        disabled={isRetrying}
        className="mt-4 px-6 h-12 rounded-btn bg-primary text-white text-base font-semibold shadow-btn-primary disabled:opacity-40"
      >
        {isRetrying ? retryingLabel : retryLabel}
      </button>
      {retryError && (
        <p role="alert" className="text-sm text-red-500">{retryError}</p>
      )}
    </div>
  )
}
