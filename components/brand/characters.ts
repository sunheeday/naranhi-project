/**
 * 나리·누리 캐릭터 / 로고 자산 카탈로그.
 * 원본은 `로고및캐릭터디자인/`에 보존하고, 웹 표시용 리사이즈본을 `public/characters/`에 둔다.
 * 모든 이미지는 흰 배경(투명 X)이므로 흰 카드/디스크 위에 올려 자연스럽게 보이게 한다.
 */
export const CHARACTERS = {
  /** 앱 로고 (라운드 스퀘어, 나리+누리) — 로그인/스플래시 */
  logoMark: '/characters/logo-mark.png',
  /** 나리·누리 손 흔들기 — 로그인/온보딩 환영 */
  wave: '/characters/nari-nuri-wave.png',
  /** 나리·누리 같이 종이 읽기 — 홈 헤더 */
  readingPaper: '/characters/nari-nuri-reading-paper.png',
  /** 나리·누리 서서 종이 — 처리 중/번역 안내 */
  standingPaper: '/characters/nari-nuri-standing-paper.png',
  /** 나리·누리 손잡고 서 있기 — 설정 프로필/온보딩 아이 정보 */
  holdingHands: '/characters/nari-nuri-holding-hands.png',
  /** 나리·누리 같이 걷기 — 로딩/다음 단계/일정 없음 */
  walk: '/characters/nari-nuri-walk.png',
  /** 따봉 — 저장/완료/성공 피드백 */
  thumbBlue: '/characters/nari-thumb.png',
  thumbYellow: '/characters/nuri-thumb.png',
  /** 포인트(손가락) — 도움말/강조/빈 상태 안내 */
  pointBlue: '/characters/nari-point.png',
  pointYellow: '/characters/nuri-point.png',
  /** 책 읽기 — 급식 헤더/대기·없음 상태 */
  readingYellow: '/characters/nari-reading.png',
  readingBlue: '/characters/nuri-reading.png',
} as const

export type CharacterKey = keyof typeof CHARACTERS
