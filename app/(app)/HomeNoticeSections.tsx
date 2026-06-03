'use client'

import { useEffect, useMemo, useState } from 'react'
import type { Locale } from '@/lib/i18n'
import {
  NOTICE_TRANSLATION_BATCH_EVENT,
  readNoticeTranslationBatch,
  type NoticeTranslationBatch,
} from '@/lib/notice-translation-batch'
import NoticeCardItem from './NoticeCardItem'

interface DisplayNoticeItem {
  id: string
  accentBar: string
  badgeBg: string
  badgeText: string
  badgeLabel: string
  title: string
  statusLabel: string
  arrivedAt: string
  arrivedSuffix: string
  dueLabel: string | null
  dueUrgent: boolean
  deleteLabel: string
  confirmTitle: string
  confirmBody?: string
  confirmCancel: string
  confirmDelete: string
  deletingLabel: string
}

interface Props {
  locale: Locale
  todoTitle: string
  newsTitle: string
  actionNotices: DisplayNoticeItem[]
  infoNotices: DisplayNoticeItem[]
}

function filterPendingBatchNotices(
  notices: DisplayNoticeItem[],
  batch: NoticeTranslationBatch | null,
  locale: Locale,
): DisplayNoticeItem[] {
  if (!batch || batch.locale !== locale || batch.phase !== 'pending') {
    return notices
  }
  const pendingIds = new Set(batch.noticeIds)
  return notices.filter(notice => !pendingIds.has(notice.id))
}

export default function HomeNoticeSections({
  locale,
  todoTitle,
  newsTitle,
  actionNotices,
  infoNotices,
}: Props) {
  const [batch, setBatch] = useState<NoticeTranslationBatch | null>(null)

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

  const visibleActionNotices = useMemo(
    () => filterPendingBatchNotices(actionNotices, batch, locale),
    [actionNotices, batch, locale],
  )
  const visibleInfoNotices = useMemo(
    () => filterPendingBatchNotices(infoNotices, batch, locale),
    [infoNotices, batch, locale],
  )

  const renderNoticeItem = (notice: DisplayNoticeItem) => (
    <li key={notice.id}>
      <NoticeCardItem
        noticeId={notice.id}
        title={notice.title}
        statusLabel={notice.statusLabel}
        arrivedAt={notice.arrivedAt}
        arrivedSuffix={notice.arrivedSuffix}
        accentBar={notice.accentBar}
        badgeBg={notice.badgeBg}
        badgeText={notice.badgeText}
        badgeLabel={notice.badgeLabel}
        dueLabel={notice.dueLabel}
        dueUrgent={notice.dueUrgent}
        deleteLabel={notice.deleteLabel}
        confirmTitle={notice.confirmTitle}
        confirmBody={notice.confirmBody}
        confirmCancel={notice.confirmCancel}
        confirmDelete={notice.confirmDelete}
        deletingLabel={notice.deletingLabel}
      />
    </li>
  )

  return (
    <>
      {visibleActionNotices.length > 0 && (
        <div>
          <div className="flex items-center gap-2 mb-3">
            <span className="w-2 h-2 rounded-full bg-cat-action" aria-hidden="true" />
            <h2 className="text-sm font-bold text-ink">{todoTitle}</h2>
            <span className="text-xs font-bold text-cat-action">{visibleActionNotices.length}</span>
          </div>
          <ul className="flex flex-col gap-3">
            {visibleActionNotices.map(renderNoticeItem)}
          </ul>
        </div>
      )}

      {visibleInfoNotices.length > 0 && (
        <div>
          <div className="flex items-center gap-2 mb-3">
            <span className="w-2 h-2 rounded-full bg-muted-soft" aria-hidden="true" />
            <h2 className="text-sm font-bold text-ink">{newsTitle}</h2>
            <span className="text-xs font-bold text-muted-soft">{visibleInfoNotices.length}</span>
          </div>
          <ul className="flex flex-col gap-3">
            {visibleInfoNotices.map(renderNoticeItem)}
          </ul>
        </div>
      )}
    </>
  )
}
