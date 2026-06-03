import Image from 'next/image'
import { CHARACTERS, type CharacterKey } from './characters'

interface Props {
  character: CharacterKey
  /** 렌더 크기(px). 정사각 박스 기준. small 64 / medium 120 / hero 220 */
  size: number
  /**
   * 흰 원형 디스크로 감쌀지 여부.
   * 캐릭터 이미지가 흰 배경이라, 색이 있는 면 위에 올릴 때 켜면 자연스럽게 녹아든다.
   */
  disc?: boolean
  /** 정보 전달용이 아니면 빈 문자열(장식). 주변 텍스트로 의미를 전달하는 경우 빈 값 권장. */
  alt?: string
  className?: string
  priority?: boolean
}

/**
 * 나리·누리 캐릭터를 레이아웃 흔들림 없이 고정 크기로 렌더링한다.
 * disc=true면 흰 배경 이미지가 색면 위에서도 자연스럽게 보이도록 원형 디스크 안에 배치한다.
 */
export default function CharacterImage({
  character,
  size,
  disc = false,
  alt = '',
  className = '',
  priority = false,
}: Props) {
  const src = CHARACTERS[character]
  // 디스크 없이 단독 배치할 때만 캐릭터 자체에 그림자를 줘 띄운 느낌을 준다.
  // 디스크 안에서는 디스크의 box-shadow를 쓰고, 캐릭터 그림자는 원 밖으로 새지 않게 끈다.
  const img = (
    <div className="relative" style={{ width: size, height: size }}>
      <Image
        src={src}
        alt={alt}
        fill
        sizes={`${size}px`}
        unoptimized
        priority={priority}
        className={`object-contain select-none ${disc ? '' : 'character-shadow'}`}
        draggable={false}
      />
    </div>
  )

  if (!disc) {
    return <div className={className}>{img}</div>
  }

  // 배경이 투명한 캐릭터를 색면 위에서도 또렷하게 보이도록 둥근 원형 디스크 안에 배치한다.
  const pad = Math.round(size * 0.16)
  return (
    <div
      className={`character-disc rounded-full flex items-center justify-center ${className}`}
      style={{ width: size + pad * 2, height: size + pad * 2 }}
      aria-hidden={alt ? undefined : true}
    >
      {img}
    </div>
  )
}
