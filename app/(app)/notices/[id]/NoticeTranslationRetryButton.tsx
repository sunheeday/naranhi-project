'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import type { Locale } from '@/lib/i18n'
import { requestNoticeTranslation } from '@/lib/notice-translation-batch'

interface Props {
  noticeId: string
  locale: Locale
  label: string
  busyLabel: string
}

export default function NoticeTranslationRetryButton({ noticeId, locale, label, busyLabel }: Props) {
  const router = useRouter()
  const [isRetrying, setIsRetrying] = useState(false)

  async function handleRetry() {
    if (isRetrying) return
    setIsRetrying(true)
    try {
      await requestNoticeTranslation(noticeId, locale)
      router.refresh()
    } finally {
      setIsRetrying(false)
    }
  }

  return (
    <button
      type="button"
      onClick={handleRetry}
      disabled={isRetrying}
      className="shrink-0 px-3 h-9 rounded-btn bg-primary text-white text-xs font-semibold shadow-btn-primary disabled:opacity-40"
    >
      {isRetrying ? busyLabel : label}
    </button>
  )
}
