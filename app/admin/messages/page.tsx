'use client'

import Link from 'next/link'
import AdminHeader from '@/components/admin/AdminHeader'
import CharacterEmptyState from '@/components/brand/CharacterEmptyState'
import { useAdminData, useAdminActions, relativeTime } from '@/lib/admin/store'

export default function MessagesPage() {
  const data = useAdminData()
  const { deleteMessage } = useAdminActions()

  const sorted = [...data.messages].sort((a, b) => b.sentAt.localeCompare(a.sentAt))

  return (
    <main className="flex min-h-screen flex-col pb-24">
      <AdminHeader
        title="메시지"
        subtitle={`보낸 메시지 ${data.messages.length}건`}
        rightSlot={
          <Link
            href="/admin/messages/new"
            className="rounded-pill bg-primary px-3.5 py-2 text-xs font-bold text-on-primary shadow-btn-primary active:bg-primary-active"
          >
            + 작성
          </Link>
        }
      />

      <section className="flex flex-col gap-2.5 px-5 pt-5">
        {sorted.length === 0 ? (
          <CharacterEmptyState
            character="wave"
            title="아직 보낸 메시지가 없어요."
            description="학부모님께 전할 소식을 메시지로 보내보세요."
            action={
              <Link
                href="/admin/messages/new"
                className="rounded-btn bg-primary px-5 py-2.5 text-sm font-bold text-on-primary shadow-btn-primary active:bg-primary-active"
              >
                메시지 작성
              </Link>
            }
          />
        ) : (
          sorted.map((m) => (
            <article key={m.id} className="rounded-card border border-hairline bg-surface px-4 py-3.5 shadow-soft">
              <div className="flex items-center gap-2">
                <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-brand-sun-soft text-sm">
                  ✉️
                </span>
                <div className="min-w-0 flex-1">
                  <p className="truncate text-xs font-semibold text-primary">{m.recipient}</p>
                </div>
                <span className="text-[11px] text-muted-soft">{relativeTime(m.sentAt)}</span>
                <button
                  type="button"
                  aria-label="메시지 삭제"
                  onClick={() => {
                    if (confirm('이 메시지를 삭제할까요?')) deleteMessage(m.id)
                  }}
                  className="-mr-1 flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-muted-soft active:bg-surface-soft"
                >
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
                    <path d="M6 19c0 1.1.9 2 2 2h8c1.1 0 2-.9 2-2V7H6v12zM19 4h-3.5l-1-1h-5l-1 1H5v2h14V4z" />
                  </svg>
                </button>
              </div>
              <p className="mt-2 text-sm font-bold text-ink">{m.title}</p>
              <p className="mt-1 whitespace-pre-wrap text-sm leading-relaxed text-body text-readable">{m.body}</p>
            </article>
          ))
        )}
      </section>
    </main>
  )
}
