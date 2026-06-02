import type { ReactNode } from 'react'
import CharacterImage from './CharacterImage'
import type { CharacterKey } from './characters'

interface Props {
  character: CharacterKey
  title: string
  /** 보조 설명 (선택) */
  description?: string | null
  /** compact: 카드 내부/짧은 영역 · full: 화면 빈 상태 */
  size?: 'compact' | 'full'
  /** 하단 액션 (버튼 등) */
  action?: ReactNode
}

/**
 * 공지 없음 / 급식 없음 / 일정 없음 등 빈 상태에 캐릭터로 따뜻함을 더한다.
 * 색상만이 아니라 텍스트 라벨로 상태를 전달한다.
 */
export default function CharacterEmptyState({
  character,
  title,
  description,
  size = 'full',
  action,
}: Props) {
  const charSize = size === 'full' ? 132 : 92
  return (
    <div
      className={`flex flex-col items-center justify-center text-center ${
        size === 'full' ? 'py-14 gap-4' : 'py-8 gap-3'
      }`}
    >
      <CharacterImage character={character} size={charSize} disc />
      <div className="flex flex-col gap-1 px-6">
        <p className="text-base font-semibold text-ink">{title}</p>
        {description ? (
          <p className="text-sm text-muted leading-relaxed">{description}</p>
        ) : null}
      </div>
      {action ? <div className="mt-1">{action}</div> : null}
    </div>
  )
}
