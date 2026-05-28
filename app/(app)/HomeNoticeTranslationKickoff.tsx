'use client'

import { useEffect, useRef } from 'react'
import { useRouter } from 'next/navigation'
import type { Locale } from '@/lib/i18n'

interface Props {
  locale: Locale
  noticeIds: string[]
}

const SUCCESS_COOLDOWN_MS = 5 * 60 * 1000
const FAILURE_COOLDOWN_MS = 45 * 1000

interface AttemptState {
  at: number
  cooldownMs: number
}

function readAttemptState(key: string): AttemptState | null {
  const raw = window.localStorage.getItem(key)
  if (!raw) return null

  const legacyTimestamp = Number(raw)
  if (Number.isFinite(legacyTimestamp) && legacyTimestamp > 0) {
    return { at: legacyTimestamp, cooldownMs: FAILURE_COOLDOWN_MS }
  }

  try {
    const parsed = JSON.parse(raw) as Partial<AttemptState>
    if (!Number.isFinite(parsed.at) || !Number.isFinite(parsed.cooldownMs)) {
      return null
    }
    return { at: Number(parsed.at), cooldownMs: Number(parsed.cooldownMs) }
  } catch {
    return null
  }
}

function writeAttemptState(key: string, cooldownMs: number) {
  window.localStorage.setItem(key, JSON.stringify({ at: Date.now(), cooldownMs }))
}

export default function HomeNoticeTranslationKickoff({ locale, noticeIds }: Props) {
  const router = useRouter()
  const startedRef = useRef<string | null>(null)

  useEffect(() => {
    if (locale === 'ko' || noticeIds.length === 0) return

    let cancelled = false

    async function run() {
      const nextNoticeId = noticeIds.find(noticeId => {
        const key = `naranhi:notice-translate:${locale}:${noticeId}`
        const previousAttempt = readAttemptState(key)
        return !previousAttempt || Date.now() - previousAttempt.at >= previousAttempt.cooldownMs
      })
      if (!nextNoticeId || startedRef.current === nextNoticeId) {
        return
      }
      startedRef.current = nextNoticeId

      const key = `naranhi:notice-translate:${locale}:${nextNoticeId}`
      try {
        const response = await fetch(`/api/notices/${encodeURIComponent(nextNoticeId)}/process`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ target_language: locale }),
          cache: 'no-store',
        })
        writeAttemptState(
          key,
          response.ok ? SUCCESS_COOLDOWN_MS : FAILURE_COOLDOWN_MS,
        )
      } catch {
        writeAttemptState(key, FAILURE_COOLDOWN_MS)
        // Ignore and let the next refresh retry after a short cooldown.
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
