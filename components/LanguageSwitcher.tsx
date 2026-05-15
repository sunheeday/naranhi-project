'use client'

import { useState, useTransition } from 'react'
import { useRouter } from 'next/navigation'
import { locales, localeNames, localeFlags, type Locale } from '@/lib/i18n'

interface LanguageSwitcherProps {
  currentLocale: Locale
  compact?: boolean
}

export default function LanguageSwitcher({ currentLocale, compact = false }: LanguageSwitcherProps) {
  const router = useRouter()
  const [isPending, startTransition] = useTransition()
  const [open, setOpen] = useState(false)

  function handleChange(locale: Locale) {
    setOpen(false)
    startTransition(() => {
      fetch('/api/locale', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ locale }),
      }).finally(() => router.refresh())
    })
  }

  // Compact: 드롭다운 형태 (헤더용). Full: 그리드 형태 (설정용)
  if (compact) {
    return (
      <div className="relative">
        <button
          type="button"
          onClick={() => setOpen(o => !o)}
          aria-expanded={open}
          aria-label="언어 선택"
          disabled={isPending}
          className="flex items-center gap-1.5 h-10 px-3 rounded-btn border border-hairline bg-canvas text-sm text-ink"
        >
          <span aria-hidden="true">{localeFlags[currentLocale]}</span>
          <span className="text-xs font-semibold">{localeNames[currentLocale]}</span>
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" aria-hidden="true">
            <path d="M6 9l6 6 6-6" />
          </svg>
        </button>
        {open && (
          <>
            <button
              type="button"
              aria-label="닫기"
              onClick={() => setOpen(false)}
              className="fixed inset-0 z-40 bg-transparent cursor-default"
            />
            <ul
              role="listbox"
              className="absolute end-0 top-12 z-50 min-w-[180px] bg-canvas border border-hairline rounded-card shadow-soft py-1.5"
            >
              {locales.map(locale => {
                const isActive = locale === currentLocale
                return (
                  <li key={locale} role="option" aria-selected={isActive}>
                    <button
                      type="button"
                      onClick={() => handleChange(locale)}
                      disabled={isPending}
                      className={`w-full text-start flex items-center gap-2.5 px-4 py-2.5 text-sm ${
                        isActive ? 'bg-surface-card text-ink font-semibold' : 'text-body active:bg-surface-card'
                      }`}
                    >
                      <span aria-hidden="true">{localeFlags[locale]}</span>
                      <span>{localeNames[locale]}</span>
                      {isActive && <span aria-hidden="true" className="ms-auto text-ink">✓</span>}
                    </button>
                  </li>
                )
              })}
            </ul>
          </>
        )}
      </div>
    )
  }

  return (
    <ul
      className="grid grid-cols-2 gap-2"
      role="group"
      aria-label="언어 선택"
    >
      {locales.map((locale) => {
        const isActive = locale === currentLocale
        return (
          <li key={locale}>
            <button
              type="button"
              onClick={() => handleChange(locale)}
              disabled={isPending}
              aria-pressed={isActive}
              aria-label={localeNames[locale]}
              className={[
                'w-full flex items-center gap-2 rounded-btn border font-sans text-sm font-semibold',
                'min-h-[48px] px-3 transition-colors',
                isActive
                  ? 'border-primary bg-primary text-on-primary'
                  : 'border-hairline bg-canvas text-body active:bg-surface-card',
                isPending ? 'opacity-60' : '',
              ].join(' ')}
            >
              <span aria-hidden="true" className="text-base">{localeFlags[locale]}</span>
              <span className="truncate">{localeNames[locale]}</span>
            </button>
          </li>
        )
      })}
    </ul>
  )
}
