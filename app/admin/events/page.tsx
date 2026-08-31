'use client'

import Link from 'next/link'
import AdminHeader from '@/components/admin/AdminHeader'
import CharacterEmptyState from '@/components/brand/CharacterEmptyState'
import {
  useAdminData,
  useAdminActions,
  EVENT_TYPE_LABEL,
  AUDIENCE_LABEL,
  formatEventDate,
  dDayLabel,
  type EventType,
} from '@/lib/admin/store'

const TYPE_STYLE: Record<EventType, { bg: string; text: string }> = {
  event: { bg: 'bg-cat-schedule-bg', text: 'text-cat-schedule' },
  exam: { bg: 'bg-brand-sun-soft', text: 'text-brand-orange' },
  deadline: { bg: 'bg-cat-action-bg', text: 'text-cat-action' },
  holiday: { bg: 'bg-cat-supply-bg', text: 'text-cat-supply' },
}

export default function EventsPage() {
  const data = useAdminData()
  const { deleteEvent } = useAdminActions()

  const todayIso = new Date().toISOString().slice(0, 10)
  const upcoming = data.events
    .filter((e) => e.date >= todayIso)
    .sort((a, b) => a.date.localeCompare(b.date) || a.time.localeCompare(b.time))
  const past = data.events.filter((e) => e.date < todayIso).sort((a, b) => b.date.localeCompare(a.date))

  return (
    <main className="flex min-h-screen flex-col pb-24">
      <AdminHeader
        title="일정 관리"
        subtitle={`예정된 일정 ${upcoming.length}건`}
        rightSlot={
          <Link
            href="/admin/events/new"
            className="rounded-pill bg-primary px-3.5 py-2 text-xs font-bold text-on-primary shadow-btn-primary active:bg-primary-active"
          >
            + 등록
          </Link>
        }
      />

      <section className="flex flex-col gap-2.5 px-5 pt-5">
        {upcoming.length === 0 && past.length === 0 ? (
          <CharacterEmptyState character="walk" title="등록된 일정이 없어요." />
        ) : null}

        {upcoming.length > 0 ? (
          <>
            <h2 className="text-sm font-bold text-ink">다가오는 일정</h2>
            {upcoming.map((e) => (
              <EventCard key={e.id} event={e} onDelete={() => deleteEvent(e.id)} />
            ))}
          </>
        ) : null}

        {past.length > 0 ? (
          <>
            <h2 className="mt-4 text-sm font-bold text-muted">지난 일정</h2>
            {past.map((e) => (
              <EventCard key={e.id} event={e} onDelete={() => deleteEvent(e.id)} dimmed />
            ))}
          </>
        ) : null}
      </section>
    </main>
  )
}

function EventCard({
  event,
  onDelete,
  dimmed,
}: {
  event: import('@/lib/admin/store').AdminEvent
  onDelete: () => void
  dimmed?: boolean
}) {
  const dday = dDayLabel(event.date)
  const style = TYPE_STYLE[event.type]
  return (
    <article
      className={`flex items-start gap-3 rounded-card border border-hairline bg-surface px-4 py-3.5 shadow-soft ${
        dimmed ? 'opacity-60' : ''
      }`}
    >
      <span className={`flex h-14 w-14 shrink-0 flex-col items-center justify-center rounded-md ${style.bg}`}>
        <span className={`text-[10px] font-semibold ${style.text}`}>{Number(event.date.slice(5, 7))}월</span>
        <span className={`text-xl font-extrabold leading-none ${style.text}`}>
          {Number(event.date.slice(8, 10))}
        </span>
      </span>
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span className={`rounded-pill px-2 py-0.5 text-[11px] font-semibold ${style.bg} ${style.text}`}>
            {EVENT_TYPE_LABEL[event.type]}
          </span>
          {!dimmed ? (
            <span
              className={`rounded-pill px-2 py-0.5 text-[11px] font-bold ${
                dday.urgent ? 'bg-cat-action-bg text-cat-action' : 'bg-surface-soft text-muted'
              }`}
            >
              {dday.text}
            </span>
          ) : null}
        </div>
        <p className="mt-1.5 text-sm font-bold text-ink">{event.title}</p>
        <p className="mt-0.5 text-xs text-muted">
          {formatEventDate(event.date)}
          {event.time ? ` · ${event.time}` : ''} · {AUDIENCE_LABEL[event.audience]}
        </p>
        {event.memo ? <p className="mt-1 text-xs text-body text-readable">{event.memo}</p> : null}
      </div>
      <button
        type="button"
        aria-label="일정 삭제"
        onClick={() => {
          if (confirm('이 일정을 삭제할까요?')) onDelete()
        }}
        className="-mr-1 -mt-1 flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-muted-soft active:bg-surface-soft"
      >
        <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
          <path d="M6 19c0 1.1.9 2 2 2h8c1.1 0 2-.9 2-2V7H6v12zM19 4h-3.5l-1-1h-5l-1 1H5v2h14V4z" />
        </svg>
      </button>
    </article>
  )
}
