'use client'

import { useEffect } from 'react'
import { useRouter } from 'next/navigation'
import type { Locale } from '@/lib/i18n'

interface Props {
  noticeId: string
  locale: Locale
}

const COOLDOWN_MS = 5 * 60 * 1000

export default function NoticeLocaleTranslationKickoff({ noticeId, locale }: Props) {
  const router = useRouter()

  useEffect(() => {
    if (locale === 'ko') return

    const key = `naranhi:notice-translate:${locale}:${noticeId}`
    const previousAttempt = Number(window.localStorage.getItem(key) ?? '0')
    if (Number.isFinite(previousAttempt) && Date.now() - previousAttempt < COOLDOWN_MS) {
      return
    }
    window.localStorage.setItem(key, String(Date.now()))

    const controller = new AbortController()
    fetch(`/api/notices/${encodeURIComponent(noticeId)}/process`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ target_language: locale }),
      cache: 'no-store',
      signal: controller.signal,
    })
      .then(() => router.refresh())
      .catch(() => {
        if (!controller.signal.aborted) {
          router.refresh()
        }
      })

    return () => controller.abort()
  }, [locale, noticeId, router])

  return null
}
