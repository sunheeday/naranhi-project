import 'server-only'
import { createSupabaseServerClient } from '@/lib/supabase/server'
import type { Locale } from '@/lib/i18n'
import { pickTranslation, type Translations } from '@/lib/translations'
import type { CardType, Json, NoticeStatus } from '@/types/database'

/**
 * 공지 상세 조회용 DTO — 프론트(`/notices/[id]/page.tsx`)가 바로 소비할 수 있는 형태.
 */
/** 원본 첨부 파일 링크 (needs_file 일 때 "원본 파일 직접 확인"에서 사용) */
export interface NoticeFileLink {
  filename: string
  url: string
}

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
  /** 정제 품질이 낮아(평탄화/할루시네이션 위험) 본문 대신 원본 파일을 안내해야 하는지 */
  needsFile: boolean
  /** 사용자가 직접 확인할 원본 첨부 파일들 */
  fileLinks: NoticeFileLink[]
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
      'id, status, error_message, created_at, title, original_text, extracted_content'
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

  const extracted = asJsonObject(notice.extracted_content)
  const needsFile = extracted?.needs_file === true
  const fileLinks = extractFileLinks(extracted)

  return {
    id: notice.id,
    status: notice.status,
    errorMessage: notice.error_message,
    createdAt: notice.created_at,
    summary,
    hasLocaleTranslation: locale === 'ko' ? Boolean(notice.original_text || notice.title) : !!translations[locale],
    summaryTranslations: translations,
    cards,
    needsFile,
    fileLinks,
  }
}

function asJsonObject(value: unknown): Record<string, unknown> | null {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null
}

/** extracted_content.sources[] 에서 사용자가 열어볼 원본 첨부 파일(파일명+URL)을 추린다. */
function extractFileLinks(extracted: Record<string, unknown> | null): NoticeFileLink[] {
  if (!extracted) return []
  const sources = Array.isArray(extracted.sources) ? extracted.sources : []
  const links: NoticeFileLink[] = []
  const seen = new Set<string>()
  for (const source of sources) {
    const obj = asJsonObject(source)
    if (!obj) continue
    const url = typeof obj.origin_url === 'string' ? obj.origin_url.trim() : ''
    const filename = typeof obj.filename === 'string' ? obj.filename.trim() : ''
    if (!url || !filename || seen.has(url)) continue
    seen.add(url)
    links.push({ filename, url })
  }
  return links
}
