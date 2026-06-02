'use client'

import Link from 'next/link'
import { useState, useTransition } from 'react'
import { deleteNotice } from './actions'

interface Props {
  noticeId: string
  title: string
  statusLabel: string
  arrivedAt: string
  arrivedSuffix: string
  /** Tailwind 클래스: 좌측 4px 세로 컬러 바용 (예: 'bg-cat-supply') */
  accentBar: string
  /** 카테고리 뱃지 배경 (예: 'bg-cat-supply-bg') */
  badgeBg: string
  /** 카테고리 뱃지 텍스트 (예: 'text-cat-supply') */
  badgeText: string
  badgeLabel: string
  /** 마감/일정 칩 텍스트 (예: 'D-3 · 4/18'). 연결된 날짜가 있을 때만 전달. */
  dueLabel?: string | null
  /** 마감 임박(D-3 이내) 시 빨강 강조 */
  dueUrgent?: boolean
  deleteLabel: string
  confirmTitle: string
  confirmBody?: string
  confirmCancel: string
  confirmDelete: string
  deletingLabel: string
}

export default function NoticeCardItem({
  noticeId,
  title,
  statusLabel,
  arrivedAt,
  arrivedSuffix,
  accentBar,
  badgeBg,
  badgeText,
  badgeLabel,
  dueLabel,
  dueUrgent = false,
  deleteLabel,
  confirmTitle,
  confirmBody,
  confirmCancel,
  confirmDelete,
  deletingLabel,
}: Props) {
  const [askingConfirm, setAskingConfirm] = useState(false)
  const [isPending, startTransition] = useTransition()
  const [error, setError] = useState<string | null>(null)

  function onDeleteClick(e: React.MouseEvent) {
    e.preventDefault()
    e.stopPropagation()
    setError(null)
    setAskingConfirm(true)
  }

  function onConfirm() {
    setError(null)
    startTransition(async () => {
      const res = await deleteNotice(noticeId)
      if (!res.ok) {
        setError(res.error)
        return
      }
      setAskingConfirm(false)
    })
  }

  return (
    <>
      <div className="relative">
        <Link
          href={`/notices/${noticeId}`}
          className="block bg-surface-card rounded-card shadow-card p-4 pe-12 active:scale-[0.98] transition-transform overflow-hidden"
          aria-label={title}
        >
          {/* 좌측 4px 세로 카테고리 컬러 바 */}
          <span
            aria-hidden="true"
            className={`absolute top-0 bottom-0 start-0 w-1 ${accentBar}`}
          />

          <div className="flex items-center justify-between mb-3 gap-2">
            <div className="flex items-center gap-1.5 min-w-0">
              <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-pill text-xs font-medium ${badgeBg} ${badgeText}`}>
                {badgeLabel}
              </span>
              {dueLabel && (
                <span
                  className={`inline-flex items-center px-2 py-1 rounded-pill text-xs font-bold whitespace-nowrap ${
                    dueUrgent ? 'bg-red-50 text-error' : 'bg-primary-soft text-primary'
                  }`}
                >
                  {dueLabel}
                </span>
              )}
            </div>
            {statusLabel && (
              <span className="text-xs text-muted shrink-0">{statusLabel}</span>
            )}
          </div>
          <h2 className="text-base font-semibold text-ink line-clamp-2 leading-snug text-readable">{title}</h2>
          <p className="text-xs text-muted-soft mt-2">
            {arrivedAt}{arrivedSuffix}
          </p>
        </Link>
        <button
          type="button"
          onClick={onDeleteClick}
          aria-label={deleteLabel}
          className="absolute top-3 end-3 w-9 h-9 rounded-full flex items-center justify-center text-muted-soft active:bg-hairline-soft"
        >
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
            <path d="M3 6h18M8 6V4a1 1 0 0 1 1-1h6a1 1 0 0 1 1 1v2M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6" />
            <path d="M10 11v6M14 11v6" />
          </svg>
        </button>
      </div>

      {askingConfirm && (
        <div
          className="fixed inset-0 z-50 flex items-end sm:items-center justify-center bg-black/40"
          onClick={() => !isPending && setAskingConfirm(false)}
        >
          <div
            role="dialog"
            aria-modal="true"
            className="w-full max-w-app bg-canvas rounded-t-2xl sm:rounded-2xl p-6 flex flex-col gap-4"
            onClick={e => e.stopPropagation()}
          >
            <h3 className="text-lg font-bold text-ink">{confirmTitle}</h3>
            {confirmBody ? <p className="text-sm text-muted">{confirmBody}</p> : null}
            {error && <p className="text-sm text-error">{error}</p>}
            <div className="flex gap-2 mt-2">
              <button
                type="button"
                onClick={() => setAskingConfirm(false)}
                disabled={isPending}
                className="flex-1 h-11 rounded-btn border border-hairline text-muted font-semibold"
              >
                {confirmCancel}
              </button>
              <button
                type="button"
                onClick={onConfirm}
                disabled={isPending}
                className="flex-1 h-11 rounded-btn bg-primary text-on-primary font-semibold active:bg-primary-active disabled:opacity-60"
              >
                {isPending ? deletingLabel : confirmDelete}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  )
}
