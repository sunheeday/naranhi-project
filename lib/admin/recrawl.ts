import 'server-only'

import { createSupabaseServiceClient } from '@/lib/supabase/server'
import { triggerInitialSchoolCrawl } from '@/lib/school-crawler-trigger'

/** 재크롤이 위험한 이유는 삭제가 아니라 «워터마크를 지우는 것»이다. 워터마크는
 *  시각이 아니라 게시판별 최대 글번호다(school_crawler_service.py:_apply_watermark_filter
 *  — 기준선보다 큰 글번호만 신규로 남긴다, 기준선이 없으면 전부 통과). 지우면 다음
 *  크롤이 «이미 있던 글»을 전부 새 글로 재판정한다 — 사용자 결정("지금부터 새로")을
 *  정면으로 어긴다.
 *
 *  다만 규모는 무한이 아니다. 정기 크롤의 스캔 깊이는 CRAWLER_SCHEDULE_NOTICE_COUNT
 *  (.github/workflows/deploy-api-cloud-run.yml:152 — 배포 기준 8)로 게시판당 한 런에
 *  최대 이 값까지만 본다(docs/scheduled-crawl-runbook.md:19,224). 그래서 "워터마크를
 *  무시하면 몇 건이 들어올 수 있는가"를 게시판 개수 × 이 상수로 추정할 수 있다 —
 *  근거 없는 감으로 지어낸 숫자가 아니다.
 */
const SCAN_DEPTH_PER_BOARD_ESTIMATE = 8

export interface RecrawlPreview {
  schoolId: string
  schoolName: string
  noticeCount: number
  translationCount: number
  eventCount: number
  cardCount: number
  watermarkBoards: number
  /** false면 이 학교는 지금도 워터마크가 없다 — ignoreWatermark 를 켜지 않아도
   *  «막을 것이 없는» 상태다. 화면은 이 사실을 체크박스와 무관하게 항상 보여줘야 한다. */
  hasWatermark: boolean
  /** 워터마크를 무시했을 때 한 크롤 사이클에서 "이미 있던 글"이 새 글로 재판정될
   *  수 있는 추정 상한. 근거: SCAN_DEPTH_PER_BOARD_ESTIMATE 주석 참고. */
  estimatedFloodIfIgnored: number
}

async function noticeIdsFor(schoolId: string): Promise<string[]> {
  const service = createSupabaseServiceClient()
  const { data, error } = await service.from('notices').select('id').eq('school_id', schoolId)
  if (error) throw new Error(`공지 목록 조회 실패: ${error.message}`)
  return (data ?? []).map((row) => row.id)
}

/** 삭제 예정 건수. notices 만이 아니라 캐스케이드 대상까지 센다 —
 *  notice_ai_translations(0005:3), school_events(0017:3-4), notice_cards.
 *  「공지 38건 · 번역 155건 · 일정 68건이 삭제됩니다」가 보여야 사람이 판단할 수 있다. */
export async function previewRecrawl(schoolId: string): Promise<RecrawlPreview> {
  const service = createSupabaseServiceClient()

  const { data: school, error: schoolError } = await service
    .from('schools')
    .select('id,name')
    .eq('id', schoolId)
    .maybeSingle()
  if (schoolError) throw new Error(`학교 조회 실패: ${schoolError.message}`)
  if (!school) throw new Error('school_not_found')

  const noticeIds = await noticeIdsFor(schoolId)

  const countIn = async (table: 'notice_ai_translations' | 'school_events' | 'notice_cards') => {
    if (noticeIds.length === 0) return 0
    const { count, error } = await service
      .from(table)
      .select('id', { count: 'exact', head: true })
      .in('notice_id', noticeIds)
    if (error) throw new Error(`${table} 집계 실패: ${error.message}`)
    return count ?? 0
  }

  const { data: state } = await service
    .from('school_crawl_state')
    .select('board_watermarks')
    .eq('school_id', schoolId)
    .maybeSingle()

  const watermarkBoards = Object.keys((state?.board_watermarks ?? {}) as Record<string, unknown>).length

  return {
    schoolId,
    schoolName: school.name,
    noticeCount: noticeIds.length,
    translationCount: await countIn('notice_ai_translations'),
    eventCount: await countIn('school_events'),
    cardCount: await countIn('notice_cards'),
    watermarkBoards,
    hasWatermark: watermarkBoards > 0,
    estimatedFloodIfIgnored: Math.max(watermarkBoards, 1) * SCAN_DEPTH_PER_BOARD_ESTIMATE,
  }
}

export interface RecrawlOptions {
  /** true면 scripts/recrawl_trigger.py 원본과 같은 동작 — board_watermarks 를 {}로
   *  지운다. 기본값은 반드시 false 로 호출해야 한다("워터마크를 존중하는 쪽이 기본"). */
  ignoreWatermark: boolean
}

/** scripts/recrawl_trigger.py 의 ①②④ 를 그대로 옮기되, ③(watermark 리셋)은
 *  ignoreWatermark 가 true 일 때만 수행한다. 원본 스크립트는 항상 지웠다 — 그게
 *  «밀린 게 우르르 온다»의 원인이므로 여기서는 명시적 opt-in 으로 바꿨다.
 *  기본(ignoreWatermark=false)에서는 watermark 를 건드리지 않는다: 남아있는
 *  기준선이 있다면 다음 크롤은 그 기준선보다 새 글만 잡는다(밀린 글 없음).
 *  단, 이 학교에 애초에 watermark 가 없었다면(hasWatermark=false) 이 옵션과
 *  무관하게 보호막이 없다 — previewRecrawl 이 그 사실을 미리 알려준다. */
export async function executeRecrawl(
  schoolId: string,
  options: RecrawlOptions,
): Promise<{ deletedNotices: number; watermarkCleared: boolean; crawlQueued: boolean }> {
  const service = createSupabaseServiceClient()

  // ① notices 삭제 — translations/cards/events 가 캐스케이드로 함께 사라진다.
  const { data: deleted, error: deleteError } = await service
    .from('notices')
    .delete()
    .eq('school_id', schoolId)
    .select('id')
  if (deleteError) throw new Error(`공지 삭제 실패: ${deleteError.message}`)

  // ② watermark 리셋 — ignoreWatermark 로 명시적으로 요청했을 때만.
  let watermarkCleared = false
  if (options.ignoreWatermark) {
    const { error: watermarkError } = await service
      .from('school_crawl_state')
      .update({ board_watermarks: {} })
      .eq('school_id', schoolId)
    if (watermarkError) {
      throw new Error(`watermark 초기화 실패: ${watermarkError.message}`)
    }
    watermarkCleared = true
  }

  // ③ discover-board 큐잉
  const crawlQueued = await triggerInitialSchoolCrawl(schoolId)

  return {
    deletedNotices: deleted?.length ?? 0,
    watermarkCleared,
    crawlQueued,
  }
}
