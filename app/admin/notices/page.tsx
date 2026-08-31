'use client'

import { useState } from 'react'
import Link from 'next/link'
import AdminHeader from '@/components/admin/AdminHeader'
import CharacterEmptyState from '@/components/brand/CharacterEmptyState'
import {
  useAdminData,
  useAdminActions,
  NOTICE_CATEGORY_LABEL,
  AUDIENCE_LABEL,
  relativeTime,
  type NoticeCategory,
} from '@/lib/admin/store'

const FILTERS: { value: 'all' | NoticeCategory; label: string }[] = [
  { value: 'all', label: '전체' },
  { value: 'letter', label: '가정통신문' },
  { value: 'notice', label: '알림' },
  { value: 'meal', label: '급식' },
  { value: 'event', label: '행사' },
]

export default function NoticesPage() {
  const data = useAdminData()
  const { deleteNotice, togglePin } = useAdminActions()
  const [filter, setFilter] = useState<'all' | NoticeCategory>('all')
  const [openId, setOpenId] = useState<string | null>(null)

  const filtered = data.notices.filter((n) => filter === 'all' || n.category === filter)
  const sorted = [...filtered].sort((a, b) => {
    if (a.pinned !== b.pinned) return a.pinned ? -1 : 1
    return b.createdAt.localeCompare(a.createdAt)
  })

  return (
    <main className="flex min-h-screen flex-col pb-24">
      <AdminHeader
        title="공지 관리"
        subtitle={`등록된 공지 ${data.notices.length}건`}
        rightSlot={
          <Link
            href="/admin/notices/new"
            className="rounded-pill bg-primary px-3.5 py-2 text-xs font-bold text-on-primary shadow-btn-primary active:bg-primary-active"
          >
            + 등록
          </Link>
        }
      />

      {/* 필터 */}
      <div className="sticky top-[61px] z-[9] flex gap-2 overflow-x-auto border-b border-hairline-soft bg-canvas px-5 py-3">
        {FILTERS.map((f) => {
          const active = filter === f.value
          return (
            <button
              key={f.value}
              type="button"
              onClick={() => setFilter(f.value)}
              className={`shrink-0 rounded-pill border px-3.5 py-1.5 text-xs font-semibold transition ${
                active ? 'border-primary bg-primary text-on-primary' : 'border-hairline bg-surface text-body'
              }`}
            >
              {f.label}
            </button>
          )
        })}
      </div>

      <section className="flex flex-col gap-2.5 px-5 pt-4">
        {sorted.length === 0 ? (
          <CharacterEmptyState character="readingBlue" title="등록된 공지가 없어요." />
        ) : (
          sorted.map((n) => {
            const isOpen = openId === n.id
            return (
              <article
                key={n.id}
                className="overflow-hidden rounded-card border border-hairline bg-surface shadow-soft"
              >
                <button
                  type="button"
                  onClick={() => setOpenId(isOpen ? null : n.id)}
                  className="flex w-full flex-col gap-2 px-4 py-3.5 text-left"
                >
                  <div className="flex items-center gap-2">
                    <span className="rounded-pill bg-primary-soft px-2 py-0.5 text-[11px] font-semibold text-primary">
                      {NOTICE_CATEGORY_LABEL[n.category]}
                    </span>
                    <span className="rounded-pill bg-surface-soft px-2 py-0.5 text-[11px] font-medium text-muted">
                      {AUDIENCE_LABEL[n.audience]}
                    </span>
                    {n.pinned ? <span className="text-xs">📌</span> : null}
                    <span className="ml-auto text-[11px] text-muted-soft">{relativeTime(n.createdAt)}</span>
                  </div>
                  <p className="text-sm font-bold text-ink">{n.title}</p>
                  {!isOpen ? (
                    <p className="line-clamp-1 text-xs text-muted text-readable">{n.body}</p>
                  ) : null}
                </button>

                {isOpen ? (
                  <div className="border-t border-hairline-soft px-4 py-3.5">
                    <p className="whitespace-pre-wrap text-sm leading-relaxed text-body text-readable">{n.body}</p>
                    <div className="mt-3.5 flex gap-2">
                      <button
                        type="button"
                        onClick={() => togglePin(n.id)}
                        className="flex-1 rounded-md border border-hairline bg-surface py-2 text-xs font-semibold text-body active:bg-surface-soft"
                      >
                        {n.pinned ? '고정 해제' : '상단 고정'}
                      </button>
                      <button
                        type="button"
                        onClick={() => {
                          if (confirm('이 공지를 삭제할까요?')) deleteNotice(n.id)
                        }}
                        className="flex-1 rounded-md border border-hairline bg-surface py-2 text-xs font-semibold text-error active:bg-surface-soft"
                      >
                        삭제
                      </button>
                    </div>
                  </div>
                ) : null}
              </article>
            )
          })
        )}
      </section>
    </main>
  )
}
