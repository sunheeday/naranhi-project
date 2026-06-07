'use client'

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
  translationPending: boolean
}

interface Props {
  todoTitle: string
  newsTitle: string
  translationProcessingLabel: string
  actionNotices: DisplayNoticeItem[]
  infoNotices: DisplayNoticeItem[]
}

export default function HomeNoticeSections({
  todoTitle,
  newsTitle,
  translationProcessingLabel,
  actionNotices,
  infoNotices,
}: Props) {
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
        translationPending={notice.translationPending}
        translationProcessingLabel={translationProcessingLabel}
      />
    </li>
  )

  return (
    <>
      {actionNotices.length > 0 && (
        <div>
          <div className="flex items-center gap-2 mb-3">
            <span className="w-2 h-2 rounded-full bg-cat-action" aria-hidden="true" />
            <h2 className="text-sm font-bold text-ink">{todoTitle}</h2>
            <span className="text-xs font-bold text-cat-action">{actionNotices.length}</span>
          </div>
          <ul className="flex flex-col gap-3">
            {actionNotices.map(renderNoticeItem)}
          </ul>
        </div>
      )}

      {infoNotices.length > 0 && (
        <div>
          <div className="flex items-center gap-2 mb-3">
            <span className="w-2 h-2 rounded-full bg-muted-soft" aria-hidden="true" />
            <h2 className="text-sm font-bold text-ink">{newsTitle}</h2>
            <span className="text-xs font-bold text-muted-soft">{infoNotices.length}</span>
          </div>
          <ul className="flex flex-col gap-3">
            {infoNotices.map(renderNoticeItem)}
          </ul>
        </div>
      )}
    </>
  )
}
