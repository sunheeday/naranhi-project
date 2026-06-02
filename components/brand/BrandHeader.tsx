import type { ReactNode } from 'react'
import CharacterImage from './CharacterImage'
import type { CharacterKey } from './characters'

interface Props {
  title: string
  subtitle?: string | null
  /** 좌측 타이틀 옆 작은 캐릭터 (선택) */
  character?: CharacterKey
  /** 우측 영역 (설정 링크 등 액션) */
  rightSlot?: ReactNode
}

/**
 * 홈/급식/캘린더/설정 상단 공통 브랜드 헤더.
 * 흰색 고정 헤더 대신 옅은 블루 → 캔버스로 떨어지는 부드러운 브랜드 헤더.
 */
export default function BrandHeader({ title, subtitle, character, rightSlot }: Props) {
  return (
    <header className="sticky top-0 z-10 brand-header-bg border-b border-hairline-soft px-5 py-3.5">
      <div className="flex items-center gap-3">
        {character && (
          <CharacterImage character={character} size={40} disc className="shrink-0" />
        )}
        <div className="min-w-0 flex-1">
          <h1 className="text-lg font-bold text-ink truncate" style={{ letterSpacing: '-0.01em' }}>
            {title}
          </h1>
          {subtitle ? (
            <p className="text-xs text-muted truncate mt-0.5">{subtitle}</p>
          ) : null}
        </div>
        {rightSlot ? <div className="shrink-0">{rightSlot}</div> : null}
      </div>
    </header>
  )
}
