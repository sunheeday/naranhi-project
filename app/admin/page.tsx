'use client'

import Link from 'next/link'
import CharacterImage from '@/components/brand/CharacterImage'
import AdminHeader from '@/components/admin/AdminHeader'
import {
  useAdminData,
  TEACHER_PROFILE,
  CLASS_LABEL,
  NOTICE_CATEGORY_LABEL,
  EVENT_TYPE_LABEL,
  relativeTime,
  dDayLabel,
} from '@/lib/admin/store'

const QUICK_ACTIONS = [
  { href: '/admin/notices/new', label: '공지 등록', desc: '가정통신문·알림', color: 'bg-cat-action-bg', accent: 'text-cat-action', icon: NoticeGlyph },
  { href: '/admin/events/new', label: '일정 등록', desc: '행사·시험·마감', color: 'bg-cat-schedule-bg', accent: 'text-cat-schedule', icon: CalendarGlyph },
  { href: '/admin/messages/new', label: '메시지 보내기', desc: '학부모 알림', color: 'bg-brand-sun-soft', accent: 'text-brand-orange', icon: MessageGlyph },
] as const

export default function AdminDashboard() {
  const data = useAdminData()

  const weekAgo = new Date().getTime() - 7 * 86400000
  const weeklyNotices = data.notices.filter((n) => new Date(n.createdAt).getTime() >= weekAgo).length
  const todayIso = new Date().toISOString().slice(0, 10)
  const upcomingEvents = data.events
    .filter((e) => e.date >= todayIso)
    .sort((a, b) => a.date.localeCompare(b.date))
  const recentNotices = data.notices.slice(0, 3)

  return (
    <main className="flex min-h-screen flex-col pb-24">
      <AdminHeader
        title="나란히 선생님"
        subtitle={`${TEACHER_PROFILE.school} · ${CLASS_LABEL}`}
        rightSlot={
          <div className="flex h-10 w-10 items-center justify-center overflow-hidden rounded-full character-disc">
            <CharacterImage character="thumbBlue" size={30} />
          </div>
        }
      />

      <section className="px-5 pt-5">
        <div className="rounded-card bg-primary-soft px-5 py-4">
          <p className="text-sm text-body">안녕하세요, {TEACHER_PROFILE.teacherName} 👋</p>
          <p className="mt-0.5 text-base font-bold text-ink">
            오늘도 우리 반 소식을 학부모님께 나란히 전해요.
          </p>
        </div>
      </section>

      {/* 통계 */}
      <section className="grid grid-cols-3 gap-2.5 px-5 pt-4">
        <StatTile label="이번 주 공지" value={weeklyNotices} />
        <StatTile label="예정 일정" value={upcomingEvents.length} />
        <StatTile label="보낸 메시지" value={data.messages.length} />
      </section>

      {/* 빠른 실행 */}
      <section className="px-5 pt-6">
        <h2 className="text-sm font-bold text-ink">빠른 실행</h2>
        <div className="mt-3 flex flex-col gap-2.5">
          {QUICK_ACTIONS.map(({ href, label, desc, color, accent, icon: Icon }) => (
            <Link
              key={href}
              href={href}
              className="flex items-center gap-3.5 rounded-card border border-hairline bg-surface px-4 py-3.5 shadow-soft transition active:scale-[0.99]"
            >
              <span className={`flex h-11 w-11 shrink-0 items-center justify-center rounded-full ${color} ${accent}`}>
                <Icon />
              </span>
              <span className="min-w-0 flex-1">
                <span className="block text-base font-bold text-ink">{label}</span>
                <span className="block text-xs text-muted">{desc}</span>
              </span>
              <ChevronRight />
            </Link>
          ))}
        </div>
      </section>

      {/* 다가오는 일정 */}
      <section className="px-5 pt-7">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-bold text-ink">다가오는 일정</h2>
          <Link href="/admin/events" className="text-xs font-semibold text-primary">
            전체 보기
          </Link>
        </div>
        {upcomingEvents.length === 0 ? (
          <p className="mt-3 rounded-card border border-hairline bg-surface px-4 py-6 text-center text-sm text-muted">
            예정된 일정이 없어요.
          </p>
        ) : (
          <ul className="mt-3 flex flex-col gap-2">
            {upcomingEvents.slice(0, 3).map((e) => {
              const dday = dDayLabel(e.date)
              return (
                <li key={e.id}>
                  <Link
                    href="/admin/events"
                    className="flex items-center gap-3 rounded-card border border-hairline bg-surface px-4 py-3 shadow-soft"
                  >
                    <span className="flex h-12 w-12 shrink-0 flex-col items-center justify-center rounded-md bg-cat-schedule-bg">
                      <span className="text-[10px] font-semibold text-cat-schedule">
                        {Number(e.date.slice(5, 7))}월
                      </span>
                      <span className="text-lg font-extrabold leading-none text-cat-schedule">
                        {Number(e.date.slice(8, 10))}
                      </span>
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-sm font-semibold text-ink">{e.title}</span>
                      <span className="mt-0.5 block text-xs text-muted">
                        {EVENT_TYPE_LABEL[e.type]}
                        {e.time ? ` · ${e.time}` : ''}
                      </span>
                    </span>
                    <span
                      className={`shrink-0 rounded-pill px-2.5 py-1 text-[11px] font-bold ${
                        dday.urgent ? 'bg-cat-action-bg text-cat-action' : 'bg-surface-soft text-muted'
                      }`}
                    >
                      {dday.text}
                    </span>
                  </Link>
                </li>
              )
            })}
          </ul>
        )}
      </section>

      {/* 최근 공지 */}
      <section className="px-5 pt-7">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-bold text-ink">최근 등록한 공지</h2>
          <Link href="/admin/notices" className="text-xs font-semibold text-primary">
            전체 보기
          </Link>
        </div>
        <ul className="mt-3 flex flex-col gap-2">
          {recentNotices.map((n) => (
            <li key={n.id}>
              <Link
                href="/admin/notices"
                className="block rounded-card border border-hairline bg-surface px-4 py-3 shadow-soft"
              >
                <div className="flex items-center gap-2">
                  <span className="rounded-pill bg-primary-soft px-2 py-0.5 text-[11px] font-semibold text-primary">
                    {NOTICE_CATEGORY_LABEL[n.category]}
                  </span>
                  {n.pinned ? <span className="text-xs">📌</span> : null}
                  <span className="ml-auto text-[11px] text-muted-soft">{relativeTime(n.createdAt)}</span>
                </div>
                <p className="mt-1.5 truncate text-sm font-semibold text-ink">{n.title}</p>
              </Link>
            </li>
          ))}
        </ul>
      </section>
    </main>
  )
}

function StatTile({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-card border border-hairline bg-surface px-3 py-3.5 text-center shadow-soft">
      <p className="text-2xl font-extrabold text-primary">{value}</p>
      <p className="mt-0.5 text-[11px] font-medium text-muted">{label}</p>
    </div>
  )
}

function ChevronRight() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true" className="shrink-0 rtl-flip">
      <path d="M9 6l6 6-6 6" stroke="#B3ABA5" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

function NoticeGlyph() {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
      <path d="M14 2H6c-1.1 0-2 .9-2 2v16c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2V8l-6-6zm2 16H8v-2h8v2zm0-4H8v-2h8v2zm-3-5V3.5L18.5 9H13z" />
    </svg>
  )
}

function CalendarGlyph() {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
      <path d="M19 3h-1V1h-2v2H8V1H6v2H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2zm0 16H5V8h14v11z" />
    </svg>
  )
}

function MessageGlyph() {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
      <path d="M20 2H4c-1.1 0-2 .9-2 2v18l4-4h14c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2z" />
    </svg>
  )
}
