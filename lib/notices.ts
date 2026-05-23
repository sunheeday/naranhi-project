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
 * 공지 + notice_cards JOIN 조회. RLS에 의해 본인 자녀의 학교 공지만 반환된다.
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
      'id, status, error_message, created_at, title, original_text'
    )
    .eq('id', noticeId)
    .single()

  if (error || !notice) return null

  const translationQuery = supabase
    .from('notice_ai_translations')
    .select('target_language, translated_text')
    .eq('notice_id', noticeId)

  const { data: translationRows } = locale === 'ko'
    ? { data: [] }
    : await translationQuery.eq('target_language', locale)

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

  const translations: Translations = {}
  if (notice.original_text) translations.ko = notice.original_text
  for (const row of translationRows ?? []) {
    if (row.target_language && row.translated_text) {
      translations[row.target_language] = row.translated_text
    }
  }
  const summary = pickTranslation(translations, locale) ?? notice.title ?? null

  return {
    id: notice.id,
    status: notice.status,
    errorMessage: notice.error_message,
    createdAt: notice.created_at,
    summary,
    hasLocaleTranslation: locale === 'ko' ? Boolean(notice.original_text || notice.title) : !!translations[locale],
    summaryTranslations: translations,
    cards,
  }
}
