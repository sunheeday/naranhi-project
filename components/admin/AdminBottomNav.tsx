'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'

const NAV_ITEMS = [
  { href: '/admin', label: '홈', icon: HomeIcon, action: false },
  { href: '/admin/notices', label: '공지', icon: NoticeIcon, action: false },
  { href: '/admin/notices/new', label: '등록', icon: PlusIcon, action: true },
  { href: '/admin/events', label: '일정', icon: CalendarIcon, action: false },
  { href: '/admin/messages', label: '메시지', icon: MessageIcon, action: false },
] as const

export default function AdminBottomNav() {
  const pathname = usePathname()

  return (
    <nav
      aria-label="어드민 하단 내비게이션"
      className="fixed bottom-0 inset-x-0 mx-auto flex h-14 w-full max-w-app items-center border-t border-hairline-soft bg-canvas pb-safe shadow-nav"
    >
      <ul className="flex w-full">
        {NAV_ITEMS.map(({ href, label, icon: Icon, action }) => {
          const isActive =
            href === '/admin'
              ? pathname === '/admin'
              : href === '/admin/notices/new'
                ? pathname === '/admin/notices/new'
                : pathname === href || pathname.startsWith(href + '/')
          return (
            <li key={href} className="flex-1">
              <Link
                href={href}
                aria-label={label}
                aria-current={isActive ? 'page' : undefined}
                className={
                  action
                    ? 'relative -mt-5 flex h-[72px] flex-col items-center justify-start gap-1 text-[11px] font-semibold text-primary transition-transform active:scale-95'
                    : `flex h-14 flex-col items-center justify-center gap-0.5 text-[11px] font-semibold transition-colors ${
                        isActive ? 'text-primary' : 'text-muted-soft'
                      }`
                }
              >
                {action ? (
                  <>
                    <span
                      className={`flex h-14 w-14 items-center justify-center rounded-full border-4 border-canvas shadow-btn-primary ${
                        isActive ? 'bg-primary-active' : 'bg-primary'
                      }`}
                    >
                      <Icon active />
                    </span>
                    <span>{label}</span>
                  </>
                ) : (
                  <>
                    <Icon active={isActive} />
                    <span>{label}</span>
                  </>
                )}
              </Link>
            </li>
          )
        })}
      </ul>
    </nav>
  )
}

function HomeIcon({ active }: { active: boolean }) {
  const fill = active ? '#5DAFEA' : '#A89F99'
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill={fill} aria-hidden="true">
      <path d="M10 20v-6h4v6h5v-8h3L12 3 2 12h3v8z" />
    </svg>
  )
}

function NoticeIcon({ active }: { active: boolean }) {
  const fill = active ? '#5DAFEA' : '#A89F99'
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill={fill} aria-hidden="true">
      <path d="M14 2H6c-1.1 0-2 .9-2 2v16c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2V8l-6-6zm2 16H8v-2h8v2zm0-4H8v-2h8v2zm-3-5V3.5L18.5 9H13z" />
    </svg>
  )
}

function CalendarIcon({ active }: { active: boolean }) {
  const fill = active ? '#5DAFEA' : '#A89F99'
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill={fill} aria-hidden="true">
      <path d="M19 3h-1V1h-2v2H8V1H6v2H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2zm0 16H5V8h14v11z" />
    </svg>
  )
}

function MessageIcon({ active }: { active: boolean }) {
  const fill = active ? '#5DAFEA' : '#A89F99'
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill={fill} aria-hidden="true">
      <path d="M20 2H4c-1.1 0-2 .9-2 2v18l4-4h14c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2zm-2 12H6v-2h12v2zm0-3H6V9h12v2zm0-3H6V6h12v2z" />
    </svg>
  )
}

function PlusIcon({ active }: { active: boolean }) {
  const fill = active ? '#FFFFFF' : '#A89F99'
  return (
    <svg width="26" height="26" viewBox="0 0 24 24" fill={fill} aria-hidden="true">
      <path d="M19 13h-6v6h-2v-6H5v-2h6V5h2v6h6v2z" />
    </svg>
  )
}
