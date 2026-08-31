import type { ReactNode } from 'react'
import Link from 'next/link'

interface Props {
  title: string
  subtitle?: string | null
  /** 뒤로가기 버튼 표시 (링크 경로) */
  back?: string
  rightSlot?: ReactNode
}

/**
 * 어드민 공통 헤더. 학부모 앱의 BrandHeader와 톤을 맞추되,
 * 선생님용임을 나타내는 옅은 블루 그라데이션과 뒤로가기 옵션을 제공한다.
 */
export default function AdminHeader({ title, subtitle, back, rightSlot }: Props) {
  return (
    <header className="sticky top-0 z-10 brand-header-bg border-b border-hairline-soft px-5 py-3.5">
      <div className="flex items-center gap-2.5">
        {back ? (
          <Link
            href={back}
            aria-label="뒤로"
            className="-ml-1 flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-ink active:bg-surface/70"
          >
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" aria-hidden="true">
              <path d="M15 18l-6-6 6-6" stroke="#2B211C" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </Link>
        ) : null}
        <div className="min-w-0 flex-1">
          <h1 className="truncate text-lg font-bold text-ink" style={{ letterSpacing: '-0.01em' }}>
            {title}
          </h1>
          {subtitle ? <p className="mt-0.5 truncate text-xs text-muted">{subtitle}</p> : null}
        </div>
        {rightSlot ? <div className="shrink-0">{rightSlot}</div> : null}
      </div>
    </header>
  )
}
