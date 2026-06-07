import type { Locale } from '@/lib/i18n'

export type NoticeTranslationBatchPhase = 'pending' | 'complete'

export interface NoticeTranslationBatch {
  locale: Locale
  noticeIds: string[]
  pendingNoticeIds: string[]
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

function sameIds(left: string[], right: string[]): boolean {
  return left.length === right.length && left.every((value, index) => value === right[index])
}

export async function requestNoticeTranslation(noticeId: string, locale: Locale): Promise<void> {
  if (!isBrowser()) return
  const trimmedId = noticeId.trim()
  if (!trimmedId || locale === 'ko') return

  try {
    await fetch(`/api/notices/${encodeURIComponent(trimmedId)}/process`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ target_language: locale }),
      cache: 'no-store',
    })
  } catch {
    // Ignore transient kickoff failures; polling/refresh will retry later.
  }
}

export async function requestNoticeTranslations(noticeIds: string[], locale: Locale): Promise<void> {
  if (!isBrowser() || locale === 'ko') return
  const normalized = normalizeNoticeIds(noticeIds)
  if (normalized.length === 0) return
  await Promise.allSettled(normalized.map(noticeId => requestNoticeTranslation(noticeId, locale)))
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
      pendingNoticeIds: normalizeNoticeIds(
        Array.isArray(parsed.pendingNoticeIds)
          ? (parsed.pendingNoticeIds as string[])
          : (parsed.noticeIds as string[]),
      ),
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
    pendingNoticeIds: normalizeNoticeIds(batch.pendingNoticeIds),
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
      pendingNoticeIds: normalized,
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
      pendingNoticeIds: normalizeNoticeIds([...current.pendingNoticeIds, ...normalized]),
      phase: 'pending',
      completedAt: undefined,
      completionBannerDismissedAt: undefined,
    })
  }
}

export function syncPendingNoticeTranslationBatch(locale: Locale, noticeIds: string[]) {
  if (!isBrowser()) return

  const normalized = normalizeNoticeIds(noticeIds)
  const current = readNoticeTranslationBatch()

  if (normalized.length === 0) {
    if (current && current.locale === locale && current.phase === 'pending') {
      markNoticeTranslationBatchComplete(current)
    }
    return
  }

  if (!current || current.locale !== locale || current.phase === 'complete') {
    writeNoticeTranslationBatch({
      locale,
      noticeIds: normalized,
      pendingNoticeIds: normalized,
      phase: 'pending',
      createdAt: Date.now(),
    })
    return
  }

  if (sameIds(current.noticeIds, normalized) && sameIds(current.pendingNoticeIds, normalized)) {
    return
  }

  writeNoticeTranslationBatch({
    ...current,
    noticeIds: normalized,
    pendingNoticeIds: normalized,
    phase: 'pending',
    completedAt: undefined,
    completionBannerDismissedAt: undefined,
  })
}

export function updateNoticeTranslationBatchProgress(
  batch: NoticeTranslationBatch,
  pendingNoticeIds: string[],
) {
  const nextPending = normalizeNoticeIds(pendingNoticeIds)
  const complete = nextPending.length === 0

  writeNoticeTranslationBatch({
    ...batch,
    pendingNoticeIds: nextPending,
    phase: complete ? 'complete' : 'pending',
    completedAt: complete ? batch.completedAt ?? Date.now() : undefined,
    completionBannerDismissedAt: complete ? batch.completionBannerDismissedAt : undefined,
  })
}

export function getPendingNoticeIds(batch: NoticeTranslationBatch | null): string[] {
  if (!batch || batch.phase !== 'pending') return []
  return batch.pendingNoticeIds
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
