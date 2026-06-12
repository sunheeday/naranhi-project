'use client'

import { useEffect } from 'react'
import { useRouter } from 'next/navigation'
import type { Locale } from '@/lib/i18n'
import { requestNoticeTranslation, syncPendingNoticeTranslationBatch } from '@/lib/notice-translation-batch'

interface Props {
  noticeId: string
  locale: Locale
  hasLocaleTranslation: boolean
  /** 번역 잡이 최종 실패한 상태 — 자동 재요청을 멈추고 사용자의 재시도 버튼만 받는다. */
  translationFailed?: boolean
}

const REFRESH_INTERVAL_MS = 5000

export default function NoticeLocaleTranslationKickoff({
  noticeId,
  locale,
  hasLocaleTranslation,
  translationFailed = false,
}: Props) {
  const router = useRouter()

  useEffect(() => {
    if (locale === 'ko') return
    syncPendingNoticeTranslationBatch(locale, hasLocaleTranslation ? [] : [noticeId])
  }, [hasLocaleTranslation, locale, noticeId])

  useEffect(() => {
    if (locale === 'ko' || hasLocaleTranslation || translationFailed) return
    void requestNoticeTranslation(noticeId, locale)
  }, [hasLocaleTranslation, locale, noticeId, translationFailed])

  useEffect(() => {
    if (locale === 'ko' || hasLocaleTranslation) return

    const timer = window.setInterval(() => {
      router.refresh()
    }, REFRESH_INTERVAL_MS)

    return () => window.clearInterval(timer)
  }, [hasLocaleTranslation, locale, router])

  return null
}
