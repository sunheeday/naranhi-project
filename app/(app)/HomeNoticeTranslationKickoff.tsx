'use client'

import { useEffect, useRef } from 'react'
import { useRouter } from 'next/navigation'
import type { Locale } from '@/lib/i18n'

interface Props {
  locale: Locale
  noticeIds: string[]
}

const COOLDOWN_MS = 5 * 60 * 1000

export default function HomeNoticeTranslationKickoff({ locale, noticeIds }: Props) {
  const router = useRouter()
  const startedRef = useRef<string | null>(null)

  useEffect(() => {
    if (locale === 'ko' || noticeIds.length === 0) return

    let cancelled = false

    async function run() {
      const nextNoticeId = noticeIds.find(noticeId => {
        const key = `naranhi:notice-translate:${locale}:${noticeId}`
        const previousAttempt = Number(window.localStorage.getItem(key) ?? '0')
        return !Number.isFinite(previousAttempt) || Date.now() - previousAttempt >= COOLDOWN_MS
      })
      if (!nextNoticeId || startedRef.current === nextNoticeId) {
        return
      }
      startedRef.current = nextNoticeId

      const key = `naranhi:notice-translate:${locale}:${nextNoticeId}`
      window.localStorage.setItem(key, String(Date.now()))
      try {
        await fetch(`/api/notices/${encodeURIComponent(nextNoticeId)}/process`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ target_language: locale }),
          cache: 'no-store',
        })
      } catch {
        // Ignore and let the next refresh retry after cooldown.
      }

      if (!cancelled) {
        router.refresh()
      }
    }

    void run()

    return () => {
      cancelled = true
    }
  }, [locale, noticeIds, router])

  return null
}
