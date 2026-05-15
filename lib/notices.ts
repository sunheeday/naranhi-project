import 'server-only'
import { createSupabaseServerClient } from '@/lib/supabase/server'
import type { Locale } from '@/lib/i18n'
import { pickTranslation, type Translations } from '@/lib/translations'
import type { CardType, Json, NoticeStatus } from '@/types/database'

/**
 * 공지 상세 조회용 DTO — 프론트(`/notices/[id]/page.tsx`)가 바로 소비할 수 있는 형태.
 */
export interface NoticeDetailDto {
  id: string
  status: NoticeStatus
  errorMessage: string | null
  childId: string
  createdAt: string
  summary: string | null
  /** 사용자 locale에 해당 번역이 캐시돼 있는지 (lazy 번역 트리거용) */
  hasLocaleTranslation: boolean
  summaryTranslations: Translations
  cards: NoticeCardDto[]
}

export interface NoticeCardDto {
  id: string
  type: CardType
  order: number
  content: Json
}

/**
 * 공지 + notice_cards JOIN 조회. RLS에 의해 본인 자녀 공지만 반환된다.
 * 인증된 사용자 세션(서버 컨텍스트)에서만 호출할 것.
 */
export async function getNoticeDetail(
  noticeId: string,
  locale: Locale = 'ko'
): Promise<NoticeDetailDto | null> {
  const supabase = await createSupabaseServerClient()

  const { data: notice, error } = await supabase
    .from('notices')
    .select(
      'id, child_id, status, error_message, created_at, summary_translations'
    )
    .eq('id', noticeId)
    .single()

  if (error || !notice) return null

  const { data: cardRows } = await supabase
    .from('notice_cards')
    .select('id, type, order, content')
    .eq('notice_id', noticeId)
    .order('order', { ascending: true })

  const cards: NoticeCardDto[] = (cardRows ?? []).map(r => ({
    id: r.id,
    type: r.type,
    order: r.order,
    content: r.content,
  }))

  const translations = (notice.summary_translations ?? {}) as Translations
  const summary = pickTranslation(translations, locale)

  return {
    id: notice.id,
    status: notice.status,
    errorMessage: notice.error_message,
    childId: notice.child_id,
    createdAt: notice.created_at,
    summary,
    hasLocaleTranslation: !!translations[locale],
    summaryTranslations: translations,
    cards,
  }
}
