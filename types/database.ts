// 테이블·컬럼 정의의 정본은 types/database.generated.ts 이며, 그 파일은
// `npm run gen:types` 로만 갱신한다 — 손으로 고치지 않는다.
//
// 아래 5개 유니언은 이 파일에 남긴다. NoticeStatus/CardType은 실측 결과
// notices.status/notice_cards.type이 실제 Postgres enum(notice_status,
// notice_card_type)이라 gen types도 동일한 리터럴 유니언을 내지만, DTO 경계에서
// 쓰는 이름을 이 파일 하나로 모아두기 위해 재선언한다. SupportedLocale·
// SchoolCrawlBoardKind·NoticeAiValidationStatus는 DB가 text + CHECK라 gen
// types가 string을 내므로 여기서 값 도메인을 좁혀 제공한다.
// 전 저장소가 '@/types/database'를 import하므로 경로는 그대로 둔다.
export type { Json, Database } from './database.generated'

export type SupportedLocale = 'ko' | 'en' | 'zh' | 'vi' | 'ru' | 'ar' | 'fr' | 'id' | 'th'
export type NoticeStatus = 'pending' | 'processing' | 'done' | 'error'
export type CardType = 'supplies' | 'action' | 'schedule'
export type SchoolCrawlBoardKind = 'family_notice' | 'announcement_fallback' | 'unknown'
/** 0005:14-15 의 CHECK 는 세 값이지만 코드가 쓰는 것은 둘뿐이고, 운영 155행이 전부 'passed' 다.
 *  Task 13 이 DB CHECK 를 이 둘로 좁힌다. */
export type NoticeAiValidationStatus = 'passed' | 'failed'
