import type { Locale } from '@/lib/i18n'

export type NoticeTranslationBatchPhase = 'pending' | 'complete'

export interface NoticeTranslationBatch {
  locale: Locale
  noticeIds: string[]
  phase: NoticeTranslationBatchPhase
  createdAt: number
  pendingBannerShownAt?: number
  completedAt?: number
  completionBannerDismissedAt?: number
}

export const NOTICE_TRANSLATION_BATCH_KEY = 'naranhi:notice-translation-batch'
export const NOTICE_TRANSLATION_BATCH_EVENT = 'naranhi:notice-translation-batch-updated'

function isBrowser(): boolean {
  return typeof window !== 'undefined'
}

function normalizeNoticeIds(noticeIds: string[]): string[] {
  return Array.from(new Set(noticeIds.map(id => id.trim()).filter(Boolean))).sort()
}

export function readNoticeTranslationBatch(): NoticeTranslationBatch | null {
  if (!isBrowser()) return null
  const raw = window.localStorage.getItem(NOTICE_TRANSLATION_BATCH_KEY)
  if (!raw) return null
  try {
    const parsed = JSON.parse(raw) as Partial<NoticeTranslationBatch>
    if (!parsed || typeof parsed.locale !== 'string' || !Array.isArray(parsed.noticeIds)) {
      return null
    }
    const createdAt = Number(parsed.createdAt)
    if (!Number.isFinite(createdAt) || createdAt <= 0) return null
    const phase = parsed.phase === 'complete' ? 'complete' : 'pending'
    return {
      locale: parsed.locale as Locale,
      noticeIds: normalizeNoticeIds(parsed.noticeIds as string[]),
      phase,
      createdAt,
      pendingBannerShownAt: Number.isFinite(parsed.pendingBannerShownAt)
        ? Number(parsed.pendingBannerShownAt)
        : undefined,
      completedAt: Number.isFinite(parsed.completedAt) ? Number(parsed.completedAt) : undefined,
      completionBannerDismissedAt: Number.isFinite(parsed.completionBannerDismissedAt)
        ? Number(parsed.completionBannerDismissedAt)
        : undefined,
    }
  } catch {
    return null
  }
}

export function writeNoticeTranslationBatch(batch: NoticeTranslationBatch) {
  if (!isBrowser()) return
  const normalized: NoticeTranslationBatch = {
    ...batch,
    noticeIds: normalizeNoticeIds(batch.noticeIds),
  }
  window.localStorage.setItem(NOTICE_TRANSLATION_BATCH_KEY, JSON.stringify(normalized))
  window.dispatchEvent(new CustomEvent(NOTICE_TRANSLATION_BATCH_EVENT, { detail: normalized }))
}

export function upsertPendingNoticeTranslationBatch(locale: Locale, noticeIds: string[]) {
  if (!isBrowser()) return
  const normalized = normalizeNoticeIds(noticeIds)
  if (normalized.length === 0) return

  const current = readNoticeTranslationBatch()
  if (!current || current.locale !== locale || current.phase === 'complete') {
    writeNoticeTranslationBatch({
      locale,
      noticeIds: normalized,
      phase: 'pending',
      createdAt: Date.now(),
    })
    return
  }

  const merged = normalizeNoticeIds([...current.noticeIds, ...normalized])
  if (merged.join('|') !== current.noticeIds.join('|')) {
    writeNoticeTranslationBatch({
      ...current,
      noticeIds: merged,
      phase: 'pending',
      completedAt: undefined,
      completionBannerDismissedAt: undefined,
    })
  }
}

export function markPendingBannerShown(batch: NoticeTranslationBatch) {
  writeNoticeTranslationBatch({
    ...batch,
    pendingBannerShownAt: batch.pendingBannerShownAt ?? Date.now(),
  })
}

export function markNoticeTranslationBatchComplete(batch: NoticeTranslationBatch) {
  writeNoticeTranslationBatch({
    ...batch,
    phase: 'complete',
    completedAt: batch.completedAt ?? Date.now(),
    completionBannerDismissedAt: undefined,
  })
}

export function dismissNoticeTranslationCompletionBanner(batch: NoticeTranslationBatch) {
  writeNoticeTranslationBatch({
    ...batch,
    completionBannerDismissedAt: Date.now(),
  })
}
