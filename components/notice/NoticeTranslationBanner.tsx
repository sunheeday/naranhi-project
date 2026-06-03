'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'
import { usePathname, useRouter } from 'next/navigation'
import type { Locale } from '@/lib/i18n'
import {
  dismissNoticeTranslationCompletionBanner,
  markNoticeTranslationBatchComplete,
  markPendingBannerShown,
  NOTICE_TRANSLATION_BATCH_EVENT,
  readNoticeTranslationBatch,
  type NoticeTranslationBatch,
} from '@/lib/notice-translation-batch'

interface BannerMessages {
  pending: string
  complete: string
  view: string
  close: string
}

interface Props {
  locale: Locale
  messages: BannerMessages
}

type BannerMode = 'pending' | 'complete' | null

const PENDING_BANNER_MS = 4000
const COMPLETE_BANNER_MS = 7000
const POLL_INTERVAL_MS = 5000

export default function NoticeTranslationBanner({ locale, messages }: Props) {
  const router = useRouter()
  const pathname = usePathname()
  const [batch, setBatch] = useState<NoticeTranslationBatch | null>(null)
  const [mode, setMode] = useState<BannerMode>(null)

  useEffect(() => {
    const sync = () => setBatch(readNoticeTranslationBatch())
    sync()
    window.addEventListener(NOTICE_TRANSLATION_BATCH_EVENT, sync as EventListener)
    window.addEventListener('storage', sync)
    return () => {
      window.removeEventListener(NOTICE_TRANSLATION_BATCH_EVENT, sync as EventListener)
      window.removeEventListener('storage', sync)
    }
  }, [])

  useEffect(() => {
    if (!batch || batch.locale !== locale || batch.noticeIds.length === 0) {
      setMode(null)
      return
    }
    if (batch.phase === 'complete') {
      if (batch.completionBannerDismissedAt) {
        setMode(null)
      } else {
        setMode('complete')
      }
      return
    }
    if (!batch.pendingBannerShownAt) {
      setMode('pending')
      markPendingBannerShown(batch)
      return
    }
    setMode(null)
  }, [batch, locale])

  useEffect(() => {
    if (mode !== 'pending') return
    const timer = window.setTimeout(() => {
      setMode(current => (current === 'pending' ? null : current))
    }, PENDING_BANNER_MS)
    return () => window.clearTimeout(timer)
  }, [mode])

  useEffect(() => {
    if (mode !== 'complete' || !batch) return
    const timer = window.setTimeout(() => {
      dismissNoticeTranslationCompletionBanner(batch)
      setMode(current => (current === 'complete' ? null : current))
    }, COMPLETE_BANNER_MS)
    return () => window.clearTimeout(timer)
  }, [batch, mode])

  useEffect(() => {
    if (!batch || batch.locale !== locale || batch.phase !== 'pending' || batch.noticeIds.length === 0) {
      return
    }
    const activeBatch = batch

    let cancelled = false

    async function poll() {
      try {
        const response = await fetch('/api/notices/translation-batch-status', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            targetLanguage: activeBatch.locale,
            noticeIds: activeBatch.noticeIds,
          }),
          cache: 'no-store',
        })
        const body = await response.json().catch(() => null)
        if (!response.ok || cancelled || !body?.ok) return
        if (body.complete) {
          const latest = readNoticeTranslationBatch()
          if (latest && latest.phase === 'pending' && latest.locale === activeBatch.locale) {
            markNoticeTranslationBatchComplete(latest)
            router.refresh()
          }
        }
      } catch {
        // Ignore polling hiccups and retry on next interval.
      }
    }

    void poll()
    const timer = window.setInterval(() => {
      void poll()
    }, POLL_INTERVAL_MS)
    return () => {
      cancelled = true
      window.clearInterval(timer)
    }
  }, [batch, locale, router])

  if (!batch || batch.locale !== locale || !mode) {
    return null
  }

  const actionHref = pathname === '/' ? null : '/'
  const title = mode === 'pending' ? messages.pending : messages.complete

  return (
    <div className="fixed inset-x-0 bottom-[calc(env(safe-area-inset-bottom)+4.5rem)] z-50 px-4 pointer-events-none">
      <div className="mx-auto max-w-app pointer-events-auto rounded-card border border-sky-200 bg-[linear-gradient(135deg,#F5FBFF_0%,#E6F4FF_100%)] shadow-card">
        <div className="flex items-start gap-3 px-4 py-3">
          <div className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-white text-primary shadow-soft" aria-hidden="true">
            {mode === 'pending' ? '...' : '✓'}
          </div>
          <div className="min-w-0 flex-1">
            <p className="text-sm font-semibold text-ink">{title}</p>
          </div>
          {mode === 'complete' && actionHref ? (
            <Link
              href={actionHref}
              className="shrink-0 rounded-pill bg-primary px-3 py-1.5 text-xs font-bold text-white"
            >
              {messages.view}
            </Link>
          ) : null}
          <button
            type="button"
            aria-label={messages.close}
            className="shrink-0 rounded-full p-1 text-muted-soft"
            onClick={() => {
              if (mode === 'complete') {
                dismissNoticeTranslationCompletionBanner(batch)
              }
              setMode(null)
            }}
          >
            <span aria-hidden="true">×</span>
          </button>
        </div>
      </div>
    </div>
  )
}
