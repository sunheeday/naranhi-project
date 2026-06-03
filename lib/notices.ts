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

/** 소스(본문/첨부)별 카드 — 각 소스의 정제 본문을 따로 보여준다. */
export interface NoticeSourceCard {
  kind: 'body' | 'attachment'
  /** 첨부일 때 파일명(본문은 빈 문자열) */
  filename: string
  /** 정제된 markdown 본문(본문은 번역본 우선, 첨부는 한국어 정제본 — 번역은 후속 단계) */
  content: string
  /** 형식이 복잡해 정제본 대신 원본 파일을 안내해야 하는지 */
  needsFile: boolean
  /** 브라우저에서 미리보기 가능한 형식인지(PDF·이미지) */
  previewable: boolean
  /** 우리 Supabase Storage 의 파일 URL(첨부만) */
  publicUrl: string | null
}

/** 원본 파일 카드에 보여줄 첨부 파일(우리 Storage 사본). */
export interface NoticeAttachmentFile {
  filename: string
  publicUrl: string
  previewable: boolean
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
  /** 본문/첨부 소스별 카드(순서: 본문 → 첨부…) */
  sourceCards: NoticeSourceCard[]
  /** 원본 파일 카드용 첨부 파일 목록(중복 파일 제거) */
  attachmentFiles: NoticeAttachmentFile[]
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
  const sourceCards = buildSourceCards(extracted, translations, locale)
  const attachmentFiles = buildAttachmentFiles(extracted)

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
    sourceCards,
    attachmentFiles,
  }
}

/** PDF·이미지면 브라우저 미리보기 가능. metadata.file_type 로 판단. */
function isPreviewable(source: Record<string, unknown>): boolean {
  const meta = asJsonObject(source.metadata)
  const fileType = typeof meta?.file_type === 'string' ? meta.file_type : ''
  return fileType === 'pdf' || fileType === 'image'
}

/** extracted_content.sources[] → included(중복제거된) 소스를 본문→첨부 순의 카드로. */
function buildSourceCards(
  extracted: Record<string, unknown> | null,
  translations: Translations,
  locale: Locale
): NoticeSourceCard[] {
  if (!extracted) return []
  const sources = Array.isArray(extracted.sources) ? extracted.sources : []
  const includedIds = new Set(
    (Array.isArray(extracted.included_source_ids) ? extracted.included_source_ids : []).map(String)
  )
  const rows: (NoticeSourceCard & { _isBody: boolean; _order: number })[] = []
  for (const source of sources) {
    const obj = asJsonObject(source)
    if (!obj) continue
    if (!includedIds.has(String(obj.source_id ?? ''))) continue
    const isBody = obj.source_type === 'html_body'
    const refined = typeof obj.refined_text === 'string' ? obj.refined_text : ''
    // 본문은 번역본 우선(기존 번역 흐름 재사용), 첨부는 한국어 정제본(번역은 후속 단계).
    const content = (isBody ? pickTranslation(translations, locale) ?? refined : refined) || ''
    const meta = asJsonObject(obj.metadata)
    rows.push({
      kind: isBody ? 'body' : 'attachment',
      filename: typeof obj.filename === 'string' ? obj.filename : '',
      content,
      needsFile: obj.needs_file === true,
      previewable: isPreviewable(obj),
      publicUrl: typeof obj.public_url === 'string' ? obj.public_url : null,
      _isBody: isBody,
      _order: typeof meta?.order_index === 'number' ? meta.order_index : 999,
    })
  }
  rows.sort((a, b) => (a._isBody === b._isBody ? a._order - b._order : a._isBody ? -1 : 1))
  return rows.map(({ _isBody, _order, ...card }) => card)
}

/** extracted_content.sources[] → public_url 있는 첨부 파일들(중복 URL 제거). */
function buildAttachmentFiles(extracted: Record<string, unknown> | null): NoticeAttachmentFile[] {
  if (!extracted) return []
  const sources = Array.isArray(extracted.sources) ? extracted.sources : []
  const seen = new Set<string>()
  const files: NoticeAttachmentFile[] = []
  for (const source of sources) {
    const obj = asJsonObject(source)
    if (!obj) continue
    const url = typeof obj.public_url === 'string' ? obj.public_url.trim() : ''
    if (!url || seen.has(url)) continue
    seen.add(url)
    const filename = typeof obj.filename === 'string' && obj.filename.trim() ? obj.filename.trim() : 'attachment'
    files.push({ filename, publicUrl: url, previewable: isPreviewable(obj) })
  }
  return files
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
