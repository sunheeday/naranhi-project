'use client'

import { useEffect } from 'react'
import { useRouter } from 'next/navigation'
import type { Locale } from '@/lib/i18n'

interface Props {
  noticeId: string
  locale: Locale
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

export default function NoticeLocaleTranslationKickoff({ noticeId, locale }: Props) {
  const router = useRouter()

  useEffect(() => {
    if (locale === 'ko') return

    const key = `naranhi:notice-translate:${locale}:${noticeId}`
    const previousAttempt = readAttemptState(key)
    if (previousAttempt && Date.now() - previousAttempt.at < previousAttempt.cooldownMs) {
      return
    }

    const controller = new AbortController()
    fetch(`/api/notices/${encodeURIComponent(noticeId)}/process`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ target_language: locale }),
      cache: 'no-store',
      signal: controller.signal,
    })
      .then(response => {
        writeAttemptState(
          key,
          response.ok ? SUCCESS_COOLDOWN_MS : FAILURE_COOLDOWN_MS,
        )
        router.refresh()
      })
      .catch(() => {
        if (!controller.signal.aborted) {
          writeAttemptState(key, FAILURE_COOLDOWN_MS)
        }
        if (!controller.signal.aborted) {
          router.refresh()
        }
      })

    return () => controller.abort()
  }, [locale, noticeId, router])

  return null
}
