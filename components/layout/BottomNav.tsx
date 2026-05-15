'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'

const NAV_ITEMS = [
  { href: '/', label: '홈', icon: HomeIcon },
  { href: '/meals', label: '급식', icon: MealIcon },
  { href: '/calendar', label: '캘린더', icon: CalendarIcon },
  { href: '/settings', label: '설정', icon: SettingsIcon },
]

export default function BottomNav() {
  const pathname = usePathname()

  return (
    <nav
      aria-label="하단 탭 바"
      className="fixed bottom-0 inset-x-0 mx-auto w-full max-w-app bg-canvas border-t border-hairline-soft h-14 pb-safe flex items-center shadow-nav"
    >
      <ul className="flex w-full">
        {NAV_ITEMS.map(({ href, label, icon: Icon }) => {
          const isActive = pathname === href || (href !== '/' && pathname.startsWith(href))
          return (
            <li key={href} className="flex-1">
              <Link
                href={href}
                aria-label={label}
                aria-current={isActive ? 'page' : undefined}
                className={`flex flex-col items-center justify-center h-14 gap-0.5 text-[11px] font-semibold transition-colors ${
                  isActive ? 'text-ink' : 'text-muted-soft'
                }`}
              >
                <Icon active={isActive} />
                <span>{label}</span>
              </Link>
            </li>
          )
        })}
      </ul>
    </nav>
  )
}

function HomeIcon({ active }: { active: boolean }) {
  const fill = active ? '#111111' : '#9CA3AF'
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill={fill} aria-hidden="true">
      <path d="M10 20v-6h4v6h5v-8h3L12 3 2 12h3v8z"/>
    </svg>
  )
}

function MealIcon({ active }: { active: boolean }) {
  const fill = active ? '#111111' : '#9CA3AF'
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill={fill} aria-hidden="true">
      <path d="M11 9V2H9v7c0 1.66-1.34 3-3 3v10h2V12c2.21 0 4-1.79 4-3zm5-3v8h2.5v8H21V2c-2.76 0-5 2.24-5 4z"/>
      <path d="M5 2v5c0 .55.45 1 1 1s1-.45 1-1V2H5z"/>
    </svg>
  )
}

function CalendarIcon({ active }: { active: boolean }) {
  const fill = active ? '#111111' : '#9CA3AF'
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill={fill} aria-hidden="true">
      <path d="M19 3h-1V1h-2v2H8V1H6v2H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2zm0 16H5V8h14v11z"/>
    </svg>
  )
}

function SettingsIcon({ active }: { active: boolean }) {
  const fill = active ? '#111111' : '#9CA3AF'
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill={fill} aria-hidden="true">
      <path d="M19.14 12.94c.04-.3.06-.61.06-.94s-.02-.64-.07-.94l2.03-1.58a.49.49 0 0 0 .12-.61l-1.92-3.32a.49.49 0 0 0-.59-.22l-2.39.96a7.02 7.02 0 0 0-1.62-.94l-.36-2.54a.484.484 0 0 0-.48-.41h-3.84c-.24 0-.43.17-.47.41l-.36 2.54c-.59.24-1.13.57-1.62.94l-2.39-.96a.48.48 0 0 0-.59.22L2.74 8.87a.48.48 0 0 0 .12.61l2.03 1.58c-.05.3-.07.62-.07.94s.02.64.07.94l-2.03 1.58a.49.49 0 0 0-.12.61l1.92 3.32c.12.22.37.29.59.22l2.39-.96c.5.37 1.04.7 1.62.94l.36 2.54c.05.24.24.41.48.41h3.84c.24 0 .44-.17.47-.41l.36-2.54c.59-.24 1.13-.57 1.62-.94l2.39.96c.22.08.47 0 .59-.22l1.92-3.32a.49.49 0 0 0-.12-.61l-2.01-1.58zM12 15.6c-1.98 0-3.6-1.62-3.6-3.6s1.62-3.6 3.6-3.6 3.6 1.62 3.6 3.6-1.62 3.6-3.6 3.6z"/>
    </svg>
  )
}
